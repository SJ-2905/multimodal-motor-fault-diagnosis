# Project context and report guide

This document gives a student or reviewer the background needed to understand the prototype, reproduce the software setup, and write an accurate project report. It records decisions and observed debugging results; it does not claim that the prototype is an industrial diagnostic instrument.

## Project at a glance

**Project:** Multimodal edge-AI based electric motor fault diagnosis (prototype)

**Purpose:** Collect vibration, electrical, and temperature readings around a small DC motor and display them live. The intended study compares readings under documented operating conditions. The current system is an instrumented monitoring prototype. It does not yet establish a validated fault diagnosis model.

**Motor reported by the project owner:** Vega RoboKit, 12 V brushed DC helical gear motor, 200 RPM.

**Current sensor set:**

| Component | Role | Interface / signal |
|---|---|---|
| ESP32 DevKit V1 | Sensor acquisition, LED indication, local Wi-Fi access point and HTTP server | I²C, OneWire, GPIO, Wi-Fi |
| ADXL345 | Measures three-axis acceleration used to calculate a short-window vibration indicator | I²C; typical address `0x53`, alternate `0x1D` |
| INA219 breakout | Measures bus voltage and shunt current when the motor supply is routed through its VIN+ and VIN− terminals | I²C; commonly `0x40` |
| DS18B20 waterproof probe | Measures temperature near the motor or test point | OneWire on GPIO4 with 4.7 kΩ DATA-to-3.3 V pull-up |
| Green, yellow, red LEDs | Local status indication from prototype sensor/vibration/supply rules | ESP32 GPIO25, GPIO26, GPIO27 respectively |
| Laptop dashboard | Displays current values, sensor state, charts and threshold-based condition text | Streamlit over HTTP/Wi-Fi |

The earlier MPU6050 was replaced by the ADXL345 after repeated detection inconsistencies between an I²C bus-check sketch and the full streaming program. Historical MPU logs should not be confused with the active ADXL345 firmware.

## What the prototype currently does

1. The ESP32 initializes the I²C and OneWire buses and reads the ADXL345, INA219, and DS18B20.
2. It calculates a vibration variation value over a short window of accelerometer samples. The raw field is named `vibration_rms_g`; the dashboard converts it to metres per second squared using standard gravity (`9.80665 m/s² per g`).
3. It reads INA219 bus voltage and current. The current value represents motor current only if motor supply current physically flows through VIN+ and then VIN−. Merely connecting the INA219's logic pins to I²C is not enough to measure motor current.
4. It keeps the last valid temperature reading after a brief DS18B20 disconnect and retries the probe. The dashboard intentionally does not make a brief probe disconnect look like a motor fault.
5. It creates a local Wi-Fi access point named `MotorMonitor`, serves JSON telemetry at `http://192.168.4.1/api/telemetry`, and responds to `http://192.168.4.1/health` with `ok`.
6. The laptop's Streamlit dashboard polls the ESP32 directly over Wi-Fi. USB serial is used for programming and optional diagnostics, not for the dashboard's live data path.
7. Once motor bus voltage is present, it waits 5 seconds and collects five current readings while unloaded; their median becomes the running current baseline. A negative or below-0.02 A baseline is rejected. Firmware publishes baseline and current-to-baseline ratio in addition to the four measured values.
8. It drives status LEDs using simple prototype rules. Vibration at 0.15 m/s² is the yellow warning and 0.30 m/s² is the red alert. Current at 1.5× unloaded baseline is yellow; 2× is red and labelled possible overload. A warning/alert must persist for three consecutive sample windows, while ADXL345/INA219 faults are red and absent motor bus voltage is yellow. The LEDs are mutually exclusive. Temperature does not control them.
9. The dashboard's “Motor condition” panel interprets these vibration cutoffs, the current ratio, sensor availability, and supply presence. It reports maintenance check, high vibration, or possible overload; offline samples are labelled last-known, not live.

The vibration cutoffs and current multipliers are demonstration thresholds. They are not derived from the motor manufacturer's limits, an ISO vibration severity assessment, a calibrated current limit, or a labelled fault dataset. The current ratio is relative to a no-load baseline; a 2× rise is not, by itself, proof that the rated overload limit has been exceeded. “No configured fault indicator” means only that these prototype rules were not crossed; it does not prove the motor is healthy.

## Hardware and wiring reference

### Low-voltage sensor connections

For the ESP32 DevKit V1 pin labels used in the firmware:

