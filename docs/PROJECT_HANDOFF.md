# Project handoff: ESP32 motor condition monitoring

This is the working handoff for the project owner, another student, or a coding agent continuing the build. It records the intended circuit and software, the decisions made during integration, the issues that were observed, and what still needs confirmation. Read the safety section before connecting the motor battery.

## 1. Current project state

### Chosen configuration

- Controller: ESP32 DevKit V1 (ESP32-WROOM-32 family board).
- Motion sensor: ADXL345. This replaced the repeatedly troublesome MPU6050 in the active build.
- Electrical sensor: INA219 breakout. Its logic interface is I²C; motor current is sensed only through its VIN+ / VIN− screw-terminal shunt path.
- Temperature sensor: three-wire DS18B20 probe with a 4.7 kΩ pull-up from DATA to 3.3 V.
- Motor: Vega RoboKit 12 V, 200 RPM geared brushed DC motor (as reported by the owner).
- Data link: the active firmware is designed to make an ESP32 Wi-Fi access point called `MotorMonitor` and expose JSON over HTTP. The Streamlit app polls the ESP32 directly; it does not need Arduino Serial Monitor or USB serial for live data.
- Local dashboard: `app.py`, using `wifi_monitor.py`; default browser URL is `http://localhost:8501`.

### What has been demonstrated, and what has not

- Earlier bus-check runs found the INA219 at I²C address `0x40`, the MPU6050 at `0x68` on some runs, and the DS18B20 as OneWire family code `0x28`. The DS18B20 produced readings around 29–33 °C after a misplaced ESP32 jumper was corrected.
- After switching to the ADXL345, a bus scan found it at `0x53`; `0x1D` is also valid when its address-select pin is high. The sensor-stream screen later showed changing acceleration/vibration values and temperature; INA219 current was near zero in a no-load/standalone setup, which does not prove motor current measurement.
- The new Wi-Fi firmware and dashboard are in the local working repository. The Streamlit server was started locally and its Streamlit health endpoint returned `ok` on 2026-11-13.
- A live connection to the ESP32 Wi-Fi HTTP endpoint was **not** confirmed in the last host check: the Mac did not report an associated Wi-Fi network and `192.168.4.1` did not respond. The owner separately reported that Wi-Fi had connected earlier. Recheck by joining `MotorMonitor` and opening the ESP32 health URL before claiming the latest Wi-Fi firmware is live.
- The firmware fix for an Arduino compile ambiguity in `String(value, digits)` is included in `esp32_adxl345_stream.ino` as an explicit cast. The latest Wi-Fi firmware should still be compiled and flashed on the actual board, then checked against the endpoint and sensors.
- The accelerometer and electrical calibration constants are still neutral defaults. Sensor values have **not** been shown to be industrially accurate. No labelled motor-fault dataset or validated fault model is available.
- A 500 mA fuse reportedly blew during the motor work. The motor's startup/stall current and the exact INA219/shunt rating have not been established. Do not bypass the fuse or run without suitable overcurrent protection.

## 2. Repository map and which files are active

| Path | Role |
|---|---|
| `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino` | **Active intended integration firmware:** ADXL345 + INA219 + DS18B20, LEDs, Wi-Fi AP, health route and telemetry JSON route. |
| `firmware/adxl345_static_calibration/adxl345_static_calibration.ino` | Temporary calibration/diagnostic sketch for measuring ADXL345 at six static orientations over Serial Monitor. Do not leave this flashed when expecting the live Wi-Fi dashboard. |
| `firmware/esp32_motor_monitor/esp32_motor_monitor.ino` | **Legacy serial firmware** for the old MPU6050 configuration. It prints CSV to USB serial and is not the active ADXL345/Wi-Fi firmware. |
| `app.py` | Streamlit UI: connection state, latest values, sensor status, trend charts, and simple recent-direction descriptions. |
| `wifi_monitor.py` | Background HTTP poller, JSON validation, reconnect handling, and bounded sample history for Streamlit. |
| `requirements.txt` | Runtime dashboard dependencies only. |
| `requirements-model.txt` | Optional dependencies for the older synthetic-data model/training files. Not required to run the live dashboard. |
| `CALIBRATION.md` | Calibration and reference-check method, including limitations. |
| `train_model.py`, `data/`, `models/`, `reports/`, `TRAINING_SUMMARY.json` | Earlier synthetic-data model experiment and its artifacts. Not part of live sensor ingestion and not used by the current dashboard. |
| `ESP32_SERIAL_FORMAT_EXAMPLE.txt` | Format note for the older serial protocol. The current Wi-Fi dashboard expects JSON over HTTP instead. |

