"""Tests for Cloudflare backoff and ban-prevention logic."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from custom_components.keyforsteam.sensor import KeyforSteamDataUpdateCoordinator
from custom_components.keyforsteam.const import CLOUDFLARE_BACKOFF_HOURS, MAX_RETRIES


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    with patch("homeassistant.helpers.frame.report_usage"):
        return KeyforSteamDataUpdateCoordinator(mock_hass, mock_config_entry)


# ---------------------------------------------------------------------------
# Backoff guard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backoff_skips_request_when_active(coordinator):
    """If _backoff_until is in the future and we have cached data, return
    cached data immediately without making a network request."""
    coordinator._backoff_until = datetime.now() + timedelta(hours=3)
    cached = {"low_price": 9.99, "name": "Test Game"}
    coordinator.data = cached

    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession"
    ) as mock_session:
        result = await coordinator._async_update_data()

    # No HTTP request should have been made
    mock_session.assert_not_called()
    assert result == cached


@pytest.mark.asyncio
async def test_backoff_raises_when_active_and_no_cached_data(coordinator):
    """If _backoff_until is in the future and there is no cached data,
    raise UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coordinator._backoff_until = datetime.now() + timedelta(hours=3)
    coordinator.data = None

    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession"):
        with pytest.raises(UpdateFailed, match="Cloudflare backoff active"):
            await coordinator._async_update_data()


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
async def test_cloudflare_block_200_triggers_backoff_and_returns_cache(coordinator):
    """A Cloudflare challenge page returned with HTTP 200 should trigger the
    backoff, stop retrying immediately, and return cached data."""
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
    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        result = await coordinator._async_update_data()

    # Backoff must be active
    assert coordinator._backoff_until is not None
    assert coordinator._backoff_until > datetime.now()

    # Cached data must be returned so entities stay available
    assert result == coordinator.data

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
    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        result = await coordinator._async_update_data()

    # Backoff must be active
    assert coordinator._backoff_until is not None
    # Should have stopped after 1 attempt
    assert mock_session.get.call_count == 1
    # Cached data returned
    assert result == coordinator.data


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

    from homeassistant.helpers.update_coordinator import UpdateFailed

    coordinator._handle_api_repair = AsyncMock()
    with patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    # Should have tried MAX_RETRIES times
    assert mock_session.get.call_count == MAX_RETRIES
    # No Cloudflare backoff should be set for a generic block
    assert coordinator._backoff_until is None


# ---------------------------------------------------------------------------
# Fault-tolerant first_refresh test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_succeeds_even_if_first_refresh_fails(
    mock_hass, mock_config_entry
):
    """async_setup_entry should return True even when the first refresh fails,
    so that HA does not immediately retry setup and trigger more requests."""
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

        result = await async_setup_entry(mock_hass, mock_config_entry)

    # Entry setup must succeed despite the failed first refresh
    assert result is True
    from custom_components.keyforsteam.const import DOMAIN

    assert DOMAIN in mock_hass.data
    assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
