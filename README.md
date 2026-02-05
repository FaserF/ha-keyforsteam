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
- **Additional Sensors**: Separate entities for **Rating**, **Offer Count**, and **Stock Status**.
- **Manual Refresh**: Use the "Update Now" button to trigger an immediate price check.
- **HA Repairs Service**: Automatic notification if the API changes or data cannot be fetched (24h failure or 404 Not Found).
- **Diagnostics**: Detailed diagnostic information for easier troubleshooting.

---

## Supported Websites 🌍

This integration supports all localized versions of the AllKeyShop network. It automatically selects the best site based on your currency:

| Currency | Primary Website | URL |
|----------|-----------------|-----|
| **EUR**  | KeyForSteam (DE) | [keyforsteam.de](https://www.keyforsteam.de) |
| **USD**  | AllKeyShop (US) | [allkeyshop.com](https://www.allkeyshop.com) |
| **GBP**  | AllKeyShop (UK) | [allkeyshop.com](https://www.allkeyshop.com) |

*Note: The integration uses JSON-LD structured data from these sites to provide stable price tracking.*

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

### Rating Sensor (`sensor.keyforsteam_<game>_rating`)
- **State**: Average user rating (e.g., 4.5).
- **Attributes**: `rating_count`.

### Offer Count Sensor (`sensor.keyforsteam_<game>_offer_count`)
- **State**: Number of stores selling the game.

### Stock Status (`binary_sensor.keyforsteam_<game>_stock`)
- **State**: `on` if at least one offer is available.

### Price Alert (`binary_sensor.keyforsteam_<game>_price_alert`)
- **State**: `on` if price is below the threshold set in integration options.
- **Configuration**: Set the threshold in the integration's **Configure** menu.

### Update Button (`button.keyforsteam_<game>_update`)
- **Action**: Immediately refresh the game data.

---

## Data Source & API 🛠️

This integration uses a combination of two reliable methods to provide up-to-date gaming data:

### 1. Game Search API
For the initial search and autocomplete during setup, the integration accesses the **AllKeyShop Catalog API**:
- **Endpoint**: `https://www.allkeyshop.com/api/v2/vaks.php?action=gameNames`
- **Data**: A comprehensive list of over 195,000 games with their unique IDs and standard names.
- **Search Optimization**: The integration uses a custom scoring system to prioritize base games over DLCs and Map Packs.

### 2. Live Price Extraction (JSON-LD)
To avoid unstable web scraping and ensure high data accuracy, the integration extracts structured **JSON-LD (Schema.org)** data directly from the product pages:
- **How it works**: Every product page contains a hidden `<script type="application/ld+json">` block that contains the official product metadata (ID, Price, Seller, Availability).
- **Stability**: This is a standard format used for search engine optimization (SEO), making it much more stable than parsing HTML elements.
- **Auto-Selection**: The integration automatically chooses the best website based on your configured currency (see [Supported Websites](#supported-websites-🌍)).

---

## Automation Examples 🤖

<details>
<summary><b>1. Notify when price drops below target</b></summary>

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
</details>

<details>
<summary><b>2. Daily Price Summary</b></summary>

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
</details>

<details>
<summary><b>3. Change Light Color when a Deal is Active</b></summary>

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
</details>

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