Do not confuse the legacy MPU/serial sketch with the active ADXL345/Wi-Fi integration sketch. Keep the sensor pins in firmware aligned with the physical wiring and this handoff.

## 3. System architecture

```text
ADXL345 ─┐
         ├── shared I²C (SDA GPIO21, SCL GPIO22) ── ESP32
INA219 ──┘                                            │
                                                     ├── SoftAP: MotorMonitor
DS18B20 DATA ── GPIO4 + 4.7 kΩ pull-up ─────────────┤      └── HTTP JSON
                                                     │           └── /api/telemetry
INA219 VIN+/VIN− ── motor battery/load current path  │
                                                     └── local Wi-Fi client
                                                            └── Streamlit dashboard
```

1. The ADXL345 supplies acceleration events over I²C.
2. Firmware collects 200 events, applies the configured per-axis static bias/scale corrections, removes each axis's mean for the window, and computes the square root of the sum of the three axis variances. It labels this result `vibration_rms_g`. This is a simple short-window acceleration-variation feature; it is not a frequency-spectrum vibration measurement.
3. INA219's library supplies bus voltage and shunt current. Firmware converts library current from mA to A and applies configurable offset/scale correction. Current is only motor current if the motor supply is physically routed through VIN+ to VIN− and the breakout remains within its rating.
4. DallasTemperature/OneWire reads the DS18B20. After its first valid reading, firmware holds the last valid temperature through a probe disconnect and retries discovery/read; it does not make the status LEDs red. Before the first valid temperature, the JSON value is `null`.
5. ESP32's `WebServer` returns the latest sample as JSON and provides `/health` for reachability. The default SoftAP IP is `192.168.4.1`.
6. `WifiTelemetryClient` polls every 0.8 s, validates the four fields, stores a maximum of 600 distinct sample IDs, and separates Connected, Reconnecting, and Waiting based on response age. The dashboard redraws every second and graphs the most recent 120 points. The live dashboard transport is Wi-Fi/HTTP; the active sketch does not use Bluetooth.
7. The dashboard trend card compares the median of the previous six valid measurements with the median of the latest six. A change above +10% is called rising, below −10% falling, otherwise steady. A floor in the percent denominator avoids division by near-zero values. This is a descriptive heuristic only, not a fault classifier or alarm threshold.

## 4. Hardware wiring

### 4.1 Logic/sensor wiring

Use the labels printed on the modules; wire colors are only aids. With all power disconnected while rewiring:

| ESP32 DevKit V1 | Connect to |
|---|---|
| `3V3` | ADXL345 VCC, INA219 logic VCC, DS18B20 VDD (after verifying probe pinout), and one side of 4.7 kΩ resistor |
| `GND` | ADXL345 GND, INA219 logic GND, DS18B20 GND, and the common low-voltage reference described below |
| `GPIO21` / `D21` | ADXL345 SDA and INA219 SDA (same shared SDA line) |
| `GPIO22` / `D22` | ADXL345 SCL and INA219 SCL (same shared SCL line) |
| `GPIO4` / `D4` | DS18B20 DATA and one side of 4.7 kΩ resistor |
| `GPIO25` | green LED output through its own current-limiting resistor |
| `GPIO26` | yellow LED output through its own current-limiting resistor |
| `GPIO27` | red LED output through its own current-limiting resistor |

The pull-up resistor belongs **between** the DATA node and 3V3: one resistor leg shares an electrically common node with the probe DATA and GPIO4; the other resistor leg goes to 3V3. It is not placed in series with the data wire. A typical waterproof DS18B20 cable used in this build was identified as red=VDD, black=GND, yellow=DATA; cable colors are not universal, so verify the exact probe before powering it.