| ESP32 connection | Connects to |
|---|---|
| 3V3 | ADXL345 VCC, INA219 logic VCC, DS18B20 VDD (verify the exact probe pinout), pull-up resistor leg |
| GND | ADXL345 GND, INA219 logic GND, DS18B20 GND, and a common reference to the motor battery negative |
| GPIO21 / D21 | ADXL345 SDA and INA219 SDA (shared I²C data bus) |
| GPIO22 / D22 | ADXL345 SCL and INA219 SCL (shared I²C clock bus) |
| GPIO4 / D4 | DS18B20 DATA and one leg of the 4.7 kΩ pull-up resistor |
| GPIO25 | Green LED through its own series current-limiting resistor |
| GPIO26 | Yellow LED through its own series current-limiting resistor |
| GPIO27 | Red LED through its own series current-limiting resistor |

The other leg of the DS18B20 4.7 kΩ resistor goes to 3V3. This is a pull-up from DATA to 3V3, not a resistor inserted in series in the data wire. On the common waterproof probe used during the build, red was treated as VDD, black as ground, and yellow as DATA, but cable colors are not universal; verify the probe's pinout before powering it.

ADXL345 and INA219 share SDA/SCL, but each still needs correct 3.3 V and common ground. Do not connect the accelerometer's auxiliary XDA/XCL pins to the ESP32 I²C bus; the pins used by this design are labelled SDA and SCL.

### Motor power and current measurement

The intended high-side motor-current path is:

```text
Battery pack positive
  → correctly rated fuse
  → motor on/off switch
  → INA219 VIN+
  → INA219 VIN−
  → motor positive

Motor negative → battery pack negative
Battery pack negative/common reference → INA219 logic GND and ESP32 GND
```

Battery negative is one common node with branches; the grounds are not connected in series. Use an appropriately rated terminal block or insulated splice to make the branch. Keep motor current out of the breadboard, ESP32, sensor logic pins, and 3.3 V rail. The ESP32 and sensor logic should have their own suitable low-voltage power source; USB powers the ESP32 during bench setup.

The pack was described as a three-cell holder with three lithium cells reading approximately 3.98 V each. That adds to about 11.94 V only if the cells are connected in series. Identify cell chemistry, series/parallel arrangement, protection and charging method before further use. A 500 mA fuse reportedly blew. The motor's startup/stall current, actual fuse type/rating, switch rating, wiring rating, and exact INA219 shunt rating were not established. Do not bypass the fuse, deliberately stall the motor, or run it without appropriate overcurrent protection. The INA219 breakout must be verified to tolerate the motor's voltage and current; a common `R100` shunt marking often means 0.10 Ω but is not enough to establish the board's safe rating.

### Breadboard lessons

On a typical solderless breadboard, A–E holes on one numbered row are connected to each other; F–J holes on that same row form a separate connected group. The center gap separates the groups. Side power rails can break in the middle. Some sensor boards initially lacked soldered headers, so wires that looked aligned beside plated pads did not necessarily make contact. During debugging, 3.3 V was present at the ESP32 but absent from expected breadboard rows; removing the ESP32 from the breadboard and using jumper leads corrected the distribution. Measure at the actual sensor pins and verify rail continuity instead of assuming nearby holes are connected.

## Software architecture and files

| File / directory | Purpose |
|---|---|
| `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino` | Active intended firmware: ADXL345 + INA219 + DS18B20, LEDs, Wi-Fi AP, health route and telemetry JSON |
| `firmware/adxl345_static_calibration/adxl345_static_calibration.ino` | Diagnostic six-orientation ADXL345 calibration sketch; flashing it replaces the Wi-Fi streaming sketch until the latter is uploaded again |
| `firmware/esp32_motor_monitor/esp32_motor_monitor.ino` | Legacy MPU6050/USB-serial sketch, not the active configuration |
| `app.py` | Streamlit dashboard, condition panel, current values and trend charts |
| `wifi_monitor.py` | Background HTTP polling, JSON validation, reconnect/freshness status and bounded sample history |
| `requirements.txt` | Dependencies needed to run the dashboard |
| `requirements-model.txt`, `train_model.py`, `data/`, `models/`, `reports/` | Separate earlier synthetic-data machine-learning experiment; not used by the live dashboard |
| `CALIBRATION.md` | Sensor calibration/reference-check procedure and limits |
| `docs/PROJECT_HANDOFF.md` | Detailed circuit, firmware behavior, setup, troubleshooting and safety handoff |

### Telemetry interface

The ESP32 telemetry endpoint returns one JSON object with fields similar to:

