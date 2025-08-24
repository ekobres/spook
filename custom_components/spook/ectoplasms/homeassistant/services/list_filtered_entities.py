"""Spook - Your homie."""

from __future__ import annotations

from datetime import datetime
<<<<<<< HEAD
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
=======
from typing import TYPE_CHECKING, Any

from homeassistant.components.homeassistant import DOMAIN
from homeassistant.core import Event, ServiceResponse, SupportsResponse, callback
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)

from ....services import AbstractSpookService

if TYPE_CHECKING:
    from homeassistant.core import ServiceCall

# Status filter options
STATUS_OPTIONS = [
    "available",
    "unavailable",
    "enabled",
    "disabled",
    "visible",
    "hidden",
    "unmanageable",
    "not_provided",
]

# Values/columns options
VALUES_OPTIONS = [
    "name",
    "device",
    "area",
    "integration",
    "status",
    "icon",
    "created",
    "modified",
    "labels",
]

# Safety limit for number of entities to return
MAX_ENTITIES_LIMIT = 50000


class SpookService(AbstractSpookService):
    """Home Assistant service to list filtered entities."""

    domain = DOMAIN
    service = "list_filtered_entities"
    supports_response = SupportsResponse.ONLY

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the service."""
        super().__init__(*args, **kwargs)
        self._areas_cache: dict[str, str] | None = None
        self._devices_cache: dict[str, str] | None = None
        self._integrations_cache: dict[str, str] | None = None
        self._domains_cache: list[str] | None = None
        self._labels_cache: dict[str, str] | None = None
        self._listeners_setup = False

    def _setup_event_listeners(self) -> None:
        """Set up event listeners for registry updates."""
        if self._listeners_setup:
            return

        self.hass.bus.async_listen(
            ar.EVENT_AREA_REGISTRY_UPDATED,
            self._handle_registry_updated,
        )
        self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            self._handle_registry_updated,
        )
        self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            self._handle_registry_updated,
        )
        
        # Feature detect label registry support
        if hasattr(lr, "async_get"):
            self.hass.bus.async_listen(
                lr.EVENT_LABEL_REGISTRY_UPDATED,
                self._handle_registry_updated,
            )
        
        self._listeners_setup = True

    @callback
    def _handle_registry_updated(self, _event: Event) -> None:
        """Handle registry update events by invalidating caches."""
        self._areas_cache = None
        self._devices_cache = None
        self._integrations_cache = None
        self._domains_cache = None
        self._labels_cache = None

    def _get_areas_options(self) -> list[dict[str, str]]:
        """Get areas selector options."""
        if self._areas_cache is None:
            area_registry = ar.async_get(self.hass)
            self._areas_cache = {
                area.id: area.name
                for area in area_registry.areas.values()
            }
        
        return [
            {"value": area_id, "label": name}
            for area_id, name in sorted(self._areas_cache.items(), key=lambda x: x[1])
        ]

    def _get_devices_options(self) -> list[dict[str, str]]:
        """Get devices selector options."""
        if self._devices_cache is None:
            device_registry = dr.async_get(self.hass)
            self._devices_cache = {}
            for device in device_registry.devices.values():
                name = device.name_by_user or device.name
                if name:
                    self._devices_cache[device.id] = name
        
        return [
            {"value": device_id, "label": name}
            for device_id, name in sorted(self._devices_cache.items(), key=lambda x: x[1])
        ]

    def _get_integrations_options(self) -> list[dict[str, str]]:
        """Get integrations selector options."""
        if self._integrations_cache is None:
            entity_registry = er.async_get(self.hass)
            integrations: set[str] = set()
            
            for entry in entity_registry.entities.values():
                if entry.platform:
                    integrations.add(entry.platform)
            
            self._integrations_cache = {
                integration: integration.replace("_", " ").title()
                for integration in integrations
            }
        
        return [
            {"value": integration, "label": name}
            for integration, name in sorted(self._integrations_cache.items(), key=lambda x: x[1])
        ]

    def _get_domains_options(self) -> list[dict[str, str]]:
        """Get domains selector options."""
        if self._domains_cache is None:
            entity_registry = er.async_get(self.hass)
            domains: set[str] = set()
            
            for entry in entity_registry.entities.values():
                domain = entry.entity_id.split(".", 1)[0]
                domains.add(domain)
            
            self._domains_cache = sorted(domains)
        
        return [
            {"value": domain, "label": domain.replace("_", " ").title()}
            for domain in self._domains_cache
        ]

    def _get_labels_options(self) -> list[dict[str, str]]:
        """Get labels selector options."""
        if not hasattr(lr, "async_get"):
            return []
            
        if self._labels_cache is None:
            try:
                label_registry = lr.async_get(self.hass)
                self._labels_cache = {
                    label.label_id: label.name
                    for label in label_registry.labels.values()
                }
            except AttributeError:
                # Labels not supported in this HA version
                return []
        
        return [
            {"value": label_id, "label": name}
            for label_id, name in sorted(self._labels_cache.items(), key=lambda x: x[1])
        ]

    @property
    def fields(self) -> dict[str, Any]:
        """Return the fields for this service."""
        self._setup_event_listeners()
        
        return {
            "search": cv.string,
            "areas": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "options": self._get_areas_options(),
                    }
                }
            },
            "devices": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "options": self._get_devices_options(),
                    }
                }
            },
>>>>>>> 3f18a4f (Implement list_filtered_entities action)
            "domains": {
                "selector": {
                    "select": {
                        "multiple": True,
<<<<<<< HEAD
                        "custom_value": True,
                        "options": self._opt_domains or [],
=======
                        "options": self._get_domains_options(),
>>>>>>> 3f18a4f (Implement list_filtered_entities action)
                    }
                }
            },
            "integrations": {
                "selector": {
                    "select": {
                        "multiple": True,
<<<<<<< HEAD
                        "custom_value": True,
                        "options": self._opt_integrations or [],
=======
                        "options": self._get_integrations_options(),
                    }
                }
            },
            "status": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "options": [
                            {"value": status, "label": status.replace("_", " ").title()}
                            for status in STATUS_OPTIONS
                        ],
>>>>>>> 3f18a4f (Implement list_filtered_entities action)
                    }
                }
            },
            "labels": {
                "selector": {
                    "select": {
                        "multiple": True,
<<<<<<< HEAD
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
=======
                        "options": self._get_labels_options(),
                    }
                }
            },
            "values": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "options": [
                            {"value": value, "label": value.replace("_", " ").title()}
                            for value in VALUES_OPTIONS
                        ],
                    }
                }
            },
            "limit": cv.positive_int,
        }

    def _matches_search(
        self,
        entity_entry: er.RegistryEntry,
        search_term: str,
        entity_data: dict[str, Any],
    ) -> bool:
        """Check if entity matches search term."""
        if not search_term:
            return True
            
        search_lower = search_term.lower()
        
        # Search fields to check
        search_fields = [
            entity_entry.entity_id,
            entity_entry.entity_id.split(".", 1)[0],  # domain
            entity_entry.platform or "",
            entity_data.get("name") or "",
            entity_data.get("device_name") or "",
            entity_data.get("area_name") or "",
            entity_data.get("integration_name") or "",
        ]
        
        # Check main fields
        for field in search_fields:
            if search_lower in field.lower():
                return True
                
        # Check label names
        for label in entity_data.get("labels", []):
            if label.get("label_name") and search_lower in label["label_name"].lower():
                return True
                
        return False

    def _get_entity_data(self, entity_entry: er.RegistryEntry) -> dict[str, Any]:
        """Get comprehensive entity data."""
        data: dict[str, Any] = {}
        
        # Entity name (display name)
        data["name"] = entity_entry.name or entity_entry.entity_id.split(".", 1)[1].replace("_", " ").title()
        
        # Device information
        device_registry = dr.async_get(self.hass)
        if entity_entry.device_id and (device := device_registry.async_get(entity_entry.device_id)):
            data["device_id"] = device.id
            data["device_name"] = device.name_by_user or device.name
        else:
            data["device_id"] = None
            data["device_name"] = None
            
        # Area information
        area_registry = ar.async_get(self.hass)
        area_id = entity_entry.area_id
        if not area_id and entity_entry.device_id:
            # Get area from device if entity doesn't have one directly
            device = device_registry.async_get(entity_entry.device_id)
            if device:
                area_id = device.area_id
                
        if area_id and (area := area_registry.async_get_area(area_id)):
            data["area_id"] = area.id
            data["area_name"] = area.name
        else:
            data["area_id"] = None
            data["area_name"] = None
            
        # Integration information
        data["integration_slug"] = entity_entry.platform
        data["integration_name"] = self._get_integration_name(entity_entry)
            
        # Status information
        data["status"] = self._get_status_info(entity_entry)
        
        # Icon (always from registry)
        data["icon"] = entity_entry.icon
        
        # Created/Modified timestamps
        data["created"] = self._format_timestamp(getattr(entity_entry, "created_at", None))
        data["modified"] = self._format_timestamp(getattr(entity_entry, "modified_at", None))
            
        # Labels information
        data["labels"] = self._get_entity_labels(entity_entry)
                
        return data

    def _get_integration_name(self, entity_entry: er.RegistryEntry) -> str | None:
        """Get integration name from config entry."""
        if not entity_entry.config_entry_id:
            return None
            
        config_entries = self.hass.config_entries
        if hasattr(config_entries, "async_get_entry"):
            config_entry = config_entries.async_get_entry(entity_entry.config_entry_id)
        else:
            # Fallback to private access if public method not available
            config_entry = getattr(config_entries, "_entries", {}).get(entity_entry.config_entry_id)
            
        return config_entry.title if config_entry else None

    def _get_status_info(self, entity_entry: er.RegistryEntry) -> dict[str, Any]:
        """Get status information for entity."""
        state = self.hass.states.get(entity_entry.entity_id)
        
        return {
            "disabled_by": entity_entry.disabled_by,
            "hidden_by": entity_entry.hidden_by,
            "available": state is not None and state.state not in ("unavailable", "unknown"),
            "unknown": state is not None and state.state == "unknown",
            "unmanageable": not entity_entry.unique_id,
            "not_provided": (
                state is None 
                and entity_entry.platform is not None 
                and entity_entry.config_entry_id is not None
            ),
        }

    def _format_timestamp(self, timestamp: Any) -> str | None:
        """Format timestamp to ISO string."""
        if not timestamp:
            return None
            
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        return timestamp

    def _get_entity_labels(self, entity_entry: er.RegistryEntry) -> list[dict[str, str]]:
        """Get labels for entity."""
        if not hasattr(lr, "async_get") or not hasattr(entity_entry, "labels") or not entity_entry.labels:
            return []
            
        try:
            label_registry = lr.async_get(self.hass)
            return [
                {"label_id": label.label_id, "label_name": label.name}
                for label_id in entity_entry.labels
                if (label := label_registry.async_get_label(label_id))
            ]
        except AttributeError:
            return []  # Labels not supported

    def _entity_matches_filters(
        self,
        entity_entry: er.RegistryEntry,
        entity_data: dict[str, Any],
        filters: dict[str, Any],
    ) -> bool:
        """Check if entity matches all filter criteria."""
        # Check basic filters
        if not self._matches_basic_filters(entity_entry, entity_data, filters):
            return False
            
        # Check status filter (more complex)
        return self._matches_status_filter(entity_data, filters.get("status", []))
        
    def _matches_basic_filters(
        self,
        entity_entry: er.RegistryEntry,
        entity_data: dict[str, Any],
        filters: dict[str, Any],
    ) -> bool:
        """Check basic filter criteria (areas, devices, domains, integrations, labels)."""
        # Areas filter (OR within type)
        areas = filters.get("areas")
        if areas and entity_data.get("area_id") not in areas:
            return False

        # Devices filter (OR within type)
        devices = filters.get("devices")
        if devices and entity_data.get("device_id") not in devices:
            return False

        # Domains filter (OR within type)
        if domains := filters.get("domains"):
            entity_domain = entity_entry.entity_id.split(".", 1)[0]
            if entity_domain not in domains:
                return False

        # Integrations filter (OR within type)
        integrations = filters.get("integrations")
        if integrations and entity_entry.platform not in integrations:
            return False
                
        # Labels filter (OR within type)
        if labels_filter := filters.get("labels"):
            entity_label_ids = {label["label_id"] for label in entity_data.get("labels", [])}
            if not entity_label_ids.intersection(labels_filter):
                return False
                
        return True
        
    def _matches_status_filter(self, entity_data: dict[str, Any], status_filters: list[str]) -> bool:
        """Check if entity matches status filter criteria."""
        if not status_filters:
            return True
            
        entity_status = entity_data["status"]
        
        # Define status check mapping
        status_checks = {
            "available": lambda s: s["available"],
            "unavailable": lambda s: not s["available"],
            "enabled": lambda s: not s["disabled_by"],
            "disabled": lambda s: bool(s["disabled_by"]),
            "visible": lambda s: not s["hidden_by"],
            "hidden": lambda s: bool(s["hidden_by"]),
            "unmanageable": lambda s: s["unmanageable"],
            "not_provided": lambda s: s["not_provided"],
        }
        
        # Check if any of the selected status filters match (OR logic)
        return any(
            status_checks.get(status_filter, lambda _: False)(entity_status)
            for status_filter in status_filters
        )

    async def async_handle_service(self, call: ServiceCall) -> ServiceResponse:
        """Handle the service call."""
        # Parse and validate input parameters
        filters, values, limit = self._parse_service_call(call)
        
        # Get matching entities
        matching_entities = self._find_matching_entities(filters, values, limit)
        
        # Sort and return results
        return self._format_response(matching_entities)

    def _parse_service_call(self, call: ServiceCall) -> tuple[dict[str, Any], list[str], int]:
        """Parse and validate service call parameters."""
        search = call.data.get("search", "")
        areas = call.data.get("areas", [])
        devices = call.data.get("devices", [])
        domains = call.data.get("domains", [])
        integrations = call.data.get("integrations", [])
        status = call.data.get("status", [])
        labels = call.data.get("labels", [])
        values = call.data.get("values", [])
        limit = call.data.get("limit")
        
        # Apply safety cap
        if limit is None or limit > MAX_ENTITIES_LIMIT:
            limit = MAX_ENTITIES_LIMIT
            
        filters = {
            "search": search,
            "areas": areas,
            "devices": devices,
            "domains": domains,
            "integrations": integrations,
            "status": status,
            "labels": labels,
        }
        
        return filters, values, limit

    def _find_matching_entities(
        self, 
        filters: dict[str, Any], 
        values: list[str], 
        limit: int,
    ) -> list[str | dict[str, Any]]:
        """Find entities matching the filter criteria."""
        entity_registry = er.async_get(self.hass)
        matching_entities = []
        
        for entity_entry in entity_registry.entities.values():
            # Get comprehensive entity data
            entity_data = self._get_entity_data(entity_entry)
            
            # Check search filter
            if not self._matches_search(entity_entry, filters.get("search", ""), entity_data):
                continue
                
            # Check all other filters
            if not self._entity_matches_filters(entity_entry, entity_data, filters):
                continue
                
            # Add to results
            if values:
                # Include requested values
                result = self._build_entity_result(entity_entry, entity_data, values)
                matching_entities.append(result)
            else:
                # Minimal format - just entity IDs
                matching_entities.append(entity_entry.entity_id)
                
            # Apply limit
            if len(matching_entities) >= limit:
                break
                
        return matching_entities

    def _build_entity_result(
        self,
        entity_entry: er.RegistryEntry,
        entity_data: dict[str, Any],
        values: list[str],
    ) -> dict[str, Any]:
        """Build entity result with requested values."""
        result = {"entity_id": entity_entry.entity_id}
        
        # Value mapping for cleaner code
        value_mapping = {
            "name": lambda: entity_data["name"],
            "device": lambda: self._add_device_info(result, entity_data),
            "area": lambda: self._add_area_info(result, entity_data),
            "integration": lambda: self._add_integration_info(result, entity_data),
            "status": lambda: entity_data["status"],
            "icon": lambda: entity_data["icon"],
            "created": lambda: entity_data["created"],
            "modified": lambda: entity_data["modified"],
            "labels": lambda: entity_data["labels"],
        }
        
        for value in values:
            if value in value_mapping:
                if value in ("device", "area", "integration"):
                    value_mapping[value]()  # These modify result in-place
                else:
                    result[value] = value_mapping[value]()
                
        return result

    def _add_device_info(self, result: dict[str, Any], entity_data: dict[str, Any]) -> None:
        """Add device information to result."""
        result["device_id"] = entity_data["device_id"]
        result["device_name"] = entity_data["device_name"]

    def _add_area_info(self, result: dict[str, Any], entity_data: dict[str, Any]) -> None:
        """Add area information to result."""
        result["area_id"] = entity_data["area_id"]
        result["area_name"] = entity_data["area_name"]

    def _add_integration_info(self, result: dict[str, Any], entity_data: dict[str, Any]) -> None:
        """Add integration information to result."""
        result["integration_slug"] = entity_data["integration_slug"]
        result["integration_name"] = entity_data["integration_name"]

    def _format_response(self, matching_entities: list[str | dict[str, Any]]) -> ServiceResponse:
        """Format the final service response."""
        # Stable sort by entity_id (for string values) or by entity_id key (for dict values)
        if matching_entities and isinstance(matching_entities[0], dict):
            # Sort dictionaries by entity_id key
            dict_entities = [e for e in matching_entities if isinstance(e, dict)]
            dict_entities.sort(key=lambda entity: str(entity.get("entity_id", "")))
            matching_entities[:] = dict_entities
        else:
            # Sort strings directly
            string_entities = [e for e in matching_entities if isinstance(e, str)]
            string_entities.sort()
            matching_entities[:] = string_entities
            
        return {
            "count": len(matching_entities),
            "entities": matching_entities,
        }
>>>>>>> 3f18a4f (Implement list_filtered_entities action)