The INA219's VCC/GND/SDA/SCL pins are its low-voltage logic supply and I²C connection. Its VIN+/VIN− screw terminals are a separate part of the motor supply measurement path. Do not confuse the header VCC with VIN+.

### 4.2 Breadboard facts that mattered during debugging

- A typical breadboard connects the five holes A–E in one numbered row together; the five F–J holes on that same row are another connected group. The center trench isolates the groups.
- Power rails along the edge can be interrupted in the middle. A jumper bridge may be required to connect the upper and lower rail sections; confirm with a continuity/voltage check on the actual board.
- A sensor PCB with empty plated holes does not automatically make electrical contact with a breadboard. It needs soldered header pins or a mechanically secure lead that actually reaches a breadboard contact. A wire placed in the next row or merely beside the PCB pin is not electrically connected.
- ESP32 dev boards are wide and may not sit correctly on a breadboard. In this project the ESP32 was eventually taken off the breadboard and wired with jumpers; this corrected an observed case where the 3V3 pin measured correctly but the breadboard rows intended to distribute it did not.
- Do not put motor current through breadboard contact strips. Use suitable wire/terminal connections for the battery–fuse–switch–INA219 shunt–motor path.

### 4.3 Motor power and current safety

The intended low-side reference and high-side current path are:

```text
Battery pack positive
    │
    └── correctly rated DC fuse ── switch ── INA219 VIN+
                                               INA219 VIN− ── motor positive
Battery pack negative ───────────────────────────────────── motor negative
          │
          ├── ESP32 GND
          └── INA219 logic GND
```

Battery negative is one common electrical node. Branching it to the motor negative, ESP32 GND, and INA219 GND does **not** mean connecting them in series. Make the branch with a suitable connector/terminal block or a sound, insulated splice. Keep high-current motor return wiring physically suitable; do not make the breadboard the motor-current junction. ESP32 and sensors must be powered from their appropriate low-voltage source/USB, never from the motor current path.

Before use, identify the battery cell chemistry, series arrangement, fully charged voltage, motor stall current, fuse type and rating, switch rating, wire rating, and INA219 module/shunt rating. Three cells each reported around 3.98 V sum to about 11.94 V only if they are actually wired in series; this is not a substitute for measuring the pack or verifying its protection/charging arrangement. A motor can draw a high startup or stall current. The reported 500 mA fuse blowing is evidence that the current path needs investigation; it does not justify using a larger fuse without checking the motor and wiring ratings. Never bypass the fuse or operate deliberately without overcurrent protection.

`R100` on a shunt often denotes 0.10 Ω, but confirm the exact module. The Adafruit INA219 library's default `begin()` calibration is intended for a common 0.10 Ω breakout and a 2 A range; clones and other shunts may differ. Do not infer current accuracy from the printed label alone. The INA219 voltage shown by this firmware is VIN− relative to GND, not automatically battery positive voltage. Follow the exact breakout documentation and observe voltage, current, and thermal limits.

## 5. Firmware behavior and HTTP interface

### Startup

At boot, firmware starts Serial at **115200 baud**, initializes GPIO25–27, then starts the Wi-Fi access point and HTTP server. It initializes I²C on SDA 21 / SCL 22 at 100 kHz, scans for ADXL345 at `0x53` or `0x1D`, initializes INA219, and discovers the DS18B20. Startup details are printed to USB serial for debugging. There is no LED self-test; red is reserved for ADXL345/INA219 faults.

### Routes and payload

- `GET /` returns a short plain-text “online” response.
- `GET /health` returns plain-text `ok` when the HTTP server is responding.
- `GET /api/telemetry` returns JSON. The payload includes device, firmware label, monotonically increasing `sample_id`, `uptime_ms`, four measurements, and per-sensor booleans.

Payload shape:

