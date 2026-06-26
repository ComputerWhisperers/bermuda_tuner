"""Home Assistant orchestration for Bermuda Tuner."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .analyzer import adverts_from_dump
from .const import BERMUDA_DOMAIN, DEFAULTS, DOMAIN, TUNABLE_KEYS

MAC_PATTERN = re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b")
IRK_PATTERN = re.compile(r"(?i)\b[0-9a-f]{32}\b")


class TunerManager:
    """Collect observations and safely manage Bermuda options."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.snapshots")

    def bermuda_entry(self):
        """Return the active Bermuda entry."""
        entries = self.hass.config_entries.async_entries(BERMUDA_DOMAIN)
        if not entries:
            raise ValueError("Bermuda is not configured")
        return entries[0]

    async def dump(self, addresses: str = "") -> dict[str, Any]:
        """Request a redacted in-memory dump directly from Bermuda."""
        result: Any = await self.hass.services.async_call(
            BERMUDA_DOMAIN,
            "dump_devices",
            {"addresses": addresses, "configured_devices": not bool(addresses), "redact": True},
            blocking=True,
            return_response=True,
        )
        return dict(result or {})

    @staticmethod
    def redact(data: Any) -> Any:
        """Defense-in-depth removal of addresses and IRKs."""
        raw = json.dumps(data, default=str)
        labels: dict[str, str] = {}

        def replace(match: re.Match[str]) -> str:
            value = match.group(0).lower()
            if value not in labels:
                digest = hashlib.sha256(value.encode()).hexdigest()[:8]
                labels[value] = f"REDACTED_{digest}"
            return labels[value]

        return json.loads(IRK_PATTERN.sub(replace, MAC_PATTERN.sub(replace, raw)))

    def current_settings(self) -> dict[str, Any]:
        """Return effective documented Bermuda options."""
        entry = self.bermuda_entry()
        return {key: entry.options.get(key, DEFAULTS[key]) for key in TUNABLE_KEYS}

    async def apply(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Snapshot and apply a validated Bermuda option patch."""
        unknown = set(patch) - TUNABLE_KEYS
        if unknown:
            raise ValueError(f"Unsupported Bermuda setting(s): {', '.join(sorted(unknown))}")
        entry = self.bermuda_entry()
        before = dict(entry.options)
        snapshots = await self.store.async_load() or {"items": []}
        snapshot = {
            "created_at": datetime.now(UTC).isoformat(),
            "entry_id": entry.entry_id,
            "options": before,
        }
        snapshots["items"] = [*snapshots.get("items", [])[-9:], snapshot]
        await self.store.async_save(snapshots)
        updated = {**before, **patch}
        self.hass.config_entries.async_update_entry(entry, options=updated)
        return {"snapshot": snapshot["created_at"], "before": before, "after": updated}

    async def rollback(self) -> dict[str, Any]:
        """Restore the latest matching Bermuda option snapshot."""
        entry = self.bermuda_entry()
        snapshots = await self.store.async_load() or {"items": []}
        items = snapshots.get("items", [])
        snapshot = next(
            (item for item in reversed(items) if item["entry_id"] == entry.entry_id), None
        )
        if snapshot is None:
            raise ValueError("No rollback snapshot is available")
        before = dict(entry.options)
        self.hass.config_entries.async_update_entry(entry, options=snapshot["options"])
        return {"restored": snapshot["created_at"], "before": before, "after": snapshot["options"]}

    @staticmethod
    def select_adverts(dump: dict[str, Any], scanner: str = "") -> list[dict[str, Any]]:
        """Select scanner adverts by case-insensitive label fragment."""
        adverts = adverts_from_dump(dump)
        if scanner:
            needle = scanner.casefold()
            adverts = [row for row in adverts if needle in str(row).casefold()]
        if not adverts:
            raise ValueError("No matching scanner observations were found")
        return adverts
