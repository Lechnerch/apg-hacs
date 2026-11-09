# Austrian Power Grid (APG) – Home Assistant Integration

A custom [HACS](https://hacs.xyz) integration that pulls data from the public
APIs of **Austrian Power Grid AG (APG)**, the operator of the Austrian
transmission grid.

It supports two APIs:

| API | Auth | What it gives you |
| --- | --- | --- |
| **Peak hour API** | none | Hours with expected high grid load for the next ~5 days |
| **Powermonitor / Infografics API** | Bearer token | Infographic datasets (renewable generation, load flows, available capacity, …) |

The **peak hour** part works out of the box with no account. The
**Powermonitor** part is optional and only loads if you supply a token.

> **Attribution (required by APG):** Mehr zum Thema sichere Stromversorgung und
> zur Energiewende unter [www.apg-powermonitor.at](https://www.apg-powermonitor.at).

---

## Installation

### Via HACS (recommended)

1. In HACS → ⋮ → **Custom repositories**, add this repository's URL with
   category **Integration**.
2. Search for **Austrian Power Grid** in HACS and install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** and search for
   **Austrian Power Grid**.

### Manual

Copy `custom_components/apg` into your Home Assistant `config/custom_components`
directory and restart Home Assistant.

---

## Configuration

Everything is configured in the UI (config flow). You can change all options
later via the integration's **Configure** button.

| Option | Meaning |
| --- | --- |
| **Update interval (minutes)** | How often the peak hour API is polled (default 30, min 5). The Powermonitor API is polled 4× less often. |
| **Powermonitor Bearer token** | Leave empty to only use peak hours. Provide a token to enable Powermonitor datasets. |
| **Powermonitor datasets** | Which Powermonitor content items to create sensors for. |

The "peak hour now" state always reflects the **current clock hour**; it flips
automatically on the hour without an extra API call.

### Where do I get a Powermonitor token?

The Powermonitor (Infografics) API requires an `Authorization: Bearer <token>`
header. APG publishes a shared demo token in the public Swagger documentation:

1. Open the [Infografics API Swagger page](https://awareness.cloud.apg.at/api/swagger/index.html?urls.primaryName=Infografics+API).
2. Read the API description — it contains the Bearer token to use.
3. Paste that token into the integration's configuration.

If you have your own APG Powermonitor account, you can use the token issued to
you instead. Tokens are stored encrypted in the Home Assistant config entry and
never logged.

---

## Entities

### Peak hours (always available)

| Entity | Type | Description |
| --- | --- | --- |
| `binary_sensor.apg_peak_hours_peak_hour_now` | binary_sensor | `on` while the current hour is a peak hour. Attributes: next peak, all upcoming peaks, span, total count. |
| `sensor.apg_peak_hours_peak_status` | sensor (enum) | `peak` / `off_peak` for the current hour. |
| `sensor.apg_peak_hours_next_peak_hour` | sensor (timestamp) | Start of the next upcoming peak hour. |
| `sensor.apg_peak_hours_peak_hours_today` | sensor | Number of peak hours on the local calendar day. |
| `sensor.apg_peak_hours_peak_hours_remaining` | sensor | Number of peak hours still to come in the data window. |

> Peak-hour status codes from the API: `1` = normal hour, `2` = peak hour.

### Powermonitor (only if a token is configured)

One sensor per selected dataset, e.g.
`sensor.apg_powermonitor_erzeugung_erneuerbarer_energien`.

- **State** = latest numeric value of the dataset's series.
- **Attributes** = detected unit, latest label/timestamp, point count and the
  raw series (capped to the last 48 points).

> ℹ️ The Powermonitor response envelope is not formally documented. The
> integration parses it defensively and exposes the raw series as an attribute
> so you can build template sensors if you need a specific field. If a value
> looks off, inspect the entity's `series` attribute.

---

## Example automation

Shift a load (e.g. an EV charger) away from peak hours:

```yaml
automation:
  - alias: "Pause charging during APG peak hours"
    trigger:
      - platform: state
        entity_id: binary_sensor.apg_peak_hours_peak_hour_now
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ev_charger

  - alias: "Resume charging after peak hours"
    trigger:
      - platform: state
        entity_id: binary_sensor.apg_peak_hours_peak_hour_now
        to: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.ev_charger
```

---

## Notes & limitations

- Both APIs are rate limited (HTTP 429). Keep the update interval reasonable.
- Only a single instance of the integration is supported (the data is
  nationwide).
- This project is **not affiliated with or endorsed by APG**. Data © Austrian
  Power Grid AG; usage subject to the
  [APG terms of use](https://www.apg.at/nutzungsbedingungen/).

## Development

Core data-parsing logic lives in `api.py` (`PeakHourData`) and
`powermonitor.py`, and has no Home Assistant dependency, so it can be unit
tested in isolation.
