"""Spook - Your homie."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.homeassistant import DOMAIN
from homeassistant.core import Event, ServiceResponse, SupportsResponse, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)

from ....const import LOGGER
from ....services import AbstractSpookService

if TYPE_CHECKING:
    from homeassistant.core import ServiceCall

# Event constants for registry updates
from homeassistant.helpers.area_registry import EVENT_AREA_REGISTRY_UPDATED
from homeassistant.helpers.device_registry import EVENT_DEVICE_REGISTRY_UPDATED
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

try:
    from homeassistant.helpers.label_registry import EVENT_LABEL_REGISTRY_UPDATED
except ImportError:
    # Fallback for older HA versions without label support
    EVENT_LABEL_REGISTRY_UPDATED = "label_registry_updated"

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
        self._listeners_setup = False

    def _setup_event_listeners(self) -> None:
        """Set up event listeners for registry updates."""
        if self._listeners_setup:
            return

        self.hass.bus.async_listen(
            EVENT_AREA_REGISTRY_UPDATED,
            self._handle_registry_updated,
        )
        self.hass.bus.async_listen(
            EVENT_DEVICE_REGISTRY_UPDATED,
            self._handle_registry_updated,
        )
        self.hass.bus.async_listen(
            EVENT_ENTITY_REGISTRY_UPDATED,
            self._handle_registry_updated,
        )

        # Feature detect label registry support
        if hasattr(lr, "async_get"):
            self.hass.bus.async_listen(
                EVENT_LABEL_REGISTRY_UPDATED,
                self._handle_registry_updated,
            )

        self._listeners_setup = True

    @callback
    def _handle_registry_updated(self, _event: Event) -> None:
        """Handle registry update events."""
        # No caching in this implementation, so nothing to invalidate

    def _get_domains_options(self) -> list[dict[str, str]]:
        """Get domains selector options with safe registry access."""
        LOGGER.debug("Getting domains options - hass available: %s", self.hass is not None)
        try:
            if hasattr(er, "async_get") and self.hass is not None:
                entity_registry = er.async_get(self.hass)
                LOGGER.debug("Entity registry obtained: %s", entity_registry is not None)
                if entity_registry and hasattr(entity_registry, "entities"):
                    domains = set()
                    for entry in entity_registry.entities.values():
                        domain = entry.entity_id.split(".", 1)[0]
                        domains.add(domain)
                    
                    options = [
                        {"value": domain, "label": domain.replace("_", " ").title()}
                        for domain in sorted(domains)
                    ]
                    LOGGER.debug("Generated %d domain options: %s", len(options), [opt["value"] for opt in options[:5]])
                    return options
        except (AttributeError, RuntimeError, KeyError) as e:
            # Registry not ready or not available
            LOGGER.debug("Exception getting domains options: %s", e)
        
        # Fallback to common domains if registry not available
        fallback_options = [
            {"value": "light", "label": "Light"},
            {"value": "switch", "label": "Switch"},
            {"value": "sensor", "label": "Sensor"},
            {"value": "binary_sensor", "label": "Binary Sensor"},
            {"value": "climate", "label": "Climate"},
            {"value": "cover", "label": "Cover"},
            {"value": "fan", "label": "Fan"},
            {"value": "lock", "label": "Lock"},
            {"value": "media_player", "label": "Media Player"},
            {"value": "vacuum", "label": "Vacuum"},
        ]
        LOGGER.debug("Using fallback domains options: %d items", len(fallback_options))
        return fallback_options

    def _get_integrations_options(self) -> list[dict[str, str]]:
        """Get integrations selector options with safe registry access."""
        LOGGER.debug("Getting integrations options - hass available: %s", self.hass is not None)
        try:
            if hasattr(er, "async_get") and self.hass is not None:
                entity_registry = er.async_get(self.hass)
                LOGGER.debug("Entity registry obtained for integrations: %s", entity_registry is not None)
                if entity_registry and hasattr(entity_registry, "entities"):
                    integrations = set()
                    for entry in entity_registry.entities.values():
                        if entry.platform:
                            integrations.add(entry.platform)
                    
                    options = [
                        {"value": integration, "label": integration.replace("_", " ").title()}
                        for integration in sorted(integrations)
                    ]
                    LOGGER.debug("Generated %d integration options: %s", len(options), [opt["value"] for opt in options[:5]])
                    return options
        except (AttributeError, RuntimeError, KeyError) as e:
            # Registry not ready or not available
            LOGGER.debug("Exception getting integrations options: %s", e)
        
        LOGGER.debug("Using empty integrations options")
        return []

    @property
    def fields(self) -> dict[str, Any]:
        """Return the fields for this service with dynamic options populated."""
        LOGGER.debug("Fields property accessed for list_filtered_entities service")
        self._setup_event_listeners()

        # Start with base field definitions (which match our YAML structure)
        fields = {
            "search": {
                "selector": {"text": {}},
            },
            "areas": {
                "selector": {"area": {"multiple": True}},
            },
            "devices": {
                "selector": {"device": {"multiple": True}},
            },
            "domains": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "custom_value": True,
                        "mode": "dropdown",
                        "options": [],  # Will be populated dynamically below
                    }
                }
            },
            "integrations": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "custom_value": True,
                        "mode": "dropdown",
                        "options": [],  # Will be populated dynamically below
                    }
                }
            },
            "status": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "mode": "dropdown",
                        "options": [
                            {"value": status, "label": status.replace("_", " ").title()}
                            for status in STATUS_OPTIONS
                        ],
                    }
                }
            },
            "label_id": {
                "selector": {"label": {"multiple": True}},
            },
            "values": {
                "selector": {
                    "select": {
                        "multiple": True,
                        "mode": "dropdown",
                        "label": "Select information to include",
                        "options": [
                            {"value": value, "label": value.replace("_", " ").title()}
                            for value in VALUES_OPTIONS
                        ],
                    }
                }
            },
            "limit": {
                "default": 50000,
                "selector": {"number": {"min": 1, "max": 50000}},
            },
        }

        # Populate dynamic options
        domains_options = self._get_domains_options()
        integrations_options = self._get_integrations_options()
        
        fields["domains"]["selector"]["select"]["options"] = domains_options
        fields["integrations"]["selector"]["select"]["options"] = integrations_options
        
        LOGGER.debug("Built field options: domains=%d, integrations=%d", len(domains_options), len(integrations_options))

        return fields

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
        label_id = call.data.get("label_id", [])
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
            "labels": label_id,
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