```json
{
  "device": "ESP32 DevKit V1",
  "firmware": "MotorMonitor Wi-Fi",
  "sample_id": 42,
  "uptime_ms": 123456,
  "vibration_rms_g": 0.0123,
  "voltage_v": 11.8,
  "current_a": 0.24,
  "current_baseline_a": 0.20,
  "current_load_ratio": 1.2,
  "temperature_c": 29.5,
  "sensor_status": {
    "adxl345": true,
    "ina219": true,
    "ds18b20": true
  }
}
```

Values above are an interface example, not a recorded or accuracy-validated sample. Failed/non-finite measurements are represented as JSON `null`. `voltage_v` is the INA219 bus reading at VIN− relative to its ground and is not necessarily the battery voltage at VIN+. `current_baseline_a` and `current_load_ratio` are supplied by the new streaming firmware and will be absent if an older sketch is still flashed.

### Reproducing the software setup

1. Install Arduino IDE and the Espressif ESP32 board package.
2. Install **Adafruit ADXL345**, **Adafruit Unified Sensor**, **Adafruit INA219**, **OneWire**, and **DallasTemperature** from Library Manager.
3. Open `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino`, select **ESP32 Dev Module** and the port belonging to the connected ESP32, then use Upload. Serial Monitor diagnostics use **115200 baud**. The normal dashboard data link is Wi-Fi, not serial.
4. Install Python 3, clone this repository, create a virtual environment, and install dashboard requirements:

   ```bash
   git clone https://github.com/SJ-2905/multimodal-motor-fault-diagnosis.git
   cd multimodal-motor-fault-diagnosis
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

   On Windows PowerShell, use `py -m venv .venv`, then run the activation script at `.venv/Scripts/Activate.ps1`.

5. Join the laptop to the ESP32 network `MotorMonitor` (default password `motorlab24`; a no-internet warning is expected). Confirm `http://192.168.4.1/health` returns `ok`, then check `http://192.168.4.1/api/telemetry`.
6. From the repository root, run `streamlit run app.py`, then open the local URL it prints, normally `http://localhost:8501`.
7. For a gradual-load demonstration, first run the motor without added load and wait until the dashboard says its current baseline is ready (typically about 10–15 seconds from switching on). Then increase load carefully with a rated, controlled fixture. The LED/status stages are mutually exclusive: green → yellow → red.

Install Python packages while internet is available before joining the ESP32's local-only AP. The dashboard computer must have a network route to the ESP32. If credentials or IP are changed, update the firmware or set `ESP32_TELEMETRY_URL` in the dashboard environment.

## Build and debugging history

This is a concise record of the integration path. Symptoms and causes are separated where the cause was not conclusively measured.

1. **Initial parts and wiring:** The first setup used an ESP32, MPU6050, INA219, and three-wire DS18B20 probe on a solderless breadboard. The owner requested coordinate-based wiring because the breadboard holes and sensor pins were confusing. Poor visibility of wiring, missing soldered headers, row grouping, and split rails made visual verification difficult.
2. **Temperature probe intermittency:** The OneWire scan sometimes found family code `0x28` but a temperature conversion failed; at other times the probe read around 29–33 °C. A misplaced ESP32 jumper and a failed 3.3 V distribution through breadboard rows were discovered. After reseating power and the data lead, valid readings resumed. The 4.7 kΩ pull-up must connect the shared DATA/GPIO4 node to 3.3 V.
3. **MPU6050 detection mismatch:** Bus scans sometimes reported an MPU6050 at `0x68`, while the full stream sketch reported it missing. Rewiring and a replacement module did not make the full build reliable. The evidence did not isolate whether the issue was contact, wiring, bus initialization, or breakout-specific behavior. The project moved to an ADXL345 rather than claiming a definitive MPU root cause.
4. **ADXL345 integration:** The bus scan later detected the ADXL345 at `0x53`; `0x1D` is possible with SDO high. The active firmware was changed to the ADXL345 library and interface. An earlier compile error for a missing MPU library belonged to the old sketch. A later ESP32 core compile ambiguity in `String(float, digits)` was fixed by explicitly casting the decimal-place argument.
5. **USB serial confusion:** OpenOCD failed to find an FTDI debug device because a debug action was selected without a compatible debug probe; serial upload via esptool succeeded separately. Several garbled serial sessions were associated with baud/serial-monitor confusion and boot logs; they were not, by themselves, proof that sensor values were corrupted. USB is reserved for flashing and diagnostics in the current Wi-Fi architecture.
6. **Stream behavior:** The legacy system emitted CSV serial rows. The requested direction changed to a direct ESP32 Wi-Fi monitor to avoid needing a serial port for live telemetry. The active firmware now starts its own AP and returns JSON; the laptop runs Streamlit and polls over HTTP.
7. **Motor supply issues:** The motor did not initially run, voltage at the motor was measured as zero at one point, a 500 mA fuse reportedly blew, and later the motor started after wiring was corrected. The fuse event and unknown stall current remain safety and measurement limitations. There is no verified result showing that the current sensor/shunt is safely sized for the motor under load.
8. **Status behavior:** The owner requested that temperature probe flicker not trigger a motor fault indication and that the last good temperature remain visible briefly. Firmware now holds the last valid DS18B20 value and excludes temperature from status LEDs. User-selected vibration cutoffs were lowered to 0.15/0.30 m/s² because earlier 30/35 m/s² values were never reached in the observed runs. Current escalation is now relative to an automatically captured unloaded baseline (1.5× warning, 2× possible-overload alert), with three-window persistence to reduce brief transients.