```json
{
  "device": "ESP32 DevKit V1",
  "firmware": "MotorMonitor Wi-Fi",
  "sample_id": 42,
  "uptime_ms": 123456,
  "vibration_rms_g": 0.0123,
  "voltage_v": 11.8,
  "current_a": 0.24,
  "temperature_c": 29.5,
  "sensor_status": {
    "adxl345": true,
    "ina219": true,
    "ds18b20": true
  }
}
```

Numbers in this example are illustrative, not a promised/validated live reading. Failed or non-finite values serialize as JSON `null`. The dashboard expects all four named fields; changing field names requires changing firmware and `wifi_monitor.py` together.

### LED states

The code uses these status states:

| LED | Firmware condition |
|---|---|
| Red | ADXL345/INA219 failed to initialize or ADXL345 read failed repeatedly |
| Yellow | ADXL345/INA219 checks pass, but INA219 bus voltage is below 1.0 V |
| Green | ADXL345/INA219 checks pass and INA219 bus voltage is at least 1.0 V |

The firmware retries failed ADXL345 / INA219 initialization every 2 seconds. A single transient ADXL345 read miss does not turn the red LED on. The DS18B20 value holds the last valid sample through a disconnect; its status is hidden from dashboard sensor cards and it never controls the red LED. This means the displayed temperature may be old while the probe is loose. The LEDs do not identify motor faults, indicate battery safety, or replace a fuse/driver. Red is no longer flashed during startup; LEDs remain off during initialization and then show the motor-sensor state.

## 6. Clean installation and runbook

### A. Prepare the code on a second computer

1. Clone the repository after the latest changes have been published to the intended GitHub branch. `main` is the normal clone target.
2. Install Python 3.10 or newer (the existing development computer used Python 3.14; the dashboard itself uses ordinary Python, Streamlit, pandas, and Requests).
3. Create and activate a virtual environment.
4. Install `requirements.txt`. `requirements-model.txt` is not needed for the live dashboard.
5. Do these network-dependent installation steps while the computer has normal internet access. The ESP32 AP is expected to have no internet.

macOS/Linux commands:

```bash
git clone https://github.com/SJ-2905/multimodal-motor-fault-diagnosis.git
cd multimodal-motor-fault-diagnosis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
git clone https://github.com/SJ-2905/multimodal-motor-fault-diagnosis.git
cd multimodal-motor-fault-diagnosis
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### B. Flash the intended ESP32 firmware

1. Connect ESP32 by USB. Install Arduino IDE and the Espressif ESP32 board package if absent.
2. Open `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino`.
3. Install libraries in Library Manager: **Adafruit ADXL345**, **Adafruit Unified Sensor**, **Adafruit INA219**, **OneWire**, **DallasTemperature**.
4. Select **ESP32 Dev Module** and the port that appears when the board is connected.
5. Use the Upload arrow. The Debug/bug action is not the normal USB upload path; an earlier OpenOCD attempt failed because no FTDI debug adapter was present, while serial flashing succeeded.
6. Open Serial Monitor at 115200 baud if checking startup diagnostics. Close Serial Monitor before uploading if it holds the port.
7. Confirm output indicates Wi-Fi AP ready and sensor initialization. A bus scan should normally show ADXL345 `0x53` (or `0x1D` if SDO is high) and INA219 `0x40`; a DS18B20 should be discovered separately on OneWire.
8. If the ESP32 fails to advertise `MotorMonitor`, check that this exact Wi-Fi sketch was uploaded, the upload completed, the board reset, and the AP credentials in the sketch. The previous MPU serial sketch and ADXL calibration sketch do not create this AP.

### C. Connect and run the live dashboard

1. On the computer running Streamlit, join Wi-Fi **MotorMonitor** with password **motorlab24**. A “no internet” warning is expected.
2. Verify `http://192.168.4.1/health` returns `ok`. Then open `http://192.168.4.1/api/telemetry` and confirm JSON is changing and sensor booleans are true as expected.
3. From the repository root, activate `.venv` and run:

   ```bash
   streamlit run app.py
   ```

