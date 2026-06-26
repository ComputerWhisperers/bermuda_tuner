"""Deterministic Bermuda observation analysis."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from math import log10
from statistics import median, pstdev
from typing import Any

UNHELPFUL_KEYS = {"readings"}


def _label(key: Any) -> str:
    """Turn machine keys into short labels for humans."""
    return str(key).replace("_", " ").capitalize()


def format_human_result(value: Any, indent: int = 0) -> str:
    """Format nested analyzer results as readable Home Assistant dialog text."""
    prefix = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if key in UNHELPFUL_KEYS and isinstance(item, list):
                continue
            label = _label(key)
            if isinstance(item, dict | list):
                nested = format_human_result(item, indent + 1)
                if nested:
                    lines.append(f"{prefix}{label}:")
                    lines.append(nested)
            elif item is not None:
                lines.append(f"{prefix}{label}: {_format_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                nested = format_human_result(item, indent + 1)
                if nested:
                    lines.append(f"{prefix}-")
                    lines.append(nested)
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return "\n".join(lines)
    return f"{prefix}{_format_scalar(value)}"


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _numbers(values: Iterable[Any]) -> list[float]:
    return [float(value) for value in values if isinstance(value, int | float)]


def adverts_from_dump(dump: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Bermuda adverts while retaining useful device context."""
    adverts: list[dict[str, Any]] = []
    for device_key, device in dump.items():
        if not isinstance(device, dict):
            continue
        for advert_key, advert in (device.get("adverts") or {}).items():
            if isinstance(advert, dict):
                adverts.append(
                    {
                        **advert,
                        "device_key": device_key,
                        "device_name": device.get("name", device_key),
                        "advert_key": advert_key,
                    }
                )
    return adverts


def scanner_name(advert: dict[str, Any]) -> str:
    """Return the best non-secret scanner label in an advert."""
    scanner = advert.get("scanner_device") or advert.get("scanner_name")
    if scanner:
        return str(scanner)
    key = str(advert.get("advert_key", "unknown"))
    return key.rsplit("__", 1)[-1]


def stable_rssi(advert: dict[str, Any]) -> dict[str, float | int]:
    """Summarize a history using robust median and population spread."""
    samples = _numbers(advert.get("hist_rssi") or [])
    if not samples and isinstance(advert.get("rssi"), int | float):
        samples = [float(advert["rssi"])]
    if not samples:
        raise ValueError("No RSSI samples were available")
    return {
        "samples": len(samples),
        "median_rssi": round(median(samples), 2),
        "spread_db": round(pstdev(samples), 2) if len(samples) > 1 else 0.0,
    }


def calibrate_reference_power(advert: dict[str, Any]) -> dict[str, Any]:
    """Calculate one-metre reference power from observed RSSI."""
    result = stable_rssi(advert)
    result["recommended_ref_power"] = result["median_rssi"]
    result["stable"] = result["samples"] >= 5 and result["spread_db"] <= 3
    result["guidance"] = (
        "Use this value for Bermuda's ref_power if this beacon was exactly one metre away."
        if result["stable"]
        else (
            "Do not use this yet. Keep the beacon and scanner still, collect at least five "
            "readings, and try for a spread under 3 dB."
        )
    )
    return result


def calibrate_attenuation(
    advert: dict[str, Any], measured_distance: float, reference_power: float
) -> dict[str, Any]:
    """Calculate path-loss exponent from a measured distance."""
    if measured_distance <= 1:
        raise ValueError("Measured distance must be greater than one metre")
    result = stable_rssi(advert)
    attenuation = (reference_power - float(result["median_rssi"])) / (10 * log10(measured_distance))
    result.update(
        measured_distance=measured_distance,
        reference_power=reference_power,
        recommended_attenuation=round(attenuation, 3),
        plausible=1.2 <= attenuation <= 6,
    )
    result["guidance"] = (
        "Use this value for Bermuda's attenuation."
        if result["plausible"]
        else (
            "This result looks unusual. Recheck the measured distance, keep the beacon still, "
            "and make sure you used the one-metre reference power from the same scanner."
        )
    )
    return result


def balance_scanners(adverts: list[dict[str, Any]]) -> dict[str, Any]:
    """Recommend offsets that align each scanner to the median scanner."""
    medians: dict[str, float] = {}
    for advert in adverts:
        try:
            medians[scanner_name(advert)] = float(stable_rssi(advert)["median_rssi"])
        except ValueError:
            continue
    if len(medians) < 2:
        raise ValueError("At least two scanners with RSSI history are required")
    target = median(medians.values())
    return {
        "reference_median_rssi": round(target, 2),
        "scanner_medians": {key: round(value, 2) for key, value in medians.items()},
        "recommended_rssi_offsets": {
            key: round(target - value, 1) for key, value in medians.items()
        },
        "guidance": (
            "Positive offsets strengthen quiet scanners; negative offsets soften loud scanners. "
            "Apply these as Bermuda rssi_offsets only after testing with a still beacon."
        ),
    }


