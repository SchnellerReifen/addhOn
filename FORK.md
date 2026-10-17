# addhOn – persönlicher Fork (WH-Steuerung)

Dieser Fork basiert auf `tis24dev/addhOn` und ergänzt die Steuerung für
Wassererhitzer vom Typ **WH** (elektrisch). Das Original-README von Upstream gilt
weiterhin.

## Was dieser Fork zusätzlich kann

- **`water_heater`-Entity für Typ WH** (hinter der Option *Experimental*):
  Zieltemperatur (30–85 °C), Ein/Aus und Modus `normal/eco/max/bps`.
- **Sendeprofil `WH`** (`send_profiles.py`):
  - Moduswechsel (laufendes Gerät): sparse `startProgram {machMode}`
  - Ein und Moduswahl im Aus-Zustand: Programm-Start (`async_send_program`,
    `startProgram` mit `programName` + Kategorie-Body)
  - Aus: sparse `stopProgram {onOffStatus:"0"}`
  - Temperatur: `settings {tempSel}` (Wire `setParameters`)
- **Read-only-Zusatz-Entities für WH** (capability-gated):
  `errors`, `program_name`, `remaining_hot_water`, `total_work_time` (Minuten),
  `selected_temperature`, `mode`, `sterilization_remaining`,
  `heating` (aus `power > 0`), `anode_maintenance`, `tank_maintenance`,
  `energy_saving`, `anode_low`.

## Installation (HACS)

1. HACS → Menü → **Custom repositories** → `https://github.com/SchnellerReifen/addhOn`
   als Kategorie **Integration** hinzufügen.
2. Installieren, Home Assistant neu starten.
3. In der Integration die Option **Experimental** aktivieren (nötig für die
   WH-`water_heater`-Entity).

## Release-Routine

- **Code-Änderung:** Version in `custom_components/addhon/manifest.json` erhöhen,
  committen (deutsch, Betreffzeile + Aufzählungspunkte), nach `origin/main` pushen
  und ein GitHub-Release mit `addhon.zip` anlegen. Grund: `hacs.json` setzt
  `zip_release`; der Workflow `.github/workflows/release.yml` hängt das Zip an das
  Release.
- **Reine Doku-Änderung:** nur committen – kein Versionssprung, kein Release.
- **Upstream aktualisieren:** `git fetch upstream` und `git rebase upstream/main`.

## Herkunft

- Modell-Referenz: `ES100V-FE3W(EU)`, Typ `WH`, Serie `fe3`, 100 L.
- Vergleichs-Integration: `gvigroux/hon` (gleiches Gerät).