The `docs/PROJECT_HANDOFF.md` file has the longer troubleshooting checklist and should be consulted before changing the wiring.

## Calibration and limits on claims

The firmware correction constants are neutral by default (zero offsets and unit scales). The measurements have not been validated against calibrated instruments in the assembled motor setup.

- **ADXL345:** Follow the six-orientation procedure in `CALIBRATION.md` for static per-axis bias and scale. This does not characterize mounting resonance, vibration frequency response, or fault thresholds.
- **INA219:** Verify the actual shunt value and current/voltage rating. Compare bus voltage with a trusted meter and current with a suitable series reference at safe known loads. Do not place a multimeter in current mode directly across a supply.
- **DS18B20:** Compare against a trusted thermometer at stable temperatures; repair intermittent wiring before applying offsets.
- **Motor condition thresholds:** The 0.15/0.30 m/s² vibration cutoffs and 1.5×/2× current multipliers are demonstration choices, not manufacturer recommendations or universal “healthy/faulty” boundaries. Build a repeatable baseline, document sensor mounting and motor load, and validate across multiple runs before drawing conclusions.
- **Machine learning:** The repository's separate Random Forest experiment uses synthetic/generated measurements. Its score applies only to that generated dataset and is not evidence of real-motor fault accuracy. The current live dashboard does not use the model's predictions.
- **Load testing:** Do not intentionally overload or stall the motor without an appropriate controlled fixture and verified fuse, battery, wiring, switch, and INA219 ratings. A casual mechanical brake is not a calibrated dynamometer.

### Suggested report structure

1. **Objective:** State that the work integrates edge sensing and visualization for an educational motor-monitoring prototype.
2. **Hardware:** Name the ESP32, ADXL345, INA219, DS18B20, motor, LED indicators, and power arrangements. Include a labelled diagram and explain the INA219 series shunt path.
3. **Methods:** Document pin mapping, sampling window, RMS-variation calculation, Wi-Fi JSON transfer, displayed units, test setup, and any calibration procedure actually completed.
4. **Results:** Include timestamped raw samples and test conditions (motor off, normal operation, controlled repeatable load). Distinguish observed results from assumptions; report sensor dropouts and retries rather than hiding them in the experimental record.
5. **Interpretation:** Explain the prototype threshold/LED behavior and the condition panel. Use “within configured demonstration thresholds” rather than stating the motor is proven healthy.
6. **Limitations and next steps:** Report calibration status, current-path/shunt limits, repeatability, sample bandwidth/window, motor load control, and absence of a real labelled fault dataset. Propose instrument comparison and controlled, labelled tests before claiming fault-diagnosis performance.

## Current verification status

The repository describes the intended integration, and the Streamlit app was previously started locally. At the latest device check recorded in the handoff, this Mac was not associated with the ESP32 AP and the ESP32 endpoint/USB serial port were unavailable. Therefore, a successful local code edit or dashboard launch must not be represented as a current live hardware test. To verify the system, flash the active firmware, join `MotorMonitor`, confirm `/health` and changing `sample_id` values at `/api/telemetry`, and check that the dashboard updates with fresh samples.

## Sources of truth in this repository

- `README.md` — quick setup, wiring summary, safety notes, and field meanings.
- `docs/PROJECT_HANDOFF.md` — detailed wiring, architecture, LED rules, setup, and troubleshooting.
- `CALIBRATION.md` — reference checks and calibration procedure.
- `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino` — actual firmware pins, sampling, thresholds, telemetry and LED behavior.
- `app.py` and `wifi_monitor.py` — dashboard logic, status interpretation, polling, and graph history.
