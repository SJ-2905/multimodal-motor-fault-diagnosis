# Multimodal Edge-AI Electric Motor Fault Diagnosis

A student project prototype for monitoring electric-motor condition using **vibration, electrical and thermal measurements**. The prototype combines an ESP32 sensor node, a Python/Streamlit dashboard and a Random Forest demonstration classifier.

> **Important:** The included classifier is trained on generated synthetic data. Its reported test score measures performance on a held-out split from that same synthetic generator. It is not evidence of real-world fault-detection accuracy, and this prototype is not a certified safety or protection system.

## Contents

- ESP32 firmware for MPU6050, INA219 and DS18B20 sensor acquisition.
- Streamlit dashboard with simulation, manual-entry and ESP32 USB-serial modes.
- Synthetic dataset with 8,000 example records.
- Trained Random Forest model and synthetic holdout evaluation reports.
- Reproducible training script.

## 1. System architecture

```text
Motor / test rig
    |
    +-- MPU6050  -> vibration RMS estimate
    +-- INA219   -> bus voltage and current
    +-- DS18B20  -> temperature
             |
           ESP32
             | USB serial, 115200 baud
             | CSV: vibration_g,voltage_V,current_A,temperature_C
             v
       Python / Streamlit
             |
       Random Forest model
             |
       Normal / Mechanical / Electrical / Thermal
```

The model currently executes on the **laptop**, not on the ESP32. The ESP32 performs sensor acquisition and sends measurements to the dashboard.

## 2. Hardware

### Required components

- ESP32 DevKit V1
- MPU6050 / GY-521 accelerometer module
- INA219 current/voltage sensor module
- DS18B20 temperature sensor
- 4.7 kΩ resistor for the DS18B20 data pull-up
- DC motor and a suitably rated, protected motor power/driver arrangement
- Jumper wires and USB cable

No acoustic sensor is used in this project.

### ESP32 pin connections

| Sensor pin | ESP32 pin |
|---|---|
| MPU6050 VCC | 3V3 |
| MPU6050 GND | GND |
| MPU6050 SDA | GPIO21 |
| MPU6050 SCL | GPIO22 |
| INA219 VCC | 3V3 |
| INA219 GND | GND |
| INA219 SDA | GPIO21 |
| INA219 SCL | GPIO22 |
| DS18B20 VDD | 3V3 |
| DS18B20 GND | GND |
| DS18B20 DATA | GPIO4 |
| 4.7 kΩ resistor | Between DS18B20 DATA and 3V3 |

The MPU6050 and INA219 share the I²C bus. The DS18B20 uses a separate 1-Wire data pin. Check the pin labels and datasheet for your exact sensor modules; do not assume the pin order of a bare TO-92 DS18B20 package.

### Motor and INA219 safety

- Disconnect USB and the motor battery before changing wiring.
- Do not connect a motor directly to an ESP32 GPIO or 3V3 pin.
- Do not connect a battery to the ESP32 3V3 pin.
- Use a motor driver and a separate motor supply rated for the motor's voltage and startup/stall current.
- Verify the INA219 module and shunt ratings against the motor's expected current before inserting it into the motor current path.
- Use appropriate battery protection and a fuse. Do not deliberately stall or overload the motor.
- The motor supply, driver and INA219 current path must be designed for the actual motor. This repository does not specify a battery because the motor electrical ratings have not been provided.

## 3. Flash the ESP32 firmware

### Arduino IDE setup

1. Install Arduino IDE.
2. Install ESP32 board support using Boards Manager if it is not already installed.
3. Select **Tools → Board → esp32 → ESP32 Dev Module**.
4. Connect the ESP32 over USB and select its COM port under **Tools → Port** (the previously used port was COM5; yours may differ).
5. Set **Tools → Upload Speed → 115200** if uploads are unreliable.
6. Open `firmware/esp32_motor_monitor/esp32_motor_monitor.ino`.

### Install Arduino libraries

In **Sketch → Include Library → Manage Libraries**, install:

- Adafruit MPU6050
- Adafruit Unified Sensor
- Adafruit INA219
- OneWire
- DallasTemperature

### Upload

1. Disconnect motor power while setting up and testing sensors.
2. Connect the three sensors according to the table above.
3. Close Serial Monitor before uploading.
4. Click **Upload**.
5. Open Serial Monitor at **115200 baud** to inspect the startup diagnostics.
6. The firmware emits one four-number CSV row per sample only when all three sensors initialize.

Expected data-line format:

```text
0.0251,12.104,0.2450,29.50
```

Field order:

1. Vibration RMS in g
2. INA219 bus voltage in V
3. INA219 current in A
4. DS18B20 temperature in °C

The first CSV header line is ignored by the dashboard parser. Diagnostic lines beginning with `#` are also ignored.

**Vibration feature note:** The example firmware estimates vibration RMS from the standard deviation of acceleration-magnitude samples over a short window, with the mean/static component removed. It is a prototype feature, not a calibrated vibration instrument or a frequency-domain bearing diagnostic.

**INA219 note:** `getBusVoltage_V()` reports the INA219 bus voltage at VIN- relative to ground. Correct current measurement requires the module to be wired in the current path according to its documentation and ratings.