def walk_test(adverts: list[dict[str, Any]], ambiguity_db: float = 4) -> dict[str, Any]:
    """Rank current scanner readings and identify ambiguous transitions."""
    readings = []
    for advert in adverts:
        try:
            summary = stable_rssi(advert)
        except ValueError:
            continue
        readings.append(
            {
                "scanner": scanner_name(advert),
                "rssi": summary["median_rssi"],
                "distance": advert.get("rssi_distance"),
            }
        )
    readings.sort(key=lambda row: float(row["rssi"]), reverse=True)
    nearest = readings[0] if readings else None
    second = readings[1] if len(readings) > 1 else None
    margin = (
        round(float(nearest["rssi"]) - float(second["rssi"]), 2) if nearest and second else None
    )
    return {
        "nearest": nearest,
        "second_nearest": second,
        "margin_db": margin,
        "ambiguous": margin is not None and margin < ambiguity_db,
        "guidance": (
            "This location is ambiguous; improve scanner placement or reduce overlap before "
            "trusting area changes here."
            if margin is not None and margin < ambiguity_db
            else "The strongest scanner is clearly ahead at this point."
        ),
        "readings": readings,
    }


def audit(dump: dict[str, Any], stale_seconds: float = 120) -> dict[str, Any]:
    """Audit scanner coverage and stale relationships."""
    adverts = adverts_from_dump(dump)
    scanners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stale = []
    unstable = []
    for advert in adverts:
        name = scanner_name(advert)
        scanners[name].append(advert)
        interval = advert.get("interval") or advert.get("hist_interval", [0])[0]
        if isinstance(interval, int | float) and interval > stale_seconds:
            stale.append({"scanner": name, "device": advert.get("device_name")})
        try:
            summary = stable_rssi(advert)
            if summary["spread_db"] > 6:
                unstable.append(
                    {
                        "scanner": name,
                        "device": advert.get("device_name"),
                        "spread_db": summary["spread_db"],
                    }
                )
        except ValueError:
            pass
    device_scanner_counts = defaultdict(int)
    for advert in adverts:
        device_scanner_counts[str(advert.get("device_name"))] += 1
    weak_coverage = [name for name, count in device_scanner_counts.items() if count < 2]
    findings = []
    if len(scanners) < 2:
        findings.append("Only one scanner is visible; room-level handoffs cannot be validated.")
    if stale:
        findings.append(f"{len(stale)} scanner relationship(s) appear stale.")
    if weak_coverage:
        findings.append(f"{len(weak_coverage)} device(s) are visible to fewer than two scanners.")
    if unstable:
        findings.append(f"{len(unstable)} relationship(s) have RSSI spread above 6 dB.")
    if not findings:
        findings.append("No obvious coverage or freshness problems were found.")
    return {
        "summary": findings,
        "scanner_count": len(scanners),
        "device_count": len(device_scanner_counts),
        "stale_relationships": stale,
        "weak_coverage_devices": weak_coverage,
        "unstable_relationships": unstable,
        "next_step": _audit_next_step(stale, weak_coverage, unstable, len(scanners)),
    }


def _audit_next_step(
    stale: list[dict[str, Any]],
    weak_coverage: list[str],
    unstable: list[dict[str, Any]],
    scanner_count: int,
) -> str:
    if scanner_count < 2:
        return "Add or enable another scanner before calibrating."
    if stale:
        return "Fix stale scanner relationships first; calibration needs fresh RSSI history."
    if weak_coverage:
        return (
            "Move scanners or devices so each important beacon is heard by at least two scanners."
        )
    if unstable:
        return "Stabilize noisy readings before calculating offsets."
    return "Run the one-metre calibration next."


def explain_settings(settings: dict[str, Any]) -> dict[str, str]:
    """Explain Bermuda settings and observed trade-offs in plain English."""
    smoothing = int(settings.get("smoothing_samples", 20))
    interval = int(settings.get("update_interval", 10))
    velocity = float(settings.get("max_velocity", 3))
    radius = float(settings.get("max_area_radius", 20))
    timeout = int(settings.get("devtracker_nothome_timeout", 30))
    return {
        "Smoothing": (
            f"Bermuda averages {smoothing} readings before trusting movement. Higher values "
            "reduce jumping between rooms, but make room changes slower."
        ),
        "Fast movement filter": (
            f"Bermuda rejects distance changes that imply a device moved faster than "
            f"{velocity:g} m/s. Lower values ignore more sudden jumps, but can also ignore "
            "real movement."
        ),
        "Room claim radius": (
            f"A scanner must estimate the device within {radius:g} m before Bermuda lets it "
            "claim that room. Smaller values reduce false room changes, but may miss weak rooms."
        ),
        "Update speed": (
            f"Bermuda updates entities at most every {interval} seconds. Lower values react "
            "faster and collect more history, but add more activity."
        ),
        "Away timeout": (
            f"If a device is silent for {timeout} seconds, Bermuda can mark it away. Longer "
            "values tolerate missed Bluetooth packets, but keep missing devices home longer."
        ),
        "Combined effect": (
            f"With {smoothing} samples and {interval} s updates, changes may feel "
            "deliberately damped. Test real room handoffs before increasing smoothing further."
        ),
    }
