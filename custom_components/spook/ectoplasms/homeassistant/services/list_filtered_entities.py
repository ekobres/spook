"""Spook - Your homie."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.homeassistant import DOMAIN
from homeassistant.core import ServiceResponse, SupportsResponse
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)

from ....services import AbstractSpookService

if TYPE_CHECKING:
    from homeassistant.core import ServiceCall

# Safety limit for number of entities to return
MAX_ENTITIES_LIMIT = 50000


class SpookService(AbstractSpookService):
    """Home Assistant service to list filtered entities."""

    domain = DOMAIN
    service = "list_filtered_entities"
    supports_response = SupportsResponse.ONLY

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

        # Entity name (only if original_name exists in registry)
        if hasattr(entity_entry, "original_name") and entity_entry.original_name:
            data["name"] = entity_entry.original_name

        # Device information (every entity has a device_id)
        data["device_id"] = entity_entry.device_id
        device_registry = dr.async_get(self.hass)
        if (device := device_registry.async_get(entity_entry.device_id)) and device.name:
            data["device_name"] = device.name

        # Area information (only if area exists)
        area_registry = ar.async_get(self.hass)
        area_id = entity_entry.area_id
        if not area_id and entity_entry.device_id:
            # Get area from device if entity doesn't have one directly
            device_registry = dr.async_get(self.hass)
            if device := device_registry.async_get(entity_entry.device_id):
                area_id = device.area_id

        if area_id and (area := area_registry.async_get_area(area_id)):
            data["area_id"] = area.id
            data["area_name"] = area.name

        # Integration information
        data["integration_name"] = self._get_integration_name(entity_entry)

        # Status information
        data["status"] = self._get_status_info(entity_entry)

        # Icon (user-defined or integration default)
        data["icon"] = self._get_entity_icon(entity_entry)

        # Created/Modified timestamps
        created_at = getattr(entity_entry, "created_at", None)
        data["created"] = created_at.isoformat() if isinstance(created_at, datetime) else created_at
        
        modified_at = getattr(entity_entry, "modified_at", None)
        data["modified"] = modified_at.isoformat() if isinstance(modified_at, datetime) else modified_at

        # Labels information
        data["labels"] = self._get_entity_labels(entity_entry)

        return data

    def _get_entity_icon(self, entity_entry: er.RegistryEntry) -> str | None:
        """Get entity icon from registry (user-defined or integration default)."""
        # Check user-defined icon first, then integration's original icon
        return entity_entry.icon or getattr(entity_entry, "original_icon", None)

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
        
        status = {}
        
        # Only include keys with truthy values
        if entity_entry.disabled_by:
            status["disabled_by"] = entity_entry.disabled_by
            
        if entity_entry.hidden_by:
            status["hidden_by"] = entity_entry.hidden_by
            
        if state is not None and state.state not in ("unavailable", "unknown"):
            status["available"] = True
            
        if state is not None and state.state == "unknown":
            status["unknown"] = True
            
        # Unmanageable: entities without config_entry_id (cannot be managed from UI)
        if entity_entry.config_entry_id is None:
            status["unmanageable"] = True

        return status

    def _get_entity_labels(self, entity_entry: er.RegistryEntry) -> list[dict[str, str]]:
        """Get labels for entity (only if labels exist and are supported)."""
        if (hasattr(lr, "async_get") and
            hasattr(entity_entry, "labels") and
            entity_entry.labels):
            try:
                label_registry = lr.async_get(self.hass)
                return [
                    {"label_id": label.label_id, "label_name": label.name}
                    for label_id in entity_entry.labels
                    if (label := label_registry.async_get_label(label_id))
                ]
            except AttributeError:
                pass
        return []

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
            "available": lambda s: s.get("available", False),
            "unavailable": lambda s: not s.get("available", False),
            "enabled": lambda s: not s.get("disabled_by"),
            "disabled": lambda s: bool(s.get("disabled_by")),
            "visible": lambda s: not s.get("hidden_by"),
            "hidden": lambda s: bool(s.get("hidden_by")),
            "unmanageable": lambda s: s.get("unmanageable", False),
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

        # Value mapping - directly add data that exists
        value_mapping = {
            "name": lambda: entity_data["name"],
            "device": lambda: (entity_data.get("device_id") and {
                "device_id": entity_data["device_id"],
                "device_name": entity_data["device_name"]
            }),
            "area": lambda: (entity_data.get("area_id") and {
                "area_id": entity_data["area_id"],
                "area_name": entity_data["area_name"]
            }),
            "integration": lambda: {
                "integration_name": entity_data["integration_name"]
            },
            "status": lambda: entity_data["status"],
            "icon": lambda: entity_data["icon"],
            "created": lambda: entity_data["created"],
            "modified": lambda: entity_data["modified"],
            "labels": lambda: entity_data["labels"],
        }

        for value in values:
            if value in value_mapping:
                data = value_mapping[value]()
                if data is not None:  # Allow empty lists, False, etc., but not None
                    if isinstance(data, dict):
                        result.update(data)  # Merge dict data (device, area)
                    else:
                        result[value] = data  # Single value

        return result

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
