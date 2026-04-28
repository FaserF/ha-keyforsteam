import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from aioresponses import aioresponses
from custom_components.keyforsteam.config_flow import (
    KeyforSteamConfigFlow,
    KeyforSteamOptionsFlow,
)
from custom_components.keyforsteam.const import GAMES_CATALOG_URL


@pytest.fixture
def flow():
    flow = KeyforSteamConfigFlow()
    flow.hass = MagicMock()
    return flow


@pytest.mark.asyncio
async def test_fetch_games_catalog(flow):
    """Test fetching the games catalog."""
    with aioresponses() as m:
        m.get(
            GAMES_CATALOG_URL,
            payload={"status": "success", "games": [{"id": 1, "name": "Game A"}]},
        )
        games = await flow._fetch_games_catalog()
        assert len(games) == 1
        assert games[0]["name"] == "Game A"


@pytest.mark.asyncio
async def test_search_games(flow):
    """Test searching games with prioritization."""
    flow._games_cache = [
        {"id": 1, "name": "Test Game"},
        {"id": 2, "name": "Test Game DLC"},
        {"id": 3, "name": "Another Game"},
    ]

    results = flow._search_games("Test")
    assert len(results) == 2
    assert results[0]["id"] == 1  # Base game should be prioritized over DLC


def test_create_slug(flow):
    """Test slug creation."""
    assert flow._create_slug("Test Game 2!") == "test-game-2"


@pytest.mark.asyncio
async def test_async_step_user(flow):
    """Test the user step."""
    with patch.object(flow, "_fetch_games_catalog", AsyncMock(return_value=[])):
        # Form display
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"

        # Search triggered
        flow._games_cache = [{"id": 1, "name": "Test Game"}]
        result = await flow.async_step_user(user_input={"game_query": "Test"})
        assert result["type"] == "form"  # Actually it forwards to async_step_select
        assert len(flow._search_results) == 1


@pytest.mark.asyncio
async def test_async_step_select(flow):
    """Test the select step."""
    flow._search_results = [{"id": 1, "name": "Test Game"}]

    with (
        patch.object(flow, "async_set_unique_id", AsyncMock()),
        patch.object(flow, "_abort_if_unique_id_configured", MagicMock()),
    ):
        result = await flow.async_step_select(
            user_input={
                "game_selection": "1",
                "currency": "eur",
                "allow_accounts": False,
                "payment_method": "lowest_fees",
            }
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Test Game"


@pytest.mark.asyncio
async def test_options_flow():
    """Test options flow."""
    entry = MagicMock()
    entry.data = {"currency": "eur", "allow_accounts": False}
    entry.options = {}

    flow = KeyforSteamOptionsFlow(entry)
    flow.hass = MagicMock()

    result = await flow.async_step_init(
        user_input={"currency": "usd", "allow_accounts": True}
    )
    assert result["type"] == "create_entry"
