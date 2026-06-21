import pytest
from unittest.mock import MagicMock
from custom_components.keyforsteam.sensor import (
    KeyforSteamDataUpdateCoordinator,
    async_setup_entry,
    KeyforSteamPriceSensor,
    KeyforSteamRatingSensor,
    KeyforSteamOfferCountSensor,
)
from custom_components.keyforsteam.const import DOMAIN


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