4. Open the URL Streamlit prints (usually `http://localhost:8501`). The Wi-Fi client polls the ESP32 automatically. The same computer must both run the dashboard and be on a network route that can reach the ESP32 endpoint.
5. To use another address, set `ESP32_TELEMETRY_URL` before launch, for example:

   ```bash
   export ESP32_TELEMETRY_URL=http://192.168.4.1/api/telemetry  # macOS/Linux
   $env:ESP32_TELEMETRY_URL = "http://192.168.4.1/api/telemetry" # PowerShell
   ```

6. Stop Streamlit with **Ctrl+C**. The web page alone does not keep the local server running if its terminal/process is stopped.

For a live presentation, keep the ESP32 powered, motor test safe, dashboard server running, and recording computer connected to the AP. Do not change network or USB settings during recording unless necessary.

## 7. Build and troubleshooting history

This section separates observed symptoms from likely causes; some root causes were not proven with a continuity diagram or reference instrument.

### Breadboard power and unreliable contacts

**Observed:** ESP32 `3V3` measured around 3.3 V, while wires expected to distribute it from breadboard rows did not show the same voltage. A sensor board without soldered header pins was pressed onto the board, and several jumpers were described as being in adjacent holes/rows.

**What changed:** the ESP32 was removed from the breadboard and wired directly with jumpers; the supply wiring was re-seated and 3.3 V then appeared on the rails and probe supply. Temperature readings resumed after correcting a data jumper placement.

**Lesson:** breadboard contact grouping, broken power rails, unbridged rail sections, and solderless sensor pads can all create an open circuit even when a wire looks aligned. Check electrical continuity/voltage at the component lead itself. Do not assume a neighboring hole is connected.

### MPU6050 was intermittent/not found; project changed to ADXL345

**Observed:** a bus-check sketch at times found common I²C devices at `0x40` (INA219) and `0x68` (MPU6050). The full sensor stream later reported `MPU6050: NOT FOUND` repeatedly, even after the board and wiring were rearranged and a replacement MPU was tried. The exact failure could have been an intermittent pin contact, power/ground, bus/data mismatch, wrong physical breakout pin, or another hardware issue; the evidence did not isolate one cause.

**Decision:** stop spending time on the MPU path and use the available ADXL345 as the accelerometer. The ADXL345 was later found at `0x53`. The active firmware only targets ADXL345; the older `esp32_motor_monitor` sketch still includes MPU6050 and is retained solely as legacy/reference code.

**Important I²C rule:** multiple sensors may share GPIO21 SDA and GPIO22 SCL, but each needs the correct power and common ground. SCL and SDA must not be swapped. Do not use an ADXL address to test an MPU or vice versa.

### DS18B20 discovery, read failures, and serial output

**Observed:** the bus test found one OneWire family-code `0x28` device, but some cycles printed “Device found, but temperature read failed.” Other runs reported temperatures about 29–33 °C. The probe's positive and ground were measured near 2.6–2.7 V during one wiring attempt even though the ESP32 itself measured about 2.73 V at its 3V3/GND; later the breadboard power distribution was corrected, the probe supply measured 3.3 V, and a misplaced ESP32 data wire was corrected.

**Likely checks:** verify probe pinout; verify it receives stable VDD/GND; make sure GPIO4 and probe DATA are on the same connected node; make sure the 4.7 kΩ resistor bridges DATA to 3V3 rather than sitting in series with DATA; inspect every jumper insertion and shared breadboard row. A data bus may occasionally discover a device yet fail to complete a valid temperature conversion.

**Unreadable/blank Serial Monitor:** the project saw non-ASCII output, partial lines, repeated boot text, and at times a blank Serial Monitor. That output alone did not prove a sensor failure. Confirm the correct sketch/port and 115200 baud for the current firmware, close competing serial clients, reset the ESP32, and check the Wi-Fi endpoint separately. The live dashboard is not fed by Serial Monitor.

### Arduino IDE and firmware compile/upload errors

