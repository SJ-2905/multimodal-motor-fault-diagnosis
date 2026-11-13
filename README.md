# ESP32 motor sensor live monitor

The ESP32 reads an ADXL345 accelerometer, INA219 voltage/current sensor, and DS18B20 temperature probe. It creates a private Wi-Fi access point and serves the latest sensor sample over HTTP. The Streamlit dashboard connects directly to that ESP32 network; it does not read Arduino Serial Monitor output.

The dashboard shows the four firmware measurements without smoothing, clipping, or hidden calibration. This does not by itself establish measurement accuracy; see [CALIBRATION.md](CALIBRATION.md).

> **Prototype limitation:** the repository's Random Forest model and sample dataset are synthetic demonstrations. The live dashboard does not show its predictions as real motor-fault results.

## Hardware wiring

| Device | Pin | ESP32 DevKit V1 |
|---|---|---|
| ADXL345 | VCC | 3V3 |
| ADXL345 | GND | GND |
| ADXL345 | SDA | GPIO21 / D21 |
| ADXL345 | SCL | GPIO22 / D22 |
| INA219 | VCC | 3V3 |
| INA219 | GND | GND |
| INA219 | SDA | GPIO21 / D21 (shared I²C bus) |
| INA219 | SCL | GPIO22 / D22 (shared I²C bus) |
| DS18B20 | VDD (red) | 3V3 |
| DS18B20 | GND (black) | GND |
| DS18B20 | DATA (yellow) | GPIO4 / D4 |
| 4.7 kΩ pull-up | one leg | DS18B20 DATA / GPIO4 node |
| 4.7 kΩ pull-up | other leg | 3V3 |

Keep the motor battery/current path separate from ESP32 3V3. The INA219 measures motor current only when the motor supply current passes through its VIN+ and VIN− terminals, within the exact breakout's voltage, current, and shunt limits. Do not power the motor through the ESP32 or breadboard rails.

## ESP32 Wi-Fi firmware

Open `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino` in Arduino IDE. Install these libraries in Library Manager:

- Adafruit ADXL345
- Adafruit Unified Sensor
- Adafruit INA219
- OneWire
- DallasTemperature

Select **ESP32 Dev Module** and the ESP32's USB serial port, then upload the sketch once over USB. USB is used to flash the firmware; live sensor data flows over Wi-Fi afterward.

The ESP32 starts an access point with:

- **Wi-Fi name:** `MotorMonitor`
- **Password:** `motorlab24`
- **Telemetry endpoint:** `http://192.168.4.1/api/telemetry`

In macOS Wi-Fi settings, join `MotorMonitor`. The dashboard polls the fixed local endpoint and reconnects automatically. Keep the dashboard running on the same Mac. The Mac may report that this Wi-Fi has no internet; that is expected for this direct local link. The endpoint returns JSON with a sample ID, the four measurements, and sensor availability. Serial Monitor is not the data transport.

The access-point name and password can be changed near the top of the firmware. If changed, update `ESP32_TELEMETRY_URL` in the dashboard environment only if the ESP32's local address is also changed; with the default SoftAP the address remains `192.168.4.1`.

## Dashboard setup

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

The dashboard automatically polls the ESP32 over HTTP on Wi-Fi. It reconnects after temporary Wi-Fi loss and shows an explicit instruction to join the ESP32 network when the endpoint is unavailable. It displays vibration RMS (g), INA219 bus voltage (V), INA219 current (A), and probe temperature (°C), with separate recent trend plots. The line plots retain the latest 120 samples from a bounded 600-sample history.

## Measurement meaning

- `vibration_rms_g` is a short-window acceleration-variation estimate from the ADXL345. It is a basic trend indicator, not calibrated bearing diagnostics or industrial vibration analysis.
- `voltage_v` is INA219 bus voltage measured at VIN− relative to ground.
- `current_a` is meaningful as motor current only when motor supply current actually passes through INA219 VIN+ to VIN−.
- `temperature_c` is the DS18B20 probe reading.
- Missing sensor values are returned as JSON `null` and shown as unavailable without hiding the other valid channels.

## Motor safety

Disconnect motor power while rewiring. Do not bypass a blown fuse or run without suitable overcurrent protection. Confirm the battery pack's fully charged voltage, motor stall current, fuse rating, motor driver rating, wiring, and INA219 breakout/shunt rating before powering the motor. Do not deliberately stall or overload the motor without a properly rated, controlled test fixture.

This prototype is not a motor protection or safety device.
