"""Tests for deterministic Bermuda tuning calculations."""

from custom_components.bermuda_tuner.analyzer import (
    audit,
    balance_scanners,
    calibrate_attenuation,
    calibrate_reference_power,
    explain_settings,
    walk_test,
)


def advert(name, samples, distance=1.0):
    return {
        "advert_key": f"device__{name}",
        "scanner_device": name,
        "hist_rssi": samples,
        "rssi_distance": distance,
    }


def test_one_meter_uses_robust_median():
    result = calibrate_reference_power(advert("Kitchen", [-60, -59, -60, -61, -10]))
    assert result["recommended_ref_power"] == -60
    assert not result["stable"]


def test_attenuation_matches_path_loss_formula():
    result = calibrate_attenuation(advert("Kitchen", [-74] * 6), 5, -60)
    assert result["recommended_attenuation"] == 2.003
    assert result["plausible"]


def test_scanner_balancing_centers_medians():
    result = balance_scanners([advert("A", [-70] * 5), advert("B", [-60] * 5)])
    assert result["reference_median_rssi"] == -65
    assert result["recommended_rssi_offsets"] == {"A": 5.0, "B": -5.0}


def test_walk_test_flags_small_margin():
    result = walk_test([advert("A", [-60] * 5), advert("B", [-62] * 5)])
    assert result["nearest"]["scanner"] == "A"
    assert result["margin_db"] == 2
    assert result["ambiguous"]


def test_audit_reports_weak_coverage():
    dump = {
        "device": {
            "name": "Beacon",
            "adverts": {"device__Kitchen": advert("Kitchen", [-60] * 5)},
        }
    }
    result = audit(dump)
    assert result["scanner_count"] == 1
    assert result["weak_coverage_devices"] == ["Beacon"]


def test_settings_explanation_contains_values():
    result = explain_settings({"smoothing_samples": 12, "update_interval": 5})
    assert "12 readings" in result["smoothing_samples"]
    assert "5 s" in result["update_interval"]
