# KeyForSteam Home Assistant Integration 🔑🎮

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Ruff](https://github.com/FaserF/ha-keyforsteam/actions/workflows/lint.yaml/badge.svg)](https://github.com/FaserF/ha-keyforsteam/actions/workflows/lint.yaml)
[![Hassfest](https://github.com/FaserF/ha-keyforsteam/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/FaserF/ha-keyforsteam/actions/workflows/hassfest.yaml)

Track game prices from **KeyForSteam** (AllKeyShop) directly in Home Assistant. Get real-time updates on the lowest prices, best deals, and seller information for your favorite games.

---

## Features ✨

- **Game Search**: Easily find and add games using the built-in search with autocomplete.
- **Price Tracking**: Monitor the lowest available price for any game in EUR, USD, or GBP.
- **Detailed Attributes**: Access seller names, all available offers, product URLs, and ratings.
- **Price Alerts**: Built-in binary sensor for configurable price thresholds.
- **HA Repairs Service**: Automatic notification if the API changes or data cannot be fetched for 24 hours.
- **Diagnostics**: Detailed diagnostic information for easier troubleshooting.

---

## Installation 🛠️

### 1. Using HACS (Recommended)
1. Open **HACS**.
2. Go to **Integrations**.
3. Click the three dots in the top right and select **Custom repositories**.
4. Add `https://github.com/FaserF/ha-keyforsteam` (Category: Integration).
5. Search for **KeyForSteam** and click **Download**.

### 2. Manual Installation
1. Download the latest [release](https://github.com/FaserF/ha-keyforsteam/releases/latest).
2. Copy the `custom_components/keyforsteam` folder to your Home Assistant `<config_dir>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration ⚙️

1. Navigate to **Settings** -> **Devices & Services**.
2. Click **Add Integration**.
3. Search for **KeyForSteam**.
4. **Step 1**: Enter the name of the game (e.g., "Grand Theft Auto V").
5. **Step 2**: Select the correct game from the dropdown and choose your preferred currency.

---

## Entity Details 📊

### Main Sensor (`sensor.keyforsteam_<game>_price`)
- **State**: Lowest current price.
- **Attributes**:
  - `low_price`: Current cheapest price.
  - `best_seller`: Name of the store offering the lowest price.
  - `offer_count`: Total number of stores selling the game.
  - `rating`: Average user rating of the game.
  - `top_offers`: List of the top 5 cheapest deals.
  - `product_url`: Direct link to the price comparison page.

### Price Alert (`binary_sensor.keyforsteam_<game>_price_alert`)
- **State**: `on` if price is below the threshold set in integration options.
- **Configuration**: Set the threshold in the integration's **Configure** menu.

---

## Automation Examples 🤖

### 1. Notify when price drops below target
```yaml
alias: "Game Price Drop: Call of Duty"
trigger:
  - platform: state
    entity_id: binary_sensor.keyforsteam_call_of_duty_black_ops_6_price_alert
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "🔥 Deal Alert: Black Ops 6"
      message: >
        The price for Black Ops 6 has dropped to {{ states('sensor.keyforsteam_call_of_duty_black_ops_6_price') }}€!
        Cheapest seller: {{ state_attr('sensor.keyforsteam_call_of_duty_black_ops_6_price', 'best_seller') }}
      data:
        url: "{{ state_attr('sensor.keyforsteam_call_of_duty_black_ops_6_price', 'product_url') }}"
```

### 2. Daily Price Summary
```yaml
alias: "Daily Gaming Deals Summary"
trigger:
  - platform: time
    at: "10:00:00"
action:
  - service: notify.persistent_notification
    data:
      title: "Morning Price Check"
      message: >
        GTA V: {{ states('sensor.keyforsteam_grand_theft_auto_v_price') }}€
        Elden Ring: {{ states('sensor.keyforsteam_elden_ring_price') }}€
        Factorio: {{ states('sensor.keyforsteam_factorio_price') }}€
```

### 3. Change Light Color when a Deal is Active
```yaml
alias: "Gaming Deal Visual Alert"
trigger:
  - platform: state
    entity_id:
      - binary_sensor.keyforsteam_game1_price_alert
      - binary_sensor.keyforsteam_game2_price_alert
    to: "on"
action:
  - service: light.turn_on
    target:
      entity_id: light.office_desk
    data:
      color_name: green
      brightness: 255
```

---

## Troubleshooting 🔍

If the sensor shows "Unknown" or hasn't updated in a while:
1. Enable debug logging in `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.keyforsteam: debug
   ```
2. Check the logs under **System** -> **Logs**.
3. If errors persist for 24h, check the **Repairs** section for a known API issue notification.

---

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

---

## Disclaimer ⚖️

This integration is not an official product of AllKeyShop or KeyForSteam. It uses publicly available data provided for search engines. Please respect the terms of service of the website.