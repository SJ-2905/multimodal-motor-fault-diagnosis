from __future__ import annotations

import math
import os
from statistics import median

import pandas as pd
import streamlit as st

from wifi_monitor import WifiTelemetryClient


ESP32_ENDPOINT = os.getenv("ESP32_TELEMETRY_URL", "http://192.168.4.1/api/telemetry")

st.set_page_config(
    page_title="Motor Fault Diagnosis",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_monitor() -> WifiTelemetryClient:
    client = WifiTelemetryClient(ESP32_ENDPOINT)
    client.start()
    return client


monitor = get_monitor()


def display(value: float | None, digits: int, suffix: str) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:.{digits}f} {suffix}" if math.isfinite(number) else "—"


def trend_label(samples: list[float]) -> str:
    """Describe recent movement; this is not a fault threshold or diagnosis."""
    if len(samples) < 12:
        return "Collecting readings for trend analysis"
    previous = median(samples[-12:-6])
    recent = median(samples[-6:])
    scale = max(abs(previous), 0.05)
    change_pct = (recent - previous) / scale * 100
    if change_pct > 10:
        direction = "rising"
    elif change_pct < -10:
        direction = "falling"
    else:
        direction = "steady"
    return f"{direction.capitalize()} ({change_pct:+.0f}% vs previous 6 samples)"


def valid_samples(history: list[dict], field: str) -> list[float]:
    values = []
    for row in history:
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def render_dashboard() -> None:
    data = monitor.snapshot()
    connected = data["status"] == "Connected"
    latest = data["latest"] or {}
    history = data["history"]
    sensor_status = data["sensor_status"]

    with st.sidebar:
        st.header("ESP32 connection")
        if connected:
            st.success("Connected over Wi‑Fi")
            st.caption(f"{data['device']} · {data['firmware']}")
            st.caption(f"Live link: {data['endpoint']}")
        else:
            st.warning("Waiting for the ESP32")
            st.markdown(
                "1. Connect this computer to **MotorMonitor** Wi‑Fi.\n"
                "2. Password: **motorlab24**\n"
                "3. Leave this dashboard open; it reconnects automatically."
            )
            st.caption("ESP32 address: 192.168.4.1")
            if data["error"]:
                st.caption(f"Connection detail: {data['error']}")
        st.divider()
        st.caption("USB is only needed to upload firmware. Sensor readings reach this dashboard over Wi‑Fi.")

    st.title("⚙️ Edge-AI Electric Motor Fault Diagnosis")
    st.caption("Live measurements from the ESP32 sensor system")

    if connected:
        st.success("Live connection active · values below are received directly from the ESP32.")
    else:
        st.info("Waiting for Wi‑Fi telemetry. The dashboard will fill in automatically when the ESP32 is reachable.")

    st.subheader("Current readings")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Vibration RMS", display(latest.get("vibration_rms_g"), 4, "g"))
    metric_columns[1].metric("Motor voltage", display(latest.get("voltage_v"), 2, "V"))
    metric_columns[2].metric("Motor current", display(latest.get("current_a"), 3, "A"))
    metric_columns[3].metric("Probe temperature", display(latest.get("temperature_c"), 2, "°C"))

    status_columns = st.columns(3)
    for col, key, label in zip(
        status_columns,
        ("adxl345", "ina219", "ds18b20"),
        ("ADXL345 vibration", "INA219 voltage/current", "DS18B20 temperature"),
    ):
        state = sensor_status.get(key)
        if state is True:
            col.success(f"{label}: OK")
        elif state is False:
            col.error(f"{label}: check")
        else:
            col.info(f"{label}: waiting")

    st.subheader("Live trends")
    if history:
        frame = pd.DataFrame(history).set_index("time").tail(120)
        left, right = st.columns(2)
        for col, title, field, unit in (
            (left, "Vibration RMS", "vibration_rms_g", "g"),
            (right, "Motor current", "current_a", "A"),
            (left, "Motor voltage", "voltage_v", "V"),
            (right, "Probe temperature", "temperature_c", "°C"),
        ):
            with col:
                st.markdown(f"**{title} ({unit})**")
                series = frame[[field]].dropna()
                if series.empty:
                    st.caption("No valid readings received yet.")
                else:
                    st.line_chart(series, height=210, y_label=unit)
    else:
        st.caption("Graphs start drawing as soon as live samples arrive.")

    st.subheader("Recent analysis")
    if len(history) >= 12:
        analysis_columns = st.columns(3)
        for col, field, label, unit in zip(
            analysis_columns,
            ("vibration_rms_g", "current_a", "temperature_c"),
            ("Vibration", "Current", "Temperature"),
            ("g", "A", "°C"),
        ):
            with col:
                col.markdown(f"**{label}**")
                col.write(trend_label(valid_samples(history, field)))
    else:
        st.caption("Trend comparison appears after 12 valid samples. It describes recent movement; it is not a calibrated fault verdict.")

    if connected and history:
        last_time = history[-1]["time"].astimezone().strftime("%H:%M:%S")
        st.caption(f"Last sample: {last_time} · {data['valid_rows']} samples received")
    st.caption("Readings are shown as sent by the sensors. Calibration and fault limits have not been applied here.")


@st.fragment(run_every=1.0)
def live_dashboard() -> None:
    render_dashboard()


live_dashboard()
