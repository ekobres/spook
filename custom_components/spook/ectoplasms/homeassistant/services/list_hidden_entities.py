"""Spook - Your homie."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.homeassistant import DOMAIN
from homeassistant.core import ServiceResponse, SupportsResponse
from homeassistant.helpers import entity_registry as er

from ....services import AbstractSpookService

if TYPE_CHECKING:
    from homeassistant.core import ServiceCall


class SpookService(AbstractSpookService):
    """Home Assistant Core integration action to list all hidden entities."""

    domain = DOMAIN
    service = "list_hidden_entities"
    supports_response = SupportsResponse.ONLY

    async def async_handle_service(self, call: ServiceCall) -> ServiceResponse:  # noqa: ARG002
        """Handle the service call."""
        registry = er.async_get(self.hass)
        entities = [
            entry.entity_id
            for entry in registry.entities.values()
            if entry.hidden_by is not None
        ]
        if call.return_response:
            return {
                "count": len(entities),
                "entities": entities,
            }
        return None