## 4. Set up the Python dashboard (Windows)

Install Python 3.10 or newer. During installation, enable **Add Python to PATH** if using the standard Windows installer.

Open PowerShell in the repository root (the folder containing `app.py`) and run:

```powershell
py -m venv .venv
```

Activate the virtual environment:

```powershell
& .\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this for the current PowerShell process only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& .\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the dashboard:

```powershell
streamlit run app.py
```

Open the URL printed in the terminal, normally:

```text
http://localhost:8501
```

Stop Streamlit with **Ctrl+C** in the PowerShell terminal.

### macOS / Linux alternative

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

## 5. Dashboard modes

Use the **Data source** selector in the sidebar:

### Simulation

Generates example values for normal, mechanical, electrical and thermal scenarios. Use this to explore the dashboard without hardware.

### ESP32 live (USB serial)

1. Upload and run the ESP32 firmware.
2. Close Arduino Serial Monitor and Serial Plotter. Only one application can normally own a serial port at a time.
3. Start the Streamlit dashboard.
4. Select **ESP32 live (USB serial)**.
5. Select the ESP32 COM port (for example COM5) and **115200** baud.
6. Wait for valid four-number CSV lines.

The expected line is:

```text
vibration_rms_g,voltage_v,current_a,temperature_c
```

The dashboard ignores boot text, status messages and CSV header lines that do not contain exactly four numeric values.

### Custom readings

Use the sliders to enter example sensor readings manually.

## 6. Retrain the synthetic model

The checked-in model artifact is at:

```text
models/motor_fault_random_forest.joblib
```

To regenerate the synthetic dataset and retrain:

```powershell
python train_model.py
```

This writes/updates:

- `data/synthetic_motor_fault_dataset.csv`
- `models/motor_fault_random_forest.joblib`
- `reports/training_metrics.json`
- `reports/confusion_matrix.csv`
- `reports/classification_report.txt`

The synthetic data contains 8,000 rows (2,000 per class) with these features:

- Vibration RMS (g)
- Voltage (V)
- Current (A)
- Temperature (°C)

Classes:

- Normal
- Mechanical anomaly
- Electrical anomaly
- Thermal anomaly

The dataset is generated from illustrative assumed distributions. Synthetic test scores can be high because train and test examples come from the same generator. **Do not present the synthetic accuracy as real-world motor accuracy.**

## 7. Repository structure

```text
multimodal-motor-fault-diagnosis/
├── app.py
├── train_model.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── ESP32_SERIAL_FORMAT_EXAMPLE.txt
├── firmware/
│   └── esp32_motor_monitor/
│       └── esp32_motor_monitor.ino
├── data/
│   └── synthetic_motor_fault_dataset.csv
├── models/
│   └── motor_fault_random_forest.joblib
└── reports/
    ├── classification_report.txt
    ├── confusion_matrix.csv
    └── training_metrics.json
```

## 8. Troubleshooting

| Problem | What to check |
|---|---|
| COM port not listed | Reconnect USB, check Device Manager, install the correct USB-to-serial driver if needed, restart Arduino IDE |
| `PermissionError` / port busy | Close Arduino Serial Monitor, Serial Plotter and other serial applications |
| No valid serial CSV received | Confirm firmware is running at 115200 baud and prints four comma-separated numeric fields ending with a newline |
| MPU6050 not found | Check 3V3, GND, SDA GPIO21, SCL GPIO22 and I²C address/wiring |
| INA219 not found | Check shared I²C wiring, power, ground and module connections |
| DS18B20 not found | Check GPIO4 data wiring, common ground and 4.7 kΩ pull-up to 3V3 |
| Dashboard says model missing | Run the app from the extracted repository root and verify `models/motor_fault_random_forest.joblib` exists |
| Dependency import error | Activate `.venv` and run `python -m pip install -r requirements.txt` again |

## 9. Limitations and next research steps

- Synthetic training data is for software demonstration and pipeline development only.
- Fault classes are illustrative labels; real mechanical/electrical/thermal faults can overlap and require careful experimental definitions.
- The current model is laptop-hosted. It is not deployed to ESP32.
- No real motor fault dataset or independent real-world test results are included.
- The vibration RMS estimate and electrical measurements require calibration and validation.
- Alert thresholds in the dashboard are configurable demonstration thresholds, not certified protection limits.

Recommended next steps:

1. Validate all three sensors together on the actual ESP32.
2. Verify sensor units, calibration, mounting and INA219 current-path wiring.
3. Collect repeated, labelled data under safe normal and controlled test conditions.
4. Split training and test data by separate runs/operating sessions to reduce leakage.
5. Evaluate on a held-out real dataset and report per-class precision, recall, F1 and confusion matrix.
6. Only then consider model quantization or deployment on an edge-capable device.

## 10. Git and GitHub commands

Create a new empty repository on GitHub, then from this project folder run:

```powershell
git init
git add .
git commit -m "Initial release: multimodal motor fault diagnosis"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/multimodal-motor-fault-diagnosis.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username and use the URL of your newly created repository.

To publish later changes:

```powershell
git add .
git commit -m "Describe your update"
git push
```

Do not commit `.venv/`, API keys, passwords or private credentials. The `.gitignore` excludes common local environment and editor files.
