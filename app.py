import time
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import streamlit as st

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

st.set_page_config(page_title="Motor Fault Diagnosis", page_icon="⚙️", layout="wide")
st.title("⚙️ Edge-AI Electric Motor Fault Diagnosis")
st.caption("Random Forest trained on synthetic data. Synthetic test metrics are not real-world motor accuracy.")

FEATURES = ["Vibration RMS (g)", "Voltage (V)", "Current (A)", "Temperature (°C)"]
LABELS = ["Normal", "Mechanical anomaly", "Electrical anomaly", "Thermal anomaly"]
ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "motor_fault_random_forest.joblib"
METRICS_PATH = ROOT / "reports" / "training_metrics.json"

if not MODEL_PATH.exists():
    st.error("Trained model file not found. Run `python train_model.py` in this project folder.")
    st.stop()

model = joblib.load(MODEL_PATH)
with METRICS_PATH.open("r", encoding="utf-8") as f:
    training_metrics = json.load(f)
synthetic_score = training_metrics["synthetic_holdout_accuracy"]

def read_latest_serial_row(port_name: str, baud_rate: int, timeout_s: float = 0.35):
    """Read serial lines and return the latest valid four-number CSV row."""
    if serial is None:
        raise RuntimeError("pyserial is not installed. Run: python -m pip install pyserial")
    latest = None
    valid_count = 0
    with serial.Serial(port=port_name, baudrate=baud_rate, timeout=timeout_s) as ser:
        # Do not reset ESP32 on every Streamlit rerun; allow a short settling period.
        ser.dtr = False
        ser.rts = False
        deadline = time.time() + timeout_s + 0.15
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="ignore").strip()
                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 4:
                    continue
                vals = [float(p) for p in parts]
                if not all(np.isfinite(vals)):
                    continue
                # Broad sanity bounds catch status text and malformed data.
                if not (0.0 <= vals[0] <= 5.0 and 0.0 <= vals[1] <= 60.0
                        and 0.0 <= vals[2] <= 50.0 and -20.0 <= vals[3] <= 150.0):
                    continue
                latest = vals
                valid_count += 1
            except (ValueError, UnicodeDecodeError):
                continue
    if latest is None:
        raise RuntimeError(
            "No valid four-value CSV row received. Expected: vibration_g,voltage_V,current_A,temperature_C"
        )
    return latest, valid_count

with st.sidebar:
    st.header("Dashboard controls")
    source = st.radio("Data source", ["Simulation", "ESP32 live (USB serial)", "Custom readings"])
    port_options = []
    if list_ports is not None:
        try:
            port_options = [p.device for p in list_ports.comports()]
        except Exception:
            port_options = []
    if source == "ESP32 live (USB serial)":
        st.subheader("ESP32 serial settings")
        default_port = "COM5" if "COM5" in port_options or not port_options else port_options[0]
        if port_options:
            port_name = st.selectbox("Serial port", port_options, index=port_options.index(default_port))
        else:
            port_name = st.text_input("Serial port", value="COM5", help="Example: COM5 on Windows")
        baud_rate = st.selectbox("Baud rate", [115200, 9600, 57600, 230400], index=0)
        st.caption("Close Arduino Serial Monitor before using this mode.")
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_seconds = st.slider("Refresh interval (seconds)", 1, 5, 2)
    st.divider()
    st.subheader("Alert thresholds")
    vib_limit = st.number_input("Vibration limit (g)", 0.05, 2.0, 0.45, 0.05)
    voltage_low = st.number_input("Low voltage limit (V)", 1.0, 20.0, 10.5, 0.5)
    voltage_high = st.number_input("High voltage limit (V)", 2.0, 30.0, 13.5, 0.5)
    current_limit = st.number_input("Current limit (A)", 0.1, 10.0, 1.30, 0.1)
    temp_limit = st.number_input("Temperature limit (°C)", 20.0, 100.0, 50.0, 1.0)

rng = np.random.default_rng()
scenarios = {
    "Normal operation": ([0.18, 12.0, 0.75, 34.0], [0.02, 0.12, 0.04, 0.8]),
    "Mechanical anomaly": ([0.72, 12.0, 0.98, 39.0], [0.035, 0.15, 0.06, 1.0]),
    "Electrical anomaly": ([0.27, 14.0, 1.65, 43.0], [0.025, 0.18, 0.08, 1.2]),
    "Thermal anomaly": ([0.28, 12.0, 0.92, 59.0], [0.025, 0.12, 0.05, 1.3]),
}