- `Adafruit_MPU6050.h: No such file or directory` came from compiling the old MPU sketch without that library installed. The selected active sketch now uses `Adafruit_ADXL345_U.h`; do not add MPU code to the active build unless deliberately switching hardware again.
- ESP32 core 3.3.12 reported `String(float&, uint8_t&)` as ambiguous in JSON number formatting. The active firmware now casts decimal places to `unsigned int` before constructing `String`.
- An OpenOCD “unable to open ftdi device” happened after launching the IDE debugger. This board was uploaded successfully through esptool over its USB-to-serial adapter in a separate attempt. For normal updates select ESP32 Dev Module and press Upload; do not choose debug unless a compatible debug probe is attached/configured.
- The live serial test sketch once showed normal compile size and successful flash verification. That proves the ESP32 accepted that particular binary, not that the active Wi-Fi firmware has been flashed or that all sensors are calibrated.

### Dashboard transport changed from USB serial to Wi-Fi

The first integration used serial CSV, which exposed sensor values but also led to confusing boot diagnostics/garbled characters and required serial-port coordination. The requested dashboard direction was a direct Wi-Fi link. The active design therefore has firmware serve JSON and a separate background client poll HTTP. USB remains for programming and optional diagnostics; it is not the data stream used by Streamlit.

The AP's previous visibility/reachability was inconsistent. If the SSID is missing, diagnose the ESP32 AP (firmware, reset, power, configured SSID) before debugging Streamlit. If the AP is visible but dashboard says waiting, check that the *same computer running Streamlit* joined the ESP32 AP and that `/health` is reachable. Having internet Wi-Fi connected is not equivalent to joining the `MotorMonitor` AP for this default topology.

### Fuse and motor not turning

The owner reported a 500 mA fuse blowing, the motor voltage measuring 0 V at one point, and later the motor starting after the wiring was corrected. A blown fuse is an interruption by design; do not bypass it. Find the motor's actual startup/stall current and verify the battery pack, fuse, switch, wiring, and INA219 ratings before further power tests. A sensor that reports current on a logic bench setup is not evidence that motor current passes through its shunt.

## 8. Troubleshooting checklist

Work through this sequence; change one thing at a time and remove motor power before moving any motor wiring.

### Dashboard says “Waiting for the ESP32”

1. Confirm the ESP32 has the active Wi-Fi firmware, not the static calibration or legacy MPU serial firmware.
2. Confirm the ESP32 is powered and `MotorMonitor` is visible. Reset it and wait for boot/AP startup.
3. Connect the computer running Streamlit to `MotorMonitor` using `motorlab24`.
4. Open `http://192.168.4.1/health`. If it does not return `ok`, this is Wi-Fi/IP/firmware reachability; Streamlit is downstream of that.
5. Open `http://192.168.4.1/api/telemetry`. If `/health` works but JSON does not, check the active firmware's route and serial boot messages.
6. Check the dashboard endpoint in the sidebar and environment variable. Restart Streamlit after changing the variable.
7. If dashboard is on a different laptop from the ESP32 AP, that laptop also needs a route to the ESP32 (usually connect it to the AP). The AP is local-only.

The dashboard polls every 0.8 seconds. A single slow or missed request no longer changes the display immediately: it remains Connected for up to 4 seconds after the last HTTP response, then shows Reconnecting, and shows Waiting after 15 seconds without a response. Sensor data freshness is tracked separately: if no new `sample_id` arrives for 5 seconds, readings are labeled stale even if the ESP32 still answers HTTP. The latest sensor values remain visible but are explicitly labeled stale while offline. The dashboard watches `uptime_ms`; if it drops, it records an ESP32 restart and warns that a power dip or motor electrical noise is one possible cause. That warning is a diagnostic lead, not proof of the cause. If the AP vanishes, first check that macOS stays joined to `MotorMonitor` (it has no internet), and compare the dashboard's reboot warning with motor starts and ESP32 serial boot logs.

### ADXL345 missing

1. Check ADXL345 VCC-to-GND at the module, not merely at the ESP32 or rail.
2. Verify SDA to GPIO21, SCL to GPIO22, common ground, and snug/soldered header contact.
3. Run the I²C scan in the active firmware. `0x53` is typical with SDO low; `0x1D` with SDO high.
4. Disconnect other I²C devices temporarily if needed to isolate the bus. Reconnect the shared bus only after the accelerometer is found.
5. Check that firmware calls `Wire.begin(21, 22)` before scanning/initializing and that its selected ADXL address matches the scan.

