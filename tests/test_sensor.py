from unittest.mock import MagicMock, patch

import pytest

from custom_components.keyforsteam.const import DOMAIN
from custom_components.keyforsteam.sensor import (
    KeyforSteamDataUpdateCoordinator,
    KeyforSteamOfferCountSensor,
    KeyforSteamPriceSensor,
    KeyforSteamRatingSensor,
    async_setup_entry,
)


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    from unittest.mock import patch

    with patch("homeassistant.helpers.frame.report_usage"):
        return KeyforSteamDataUpdateCoordinator(mock_hass, mock_config_entry)


def test_build_product_url(coordinator):
    """Test URL building."""
    assert "test-game" in coordinator._build_product_url()

    coordinator.product_slug = ""
    coordinator.product_name = "Test Game Name"
    assert "test-game-name" in coordinator._build_product_url()


def test_extract_json_ld(coordinator):
    """Test JSON-LD extraction."""
    html = '<script type="application/ld+json">{"@type": "Product", "name": "Test"}</script>'
    data = coordinator._extract_json_ld(html)
    assert data["name"] == "Test"


def test_parse_offers(coordinator):
    """Test offer parsing from JSON-LD."""
    product_data = {
        "name": "Test Game",
        "image": "img_url",
        "offers": {
            "@type": "AggregateOffer",
            "lowPrice": 10.0,
            "highPrice": 20.0,
            "priceCurrency": "EUR",
            "offerCount": 5,
            "offers": [{"price": 10.0, "seller": "Seller A"}],
        },
    }
    result = coordinator._parse_offers(product_data, "http://url")
    assert result["low_price"] == 10.0
    assert result["image"] == "img_url"


def test_extract_game_page_trans(coordinator):
    """Test gamePageTrans extraction."""
    html = '<script>var gamePageTrans = {"prices": []};</script>'
    data = coordinator._extract_game_page_trans(html)
    assert "prices" in data


def test_parse_game_page_trans(coordinator):
    """Test gamePageTrans parsing."""
    game_data = {
        "prices": [
            {
                "price": 12.0,
                "priceCard": 11.0,
                "pricePaypal": 11.5,
                "merchant": 1,
                "dispo": 1,
            }
        ],
        "merchants": {"1": {"name": "Seller A"}},
    }
    result = coordinator._parse_game_page_trans(game_data, "http://url")
    assert result["low_price"] == 11.0  # Card is min for lowest_fees


@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config_entry):
    """Test sensor setup entry."""
    coordinator = MagicMock()
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}

    mock_add_entities = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()


def test_price_sensor(coordinator):
    """Test price sensor."""
    sensor = KeyforSteamPriceSensor(coordinator, MagicMock())
    coordinator.data = {
        "low_price": 15.0,
        "currency": "EUR",
        "name": "Test",
        "offers": [{"seller": "Seller A", "price": 15.0}],
    }
    coordinator.last_update_success = True

    assert sensor.native_value == 15.0
    assert sensor.native_unit_of_measurement == "€"
    assert sensor.available is True
    assert sensor.extra_state_attributes["low_price"] == 15.0


def test_rating_sensor(coordinator):
    """Test rating sensor."""
    sensor = KeyforSteamRatingSensor(coordinator, MagicMock())
    coordinator.data = {"rating": {"value": 4.5, "count": 100}}
    assert sensor.native_value == 4.5


def test_offer_count_sensor(coordinator):
    """Test offer count sensor."""
    sensor = KeyforSteamOfferCountSensor(coordinator, MagicMock())
    coordinator.data = {"offer_count": 10}
    assert sensor.native_value == 10


@pytest.mark.asyncio
async def test_coordinator_cache_age_limit(coordinator):
    """Test that disk cache is only used if within 24 hours."""
    from datetime import datetime, timedelta
    from unittest.mock import AsyncMock

    from homeassistant.helpers.update_coordinator import UpdateFailed

    # Cache is 25 hours old -> should be ignored, fetch attempted and fail with UpdateFailed
    coordinator.data = None
    coordinator._handle_api_repair = AsyncMock()
    old_time = (datetime.now() - timedelta(hours=25)).isoformat()
    coordinator._store.async_load = AsyncMock(
        return_value={"data": {"low_price": 5.0}, "timestamp": old_time}
    )

    with (
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession"
        ) as mock_session,
        pytest.raises(UpdateFailed),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("Network error"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.get.return_value = mock_ctx
        await coordinator._async_update_data()

    # Cache was 2 hours old -> should be used immediately
    coordinator.data = None
    recent_time = (datetime.now() - timedelta(hours=2)).isoformat()
    coordinator._store.async_load = AsyncMock(
        return_value={"data": {"low_price": 8.0}, "timestamp": recent_time}
    )
    result = await coordinator._async_update_data()
    assert result == {"low_price": 8.0}
