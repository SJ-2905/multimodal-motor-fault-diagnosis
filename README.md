# Multimodal electric motor monitoring prototype

This repository contains the ESP32 firmware and local dashboard for a small motor condition monitoring project. The active configuration uses an **ADXL345 accelerometer**, an **INA219 voltage/current monitor**, and a **DS18B20 temperature probe**. The ESP32 creates a local Wi-Fi access point and serves readings over HTTP. A Streamlit app on a nearby computer displays the live values and recent trends.

> This is a prototype for learning and demonstration. It is not an industrial vibration analyzer, calibrated measurement instrument, motor protection system, or validated fault diagnosis system. The separate Random Forest files in this repository use synthetic data; their score must not be presented as real-world fault-detection accuracy.

## Fast setup

### 1. Flash the ESP32

Open [`firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino`](firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino) in Arduino IDE. Install **Adafruit ADXL345**, **Adafruit Unified Sensor**, **Adafruit INA219**, **OneWire**, and **DallasTemperature** from Library Manager. Select **ESP32 Dev Module** and the correct USB serial port, then use the **Upload** arrow. The serial port is needed to flash firmware and inspect diagnostics; live dashboard data uses Wi-Fi.

The firmware's default access point is:

| Setting | Value |
|---|---|
| Wi-Fi name | `MotorMonitor` |
| Password | `motorlab24` |
| ESP32 address | `192.168.4.1` |
| Health URL | `http://192.168.4.1/health` |
| Telemetry URL | `http://192.168.4.1/api/telemetry` |

### 2. Install and start the dashboard

Install dependencies while the computer has internet access, then connect it to the ESP32 access point. The access point is local-only and does not provide internet.

**macOS / Linux**

```bash
git clone https://github.com/SJ-2905/multimodal-motor-fault-diagnosis.git
cd multimodal-motor-fault-diagnosis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

**Windows PowerShell**

```powershell
git clone https://github.com/SJ-2905/multimodal-motor-fault-diagnosis.git
cd multimodal-motor-fault-diagnosis
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Join **MotorMonitor** Wi-Fi on the same computer, then open the local URL printed by Streamlit (usually `http://localhost:8501`). The access point is local-only and has no internet; keep the computer connected to it while monitoring (macOS may prefer another saved network). The dashboard retries automatically, tolerates brief missed polls, shows **Reconnecting** before declaring the ESP32 unreachable, and labels retained values as stale. It also distinguishes an active Wi-Fi link from fresh sensor samples: samples older than 5 seconds are marked stale. The dashboard reports ESP32 uptime resets observed during the current session. A reset near motor startup can point to a supply dip or electrical noise, but the dashboard cannot diagnose the cause on its own. To stop the app, press **Ctrl+C** in the terminal running Streamlit.

If a fresh clone does not contain the Wi-Fi dashboard files described here, fetch the latest project changes from the maintainer before continuing.

## Current sensor wiring

All sensor logic wiring is for an **ESP32 DevKit V1**. The ADXL345 and INA219 share the same I²C bus. ESP32 `3V3` and `GND` power the sensor logic; never use these pins or breadboard power rails to run the 12 V motor.

| Device | Module pin | ESP32 / connection |
|---|---|---|
| ADXL345 | VCC | 3V3 |
| ADXL345 | GND | GND |
| ADXL345 | SDA | GPIO21 / D21 |
| ADXL345 | SCL | GPIO22 / D22 |
| INA219 logic | VCC | 3V3 |
| INA219 logic | GND | GND |
| INA219 logic | SDA | GPIO21 / D21 (shared I²C) |
| INA219 logic | SCL | GPIO22 / D22 (shared I²C) |
| DS18B20 probe | VDD / red, if verified for this cable | 3V3 |
| DS18B20 probe | GND / black, if verified for this cable | GND |
| DS18B20 probe | DATA / yellow, if verified for this cable | GPIO4 / D4 |
| Pull-up resistor | 4.7 kΩ, one side | DS18B20 DATA / GPIO4 node |
| Pull-up resistor | other side | 3V3 |

Probe wire colors are common for the probe used in this build, not a universal standard. Check the exact probe's labeling or datasheet before applying power. For solderless breadboards, five holes on one numbered row within A–E are connected together; likewise F–J; the center trench isolates the two halves. Power rails may be split partway along the board. Verify continuity and voltage with a meter instead of assuming a rail is continuous.

### Motor current path

The INA219 only reports motor current when the motor supply current passes through its screw-terminal path **VIN+ → VIN−**. The logic header still connects to ESP32 3V3, GND, SDA, and SCL.

```text
Battery positive → correctly rated fuse → switch → INA219 VIN+
INA219 VIN− → motor positive
Motor negative → battery negative
Battery negative/common reference → INA219 GND and ESP32 GND
```

Use suitable wire and rated terminals for the motor current path; do not route motor current through a breadboard, the ESP32, or its 3V3/GND rails. The right fuse depends on motor startup/stall current, wire, battery, and sensor/shunt ratings. A 500 mA fuse reportedly blew in this build; do not bypass it or test the motor unfused. Do not deliberately stall or mechanically overload the motor without a controlled, rated fixture. See [the handoff guide](docs/PROJECT_HANDOFF.md#motor-power-and-current-safety).

## What the software reports

The dashboard presents four values transmitted by the firmware:

- `vibration_rms_g`: short-window variation in the ADXL345's three acceleration axes, after subtracting each axis's mean for that window; the API stores this in g, while the dashboard displays the converted m/s² value.
- `voltage_v`: INA219 bus voltage at VIN− relative to GND; this is not necessarily battery voltage at VIN+.
- `current_a`: INA219 current, meaningful as motor current only when wired in series with the motor supply path and when the module/shunt remain within rating.
- `temperature_c`: DS18B20 probe measurement.

The dashboard plots the last 120 samples from a bounded 600-sample history. It compares medians of the previous and latest six readings for simple directional trend labels. Those labels are descriptive only, not fault limits or diagnoses. If the DS18B20 has produced one valid reading, the firmware holds that temperature through probe disconnects; the shown temperature can therefore be old until the probe resumes updating.

The ESP32 also has three status LED outputs configured on GPIO25 (green), GPIO26 (yellow), and GPIO27 (red). Prototype vibration thresholds are 30 m/s² for yellow and 35 m/s² for red. Red also indicates an ADXL345 or INA219 fault; yellow also indicates INA219 bus voltage below 1 V when there is no red condition. Green means the ADXL345/INA219 checks pass, vibration is below 30 m/s², and INA219 bus voltage is at least 1 V. DS18B20 temperature holds its last valid reading and does not control the LEDs. A single transient ADXL345 read miss is tolerated. Sensor initialization retries every 2 seconds. These thresholds are demonstration indicators, not calibrated or validated motor-fault limits. The dashboard link is Wi‑Fi (`MotorMonitor`), not Bluetooth.

## Further documentation

- [Project handoff, architecture, build history, troubleshooting, and setup for users/agents](docs/PROJECT_HANDOFF.md)
- [Sensor calibration and accuracy-check procedure](CALIBRATION.md)
- [ESP32 streaming firmware](firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino)
- [ADXL345 static calibration sketch](firmware/adxl345_static_calibration/adxl345_static_calibration.ino)
- [Streamlit dashboard](app.py)
- [Wi-Fi telemetry client](wifi_monitor.py)
