# Home-Assistant-Einrichtung (Warmwasser)

Diese Bordmittel liegen zusätzlich zur Integration auf der HA-Instanz. Sie sind
**nicht** Teil des Integrationscodes, sondern per UI/API angelegt; dieses Dokument
hält sie reproduzierbar fest.

Modell-Referenz: `ES100V-FE3W(EU)` (Typ WH). Basis-Sensoren der Integration:
`sensor.es100v_fe3w_eu_power` (W), `binary_sensor.es100v_fe3w_eu_heating`,
`sensor.es100v_fe3w_eu_water_temperature`, `sensor.es100v_fe3w_eu_errors`.

## Helfer

### Template-Sensoren
- **Heizt (0/1)** – `sensor.wh_heizung_aktiv`
  `{{ 1 if (states('sensor.es100v_fe3w_eu_power') | float(0)) > 0 else 0 }}`
- **Aktuelle Heizdauer** – `sensor.wh_heizdauer_aktuell` (Einheit h, `duration`)
  `{{ ((now() - states.binary_sensor.es100v_fe3w_eu_heating.last_changed).total_seconds() / 3600) | round(3) if is_state('binary_sensor.es100v_fe3w_eu_heating','on') else 0 }}`
- **Heizt seit** – `sensor.wh_heizt_seit` (`timestamp`)
  `{{ states.binary_sensor.es100v_fe3w_eu_heating.last_changed.isoformat() if is_state('binary_sensor.es100v_fe3w_eu_heating','on') else none }}`
- **Letzte Heizdauer** – `sensor.letzte_heizdauer` (Einheit h, `duration`): spiegelt
  `sensor.wh_heizdauer_aktuell`, solange geheizt wird, und **friert beim Abschalten**
  den letzten Wert ein (über `this.state`)
  `{{ states('sensor.wh_heizdauer_aktuell') if is_state('binary_sensor.es100v_fe3w_eu_heating','on') else (this.state if this.state not in ['unknown','unavailable','none'] else 0) }}`

### Integration (Riemann-Summe)
- **Heizzeit gesamt** – `sensor.warmwasser_heizzeit_gesamt` (h): Quelle `sensor.wh_heizung_aktiv`,
  `unit_time: h`, `method: left`, `max_sub_interval: 1 min`
- **Verbrauch gesamt** – `sensor.es100v_fe3w_eu_warmwasser_verbrauch_gesamt` (kWh): Quelle
  `sensor.es100v_fe3w_eu_power`, `unit_prefix: k`, `unit_time: h`, `method: left`,
  `max_sub_interval: 1 min`

### History Stats
- **Heizzeit heute** – `sensor.es100v_fe3w_eu_wh_heizzeit_heute` (h): Entity
  `binary_sensor.es100v_fe3w_eu_heating`, `state: on`, `start: {{ today_at() }}`,
  `end: {{ now() }}`
- **Heizzeit 7 Tage** – `sensor.es100v_fe3w_eu_wh_heizzeit_7_tage` (h): `start:
  {{ now() - timedelta(days=7) }}`, `end: {{ now() }}`

### Utility Meter
- **Verbrauch heute / Woche / Monat** –
  `sensor.es100v_fe3w_eu_warmwasser_verbrauch_heute` (`daily`),
  `..._woche` (`weekly`), `..._monat` (`monthly`, kWh): Quelle jeweils
  `sensor.es100v_fe3w_eu_warmwasser_verbrauch_gesamt`

## Automations
- **Warmwasser: wöchentliche Desinfektion 65 °C** (`automation.warmwasser_woechentliche_desinfektion_65_c`)
  – Trigger: Zeit 03:00, Bedingung: Sonntag. Aktion: Solltemperatur auf 65 °C,
  warten bis `sensor.es100v_fe3w_eu_water_temperature` ≥ 60 °C (max. 2 h), danach
  die vorherige Solltemperatur wiederherstellen.
- **Warmwasser: Fehlercode** (`automation.warmwasser_fehlercode`)
  – `numeric_state` `sensor.es100v_fe3w_eu_errors` > 0 → `persistent_notification`.
- **Warmwasser: lange Heizzeit heute** (`automation.warmwasser_lange_heizzeit_heute`)
  – `numeric_state` `sensor.es100v_fe3w_eu_wh_heizzeit_heute` > 6 (h) → `persistent_notification`.

## Dashboard
- Storage-Dashboard **Warmwasser** unter `/warmwasser-panel`:
  - Thermostat auf `water_heater.es100v_fe3w_eu_water_heater`
  - Karten: *Status*, *Heizzeiten*, *Verbrauch (kWh)*, *Wartung*

## Namensgebung
- Den Integrations-Entities wurde im Entity-Register ein eigener `name` gegeben
  (`config/entity_registry/update`), damit HA bei `has_entity_name` nicht
  „`<Gerätename> `" voranstellt. Entity-IDs bleiben unverändert.

## Entfernte Entity
- **Betriebszeit gesamt** (`sensor.es100v_fe3w_eu_total_work_time`) – ab v5.27.9 nicht
  mehr vorhanden: `totalWorkTime` bleibt auf dem ES100V praktisch stehen (1–2 Minuten)
  und ist damit keine nutzbare Betriebszeit.
