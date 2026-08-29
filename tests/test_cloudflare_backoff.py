"""Tests for Cloudflare backoff and ban-prevention logic."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.keyforsteam.const import CLOUDFLARE_BACKOFF_HOURS, MAX_RETRIES
from custom_components.keyforsteam.sensor import KeyforSteamDataUpdateCoordinator


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    with patch("homeassistant.helpers.frame.report_usage"):
        return KeyforSteamDataUpdateCoordinator(mock_hass, mock_config_entry)


# ---------------------------------------------------------------------------
# Backoff guard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backoff_raises_when_active(coordinator):
    """If _backoff_until is in the future, raise UpdateFailed without making
    a network request."""
    coordinator._backoff_until = datetime.now() + timedelta(hours=3)
    coordinator.data = {"low_price": 9.99, "name": "Test Game"}

    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession"
    ) as mock_session:
        with pytest.raises(UpdateFailed, match="Cloudflare backoff active"):
            await coordinator._async_update_data()

    # No HTTP request should have been made
    mock_session.assert_not_called()


def test_set_cloudflare_backoff(coordinator):
    """_set_cloudflare_backoff should set _backoff_until approximately
    CLOUDFLARE_BACKOFF_HOURS in the future."""
    assert coordinator._backoff_until is None
    before = datetime.now()
    coordinator._set_cloudflare_backoff()
    after = datetime.now()

    assert coordinator._backoff_until is not None
    expected_low = before + timedelta(hours=CLOUDFLARE_BACKOFF_HOURS)
    expected_high = after + timedelta(hours=CLOUDFLARE_BACKOFF_HOURS)
    assert expected_low <= coordinator._backoff_until <= expected_high


@pytest.mark.asyncio
async def test_cloudflare_block_200_triggers_backoff(coordinator):
    """A Cloudflare challenge page returned with HTTP 200 should trigger the
    backoff, stop retrying immediately, and raise UpdateFailed."""
    coordinator.data = {"low_price": 7.50, "name": "Cached Game"}

    cloudflare_html = (
        "<!doctype html><html><body>"
        "<h1>Just a moment...</h1>"
        "<div id='cf-browser-verification'>Checking your browser...</div>"
        "</body></html>"
    )

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_response.raise_for_status = MagicMock()
    mock_response.text = AsyncMock(return_value=cloudflare_html)

    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_ctx)

    coordinator._handle_api_repair = AsyncMock()
    with (
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    # Backoff must be active
    assert coordinator._backoff_until is not None
    assert coordinator._backoff_until > datetime.now()

    # Only one request attempt should have been made (break after first block)
    assert mock_session.get.call_count == 1


@pytest.mark.asyncio
async def test_cloudflare_block_403_triggers_backoff(coordinator):
    """A 403 response containing a Cloudflare marker should trigger backoff
    and break immediately rather than retrying."""
    coordinator.data = {"low_price": 5.00, "name": "Blocked Game"}

    cloudflare_html = "<html><body>cloudflare error ray id: abc123</body></html>"

    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_response.text = AsyncMock(return_value=cloudflare_html)

    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_ctx)

    coordinator._handle_api_repair = AsyncMock()
    with (
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    # Backoff must be active
    assert coordinator._backoff_until is not None
    # Should have stopped after 1 attempt
    assert mock_session.get.call_count == 1


@pytest.mark.asyncio
async def test_non_cloudflare_403_retries(coordinator):
    """A 403 response without Cloudflare markers should continue retrying
    (up to MAX_RETRIES) rather than breaking immediately."""
    coordinator.data = None

    generic_403_html = "<html><body>Access denied by firewall rule.</body></html>"

    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_response.text = AsyncMock(return_value=generic_403_html)

    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_ctx)

    coordinator._handle_api_repair = AsyncMock()
    with (
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    # Should have tried MAX_RETRIES times
    assert mock_session.get.call_count == MAX_RETRIES
    # No Cloudflare backoff should be set for a generic block
    assert coordinator._backoff_until is None


# ---------------------------------------------------------------------------
# First refresh error propagation test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_raises_if_first_refresh_fails(mock_hass, mock_config_entry):
    """async_setup_entry should raise when first refresh fails so HA handles retry."""
    with patch("homeassistant.helpers.frame.report_usage"):
        from custom_components.keyforsteam import async_setup_entry

    with patch(
        "custom_components.keyforsteam.sensor.KeyforSteamDataUpdateCoordinator"
    ) as mock_coord_class:
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock(
            side_effect=Exception("Cloudflare block!")
        )
        mock_coord.product_name = "Test Game"
        mock_coord.product_id = "12345"
        mock_coord_class.return_value = mock_coord

        with pytest.raises(Exception, match="Cloudflare block!"):
            await async_setup_entry(mock_hass, mock_config_entry)