values = None
if source == "ESP32 live (USB serial)":
    st.subheader("ESP32 live connection")
    if serial is None:
        st.error("pyserial is missing. Install it with `python -m pip install pyserial`.")
    else:
        try:
            values, rows_read = read_latest_serial_row(port_name, baud_rate)
            st.success(f"Connected to {port_name} at {baud_rate} baud. Received {rows_read} valid row(s) this refresh.")
            st.caption("CSV order: Vibration_RMS_g,Voltage_V,Current_A,Temperature_C")
            st.session_state["last_live_values"] = values
        except Exception as exc:
            st.warning(f"Could not read live sensor data: {exc}")
            if "last_live_values" in st.session_state:
                values = st.session_state["last_live_values"]
                st.info("Showing the last successfully received reading until a new valid row arrives.")
            else:
                st.info("Waiting for the first valid ESP32 reading. Check the wiring, COM port, baud rate and firmware output.")
                st.stop()
elif source == "Custom readings":
    st.subheader("Custom sensor readings")
    cols = st.columns(4)
    defaults = [0.25, 12.0, 0.8, 35.0]
    ranges = [(0.0, 1.5, 0.01), (0.0, 24.0, 0.1), (0.0, 5.0, 0.05), (10.0, 100.0, 0.5)]
    values = [
        c.slider(name, min_value=rg[0], max_value=rg[1], value=d, step=rg[2])
        for c, name, d, rg in zip(cols, FEATURES, defaults, ranges)
    ]
else:
    scenario = st.selectbox(
        "Simulation condition",
        ["Normal operation", "Mechanical anomaly", "Electrical anomaly", "Thermal anomaly"]
    )
    means, stds = scenarios[scenario]
    values = rng.normal(means, stds).tolist()
    values = [max(0.01, values[0]), max(0.1, values[1]), max(0.01, values[2]), max(10.0, values[3])]

values = [float(v) for v in values]
row = pd.DataFrame([values], columns=FEATURES)
pred = model.predict(row)[0]
probs = model.predict_proba(row)[0]
prob_df = pd.DataFrame({"Condition": model.classes_, "Model score (%)": probs * 100}).sort_values(
    "Model score (%)", ascending=False
)

warnings = []
if values[0] > vib_limit:
    warnings.append(f"Vibration above limit: {values[0]:.2f} g")
if values[1] < voltage_low:
    warnings.append(f"Voltage below limit: {values[1]:.2f} V")
if values[1] > voltage_high:
    warnings.append(f"Voltage above limit: {values[1]:.2f} V")
if values[2] > current_limit:
    warnings.append(f"Current above limit: {values[2]:.2f} A")
if values[3] > temp_limit:
    warnings.append(f"Temperature above limit: {values[3]:.1f} °C")

st.subheader("Sensor readings")
cols = st.columns(4)
units = ["g", "V", "A", "°C"]
for col, name, value, unit in zip(cols, FEATURES, values, units):
    col.metric(name, f"{value:.3f} {unit}")

st.subheader("Fault detection")
left, right = st.columns(2)
with left:
    if warnings:
        st.error("Threshold alert: abnormal reading(s)")
        for warning in warnings:
            st.write("- " + warning)
    else:
        st.success("No configured threshold exceeded")
with right:
    if pred == "Normal":
        st.success(f"Random Forest prediction: {pred}")
    else:
        st.warning(f"Random Forest prediction: {pred}")

st.subheader("Model scores (synthetic demonstration)")
st.bar_chart(prob_df.set_index("Condition"))

if "history_v2" not in st.session_state:
    st.session_state.history_v2 = []
st.session_state.history_v2.append({
    "Time": pd.Timestamp.now().strftime("%H:%M:%S"),
    **dict(zip(FEATURES, values)),
    "ML prediction": pred,
    "Threshold alert": "Yes" if warnings else "No"
})
st.session_state.history_v2 = st.session_state.history_v2[-120:]
history = pd.DataFrame(st.session_state.history_v2)

st.subheader("Sensor trends")
st.line_chart(history.set_index("Time")[["Vibration RMS (g)"]])
st.line_chart(history.set_index("Time")[["Voltage (V)", "Current (A)", "Temperature (°C)"]])
with st.expander("Recent readings and predictions"):
    st.dataframe(history.iloc[::-1], use_container_width=True)

st.caption(f"Synthetic-data test score: {synthetic_score * 100:.2f}% — not real-world accuracy.")
if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
