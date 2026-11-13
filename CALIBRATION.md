# Sensor calibration and accuracy check

## Current status

The firmware defaults to zero offsets and unity scale factors for all sensors. The dashboard does not secretly adjust or smooth readings. Earlier bench logs showed a stable-looking temperature around 29–33 °C, small no-load INA219 readings near zero, and occasional missing/invalid sensor readings. Those observations show that data can arrive; they do **not** establish measurement accuracy. There is no reference-instrument calibration record yet.

Calibrate the sensors after they are firmly mounted in their final positions. A change in accelerometer mounting or mechanical stress can change the result.

## ADXL345: six-position static calibration

1. Disconnect motor power. Leave the ADXL345 connected to the ESP32 at 3V3, GND, SDA GPIO21, and SCL GPIO22.
2. Open `firmware/adxl345_static_calibration/adxl345_static_calibration.ino`, upload it, and open Serial Monitor at 115200 baud to collect the calibration values. The live dashboard uses Wi-Fi and does not consume the serial port.
3. Put the board still on a level surface. Orient the sensor so X points up, wait for readings to settle, and record/average at least 30 consecutive `ax_g` values. Then point X down and record/average 30 values. Repeat for Y up/down and Z up/down. Keep each orientation steady; gravity should be about +1 g or −1 g on the pointed axis and near 0 g on the other axes.
4. For each axis calculate from the two means:

   ```text
   bias_g  = (mean_plus_1g + mean_minus_1g) / 2
   scale   = 2 / (mean_plus_1g - mean_minus_1g)
   ```

   For example, if X reads +1.04 g and −0.98 g, X bias is 0.03 g and X scale is about 0.9901.
5. Copy the six results into `ADXL_BIAS_X_G`, `ADXL_BIAS_Y_G`, `ADXL_BIAS_Z_G` and `ADXL_SCALE_X`, `ADXL_SCALE_Y`, `ADXL_SCALE_Z` near the top of `firmware/esp32_adxl345_stream/esp32_adxl345_stream.ino`. Upload the streaming sketch again.
6. Repeat the six orientations to verify calibrated means near +1.00/−1.00 g and near zero on the two perpendicular axes. Keep the result sheet with the project.

This corrects static offset and scale in the acceleration samples used for the short-window RMS calculation. It does not calibrate vibration frequency response, mounting resonance, or motor-fault thresholds. The current stream is a basic trend measurement and should not be described as an industrial vibration analyzer.

## INA219: voltage and current checks

1. Check the exact breakout board's shunt marking/rating and compare it with the motor's safe current. `R100` commonly denotes a 0.10 Ω shunt, but confirm the board documentation. The Adafruit library's `begin()` uses its 32 V / 2 A calibration, which assumes a 0.10 Ω shunt. If your board differs, do not treat current as calibrated until its shunt and library setting match. Do not run motor current through a shunt, fuse, jumper, or breadboard beyond its rating.
2. With motor supply disconnected, power the ESP32/sensors only. Compare the INA219 voltage reading with a trusted digital multimeter measuring VIN− to INA219 GND. Repeat at a second safe voltage if possible. For two readings, calculate `scale = (reference2 - reference1) / (reported2 - reported1)` and `offset = reported1 - reference1 / scale`. Enter them in `INA_BUS_VOLTAGE_SCALE` and `INA_BUS_VOLTAGE_OFFSET_V` in the firmware.
3. Check current zero with no load current through the INA219. Record the stable reading as `INA_CURRENT_OFFSET_A`. Do not assume a tiny negative value is real reverse current.
4. For current scale, use a known, safe DC load and a trusted ammeter **in series** with that load, or a current-limited bench supply with a verified current readout. At a known nonzero current, calculate `scale = reference_current / (reported_current - INA_CURRENT_OFFSET_A)` and enter it in `INA_CURRENT_SCALE`. Compare at several safe points. Never put a meter in current mode directly across a battery or supply.
5. Correct wiring must put the measured load path through INA219 VIN+ and VIN−, with common ground between the ESP32 and the measurement system. The INA219 bus-voltage field is VIN− relative to ground; it is not automatically the battery voltage on VIN+.

Record reference, displayed, difference, and percent difference at each point. If the error changes with load, investigate shunt value/rating, module calibration, wiring/contact resistance, and sensor saturation before applying a single software correction.

## DS18B20 temperature check

Compare the probe against a trusted thermometer in a well-stirred stable bath at two or more temperatures. Keep the probe tips near each other without touching the container; wait for both readings to stabilize. Calculate `offset = reference_temperature - reported_temperature` and enter the stable average offset in `DS18B20_OFFSET_C`. If the difference changes significantly across the range, an offset alone is not a valid calibration. A genuine DS18B20 is specified to ±0.5 °C over −10 °C to +85 °C, but a waterproof probe assembly, wiring, installation, and clones can add error. Do not average away `nan`, disconnects, or sudden spikes; fix intermittent wiring first.

## Dashboard interpretation

- The dashboard displays four ESP32 Wi-Fi telemetry fields: vibration RMS (g), INA219 bus voltage (V), INA219 current (A), and DS18B20 temperature (°C).
- Missing sensor values are returned as JSON `null` and shown as unavailable for that channel; valid readings from the same sample remain visible.
- All correction constants in the firmware start at neutral values (zero offsets and scale 1). After reference checks, the firmware applies the constants you enter before publishing telemetry. The dashboard displays those transmitted values as-is and never adds its own correction.
- Save a known-good baseline with motor off and with the motor running safely at its ordinary operating condition. Change one test condition at a time and compare trends. A fault classifier needs labeled, repeatable motor measurements; synthetic model scores do not establish real fault-detection performance.
