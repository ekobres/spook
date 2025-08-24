"""Spook - Your homie."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, TypedDict

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import ServiceCall, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

try:
    from homeassistant.helpers import label_registry as lr  # HA 2024.12+
except Exception:  # pragma: no cover
    lr = None  # type: ignore[assignment]

from homeassistant.helpers.area_registry import EVENT_AREA_REGISTRY_UPDATED
from homeassistant.helpers.device_registry import EVENT_DEVICE_REGISTRY_UPDATED
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

if lr is not None:
    from homeassistant.helpers.label_registry import (  # type: ignore[attr-defined]
        EVENT_LABEL_REGISTRY_UPDATED,
    )

from .. import AbstractSpookService


_STATUS_SLUG_TO_LABEL = {
    "available": "Available",
    "unavailable": "Unavailable",
    "enabled": "Enabled",
    "disabled": "Disabled",
    "visible": "Visible",
    "hidden": "Hidden",
    "unmanageable": "Unmanageable",
    "not_provided": "Not provided",
}


class StatusOut(TypedDict, total=False):
    disabled_by: Optional[str]
    hidden_by: Optional[str]
    available: bool
    unknown: bool
    unmanageable: bool
    not_provided: bool


def _to_lower_set(items: Any) -> Optional[set[str]]:
    if not items:
        return None
    if isinstance(items, list):
        s = {str(x).strip() for x in items if str(x).strip()}
    else:
        s = {str(items).strip()}
    return {i.lower() for i in s}


def _to_id_set(items: Any) -> Optional[set[str]]:
    if not items:
        return None
    if isinstance(items, list):
        return {str(x) for x in items if str(x)}
    return {str(items)}


def _ci_contains(hay: Optional[str], needle: str) -> bool:
    if not needle:
        return True
    if not hay:
        return False
    return needle in hay.lower()


def _iso_or_none(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


class ListFilteredEntities(AbstractSpookService):
    name = "list_filtered_entities"
    description = "Return entities that match the selected filters. Response includes a count and a list of entity IDs, or objects with requested values."
    supports_response = True

    _opt_domains: list[str] | None = None
    _opt_integrations: list[str] | None = None
    _opt_labels: list[dict[str, str]] | None = None
    _listeners_attached: bool = False

    def _attach_listeners(self) -> None:
        if self._listeners_attached:
            return

        @callback
        def _on_registry_changed(event) -> None:
            self._rebuild_dynamic_options()

        bus = self.hass.bus
        bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, _on_registry_changed)
        bus.async_listen(EVENT_DEVICE_REGISTRY_UPDATED, _on_registry_changed)
        bus.async_listen(EVENT_AREA_REGISTRY_UPDATED, _on_registry_changed)
        if lr is not None:
            bus.async_listen(EVENT_LABEL_REGISTRY_UPDATED, _on_registry_changed)  # type: ignore[arg-type]

        self._listeners_attached = True

    def _rebuild_dynamic_options(self) -> None:
        entity_reg = er.async_get(self.hass)

        domains: set[str] = set()
        integrations: set[str] = set()
        for entry in entity_reg.entities.values():
            domains.add(entry.domain)
            if entry.platform:
                integrations.add(entry.platform)

        self._opt_domains = sorted(domains)
        self._opt_integrations = sorted(integrations)

        if lr is not None:
            label_reg = lr.async_get(self.hass)  # type: ignore[union-attr]
            self._opt_labels = [
                {"label": (label.name or label.id), "value": label.id}
                for label in sorted(label_reg.labels.values(), key=lambda l: (l.name or l.id).lower())
            ]
        else:
            self._opt_labels = []

    def _ensure_dynamic_options(self) -> None:
        if (
            self._opt_domains is None
            or self._opt_integrations is None
            or self._opt_labels is None
        ):
            self._rebuild_dynamic_options()
        self._attach_listeners()

    @property
    def fields(self) -> dict[str, Any]:
        # Provide dynamic options for selectors we populate at runtime (no user-facing strings)
        self._ensure_dynamic_options()
        return {
            "domains": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "custom_value": True,
                        "options": self._opt_domains or [],
                    }
                }
            },
            "integrations": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "custom_value": True,
                        "options": self._opt_integrations or [],
                    }
                }
            },
            "labels": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "options": self._opt_labels or [],
                    }
                }
            },
        }

    async def async_handle(self, call: ServiceCall) -> dict[str, Any]:
        data = call.data or {}

        # Note: area_id/device_id/label_id are IDs; do NOT lowercase
        areas = _to_id_set(data.get("areas"))
        devices = _to_id_set(data.get("devices"))
        label_ids = _to_id_set(data.get("labels"))

        # Domains & integrations are slugs: case-insensitive
        domains = _to_lower_set(data.get("domains"))
        integrations = _to_lower_set(data.get("integrations"))
        status_filter = _to_lower_set(data.get("status"))

        search = str(data.get("search") or "").strip().lower() or None

        values: list[str] = data.get("values") or []
        if not isinstance(values, list):
            values = []
        values_set = {str(v) for v in values}

        # Limit & safety cap
        limit = data.get("limit", 500)
        try:
            limit = int(limit) if limit is not None else None
        except Exception:
            limit = 500
        safety_cap = 50000
        limit_effective = safety_cap if limit is None else max(1, min(safety_cap, limit))

        area_reg = ar.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        label_reg = lr.async_get(self.hass) if lr is not None else None  # type: ignore[call-arg]

        # Maps for names
        area_name_by_id: dict[str, str] = {a.id: (a.name or a.id) for a in area_reg.areas.values()}
        device_name_by_id: dict[str, str] = {
            d.id: (d.name_by_user or d.name or d.id) for d in device_reg.devices.values()
        }

        # Integration names (config entry titles) cached lazily
        config_entry_name_by_id: dict[str, Optional[str]] = {}

        results: list[Any] = []

        # Deterministic iteration
        for entity_id, entry in sorted(entity_reg.entities.items(), key=lambda kv: kv[0]):
            # Filter: areas/devices/domains/integrations
            if areas is not None and (entry.area_id or "") not in areas:
                continue
            if devices is not None and (entry.device_id or "") not in devices:
                continue
            if domains is not None and entry.domain.lower() not in domains:
                continue
            integ_slug = (entry.platform or "").lower()
            if integrations is not None and integ_slug not in integrations:
                continue

            # Status flags
            state_obj = self.hass.states.get(entity_id)
            has_state = state_obj is not None
            state_str = state_obj.state if has_state else None

            available = bool(has_state and state_str not in (STATE_UNAVAILABLE, STATE_UNKNOWN))
            unknown = bool(has_state and state_str == STATE_UNKNOWN)

            disabled_by = entry.disabled_by
            hidden_by = getattr(entry, "hidden_by", None)  # older HA compatibility
            unmanageable = not bool(entry.unique_id)

            # "Not provided": entity exists in registry but not currently created by integration
            not_provided = (not has_state) and bool(entry.platform) and bool(entry.config_entry_id)

            entity_statuses: set[str] = set()
            entity_statuses.add("available" if available else "unavailable")
            entity_statuses.add("enabled" if disabled_by is None else "disabled")
            entity_statuses.add("visible" if hidden_by is None else "hidden")
            if unmanageable:
                entity_statuses.add("unmanageable")
            if not_provided:
                entity_statuses.add("not_provided")

            if status_filter is not None and not (entity_statuses & status_filter):
                continue

            # Labels filter
            entry_labels_ids = set(getattr(entry, "labels", []) or [])
            if label_ids is not None and not (entry_labels_ids & label_ids):
                continue

            # Search (names & identifiers, exclude icon/created/modified)
            if search:
                name = entry.name or ""
                device_name = device_name_by_id.get(entry.device_id or "", "")
                area_name = area_name_by_id.get(entry.area_id or "", "")

                integration_name = ""
                if entry.config_entry_id:
                    if entry.config_entry_id not in config_entry_name_by_id:
                        ce = self.hass.config_entries.async_get_entry(entry.config_entry_id)
                        config_entry_name_by_id[entry.config_entry_id] = ce.title if ce and getattr(ce, "title", None) else None
                    integration_name = config_entry_name_by_id.get(entry.config_entry_id) or ""

                label_names: list[str] = []
                if label_reg is not None:
                    for lid in entry_labels_ids:
                        lbl = label_reg.labels.get(lid)
                        if lbl and lbl.name:
                            label_names.append(lbl.name)

                # Include both slugs and labels for statuses
                status_labels = [_STATUS_SLUG_TO_LABEL[s] for s in entity_statuses if s in _STATUS_SLUG_TO_LABEL]

                haystacks = [
                    entity_id,
                    name,
                    entry.domain,
                    integ_slug,
                    integration_name,
                    device_name,
                    area_name,
                    *label_names,
                    *list(entity_statuses),
                    *status_labels,
                ]
                if not any(_ci_contains(h, search) for h in haystacks):
                    continue

            # Build output
            if not values_set:
                results.append(entity_id)
            else:
                item: Dict[str, Any] = {"entity_id": entity_id}

                if "name" in values_set:
                    item["name"] = entry.name or None

                if "device" in values_set:
                    did = entry.device_id
                    item["device_id"] = did
                    item["device_name"] = device_name_by_id.get(did or "", None)

                if "area" in values_set:
                    aid = entry.area_id
                    item["area_id"] = aid
                    item["area_name"] = area_name_by_id.get(aid or "", None)

                if "integration" in values_set:
                    item["integration_slug"] = entry.platform
                    integ_name: Optional[str] = None
                    if entry.config_entry_id:
                        if entry.config_entry_id not in config_entry_name_by_id:
                            ce = self.hass.config_entries.async_get_entry(entry.config_entry_id)
                            config_entry_name_by_id[entry.config_entry_id] = ce.title if ce and getattr(ce, "title", None) else None
                        integ_name = config_entry_name_by_id.get(entry.config_entry_id)
                    item["integration_name"] = integ_name

                if "status" in values_set:
                    item["status"] = StatusOut(
                        disabled_by=disabled_by,
                        hidden_by=hidden_by,
                        available=available,
                        unknown=unknown,
                        unmanageable=unmanageable,
                        not_provided=not_provided,
                    )

                if "icon" in values_set:
                    item["icon"] = getattr(entry, "icon", None)

                if "created" in values_set:
                    item["created"] = _iso_or_none(getattr(entry, "created", None))

                if "modified" in values_set:
                    mod = getattr(entry, "modified", None)
                    if mod is None:
                        mod = getattr(entry, "updated", None)
                    item["modified"] = _iso_or_none(mod)

                if "labels" in values_set:
                    labels_out = []
                    if label_reg is not None:
                        for lid in entry_labels_ids:
                            lbl = label_reg.labels.get(lid)
                            labels_out.append(
                                {
                                    "label_id": lid,
                                    "label_name": (lbl.name if lbl and lbl.name else None),
                                }
                            )
                    else:
                        labels_out = [{"label_id": lid, "label_name": None} for lid in entry_labels_ids]
                    item["labels"] = labels_out

                results.append(item)

            if len(results) >= limit_effective:
                break

        return {"count": len(results), "entities": results}