### INA219 missing or current stays near zero

1. For I²C detection, check VCC, GND, SDA21, SCL22, and expected `0x40` address.
2. For current measurement, confirm motor battery positive runs through fuse and switch to VIN+, then VIN− to motor positive. Confirm motor negative returns to battery negative.
3. Verify common reference: battery negative, ESP32 GND, and INA219 logic GND join at a sound low-voltage ground connection.
4. Confirm with documentation that the breakout/shunt can safely measure the expected voltage/current. Do not assume current is calibrated because the I²C device is found.
5. If the motor current is above the module/shunt limit, stop; replace it with a correctly rated sensor rather than risking damage.

### DS18B20 missing or intermittently fails

1. Verify the exact three wires from the probe manufacturer/label; do not rely only on color.
2. Verify stable 3.3 V between VDD and GND at the probe.
3. Verify DATA reaches GPIO4 continuously and the 4.7 kΩ pull-up connects that same DATA node to 3.3 V.
4. Check the cable, connector, breadboard row continuity, resistor value, and power-rail split.
5. Use the bus-check/calibration diagnostic at 115200 baud to separate discovery from temperature-conversion failure.

### All three sensors missing after rewiring

Check the selected board sketch, board power, exact ESP32 pin labels, ground, and breadboard rail continuity first. If the ESP32 is not in the intended breadboard rows, do not assume its pins power those rows. Measure 3.3 V at each module. Then check I²C sensors using the address scan and DS18B20 separately on OneWire.

## 9. Accuracy, calibration, and responsible interpretation

Follow [`CALIBRATION.md`](../CALIBRATION.md) after mounting sensors in their final position. It covers the ADXL345 six-position static offset/scale method, INA219 comparisons against trusted voltage/current references, and DS18B20 comparison against a trusted thermometer. Keep raw readings and reference readings together with the final calibration constants.

Current limits/accuracy have not been demonstrated with a calibrated ammeter and the actual motor under representative load. Vibration RMS has not been compared with a calibrated accelerometer or vibration analyzer. Temperature needs a reference thermometer comparison. Report these as prototype sensor readings until these checks are completed.

The older `train_model.py` builds a Random Forest from a generated 8,000-row synthetic dataset. Its reported 92.15% holdout accuracy describes only a split of that synthetic generator. It is not a live model, it is not on the ESP32, and the current dashboard does not use its predictions. A genuine fault model requires repeatable, labelled measurements from the real motor under documented healthy and fault/load conditions, plus an independent evaluation set.

## 10. Handoff notes for the next person or coding agent

1. Start with this file and `README.md`; use `firmware/esp32_adxl345_stream/` as the active firmware.
2. Preserve the established pin contract unless the physical circuit and all docs are changed together: SDA21, SCL22, DS18B20 DATA4, LEDs25/26/27.
3. Preserve the JSON field names `vibration_rms_g`, `voltage_v`, `current_a`, `temperature_c`, `sample_id`, and `sensor_status` unless updating both firmware and Python consumer.
4. Do not infer calibration or fault labels from dashboard trend text. Do not describe synthetic classifier accuracy as real fault detection.
5. Do not run the motor unfused, over the INA219 rating, from the ESP32, or through the breadboard. Verify the protection and current path before load experiments.
6. Keep user-facing setup beginner-friendly: provide exact IDE board/port/library choices and show the local dashboard URL; point to `/health` and `/api/telemetry` to separate network issues from UI issues.
7. Before saying a new version works live, compile/flash the active firmware, confirm AP visibility, fetch `/health` and `/api/telemetry`, and observe the dashboard receiving changing sample IDs. A serial compile or successful upload alone does not demonstrate the entire system.
8. The Wi-Fi AP uses an example password (`motorlab24`) and has no authentication on telemetry endpoints. It is intended for a local demonstration network, not an exposed or production deployment. Change credentials and add suitable network security before wider deployment.
