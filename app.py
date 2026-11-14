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
    status = data["status"]
    connected = status == "Connected"
    reconnecting = status == "Reconnecting"
    latest = data["latest"] or {}
    history = data["history"]
    sensor_status = data["sensor_status"]
    sample_age = data.get("sample_age_s")
    sample_fresh = sample_age is not None and sample_age <= 5.0
    readings_live = connected and sample_fresh
    sample_age_text = (
        f"{sample_age:.1f}s ago" if sample_age is not None else "not received yet"
    )

    with st.sidebar:
        st.header("ESP32 connection")
        if connected:
            st.success("Connected over Wi‑Fi")
            st.caption(f"{data['device']} · {data['firmware']}")
            st.caption(f"Live link: {data['endpoint']}")
        elif reconnecting:
            st.warning("Reconnecting · brief Wi‑Fi interruption")
            st.caption(f"Last ESP32 response: {data['response_age_s']:.1f}s ago")
        else:
            st.warning("Waiting for the ESP32")
            st.markdown(
                "1. Connect this computer to **MotorMonitor** Wi‑Fi.\n"
                "2. Password: **motorlab24**\n"
                "3. Keep the computer on that network; it has no internet access.\n"
                "4. Leave this dashboard open; it reconnects automatically."
            )
            st.caption("ESP32 address: 192.168.4.1")
            st.caption(
                "If MotorMonitor is missing from the Wi‑Fi list, check ESP32 power, press EN/RESET once, "
                "and confirm the 115200-baud boot log says the access point is ready."
            )
        st.caption(f"Latest sensor sample: {sample_age_text}")
        if data["error"]:
            with st.expander("Connection details"):
                st.code(data["error"], language=None)
        st.divider()
        st.caption("USB is only needed to upload firmware. Sensor readings reach this dashboard over Wi‑Fi.")

    st.title("⚙️ Edge-AI Electric Motor Fault Diagnosis")
    st.caption("Live measurements from the ESP32 sensor system")

    if readings_live:
        st.success("Live connection active · fresh sensor samples are arriving from the ESP32.")
    elif connected and latest:
        st.warning("ESP32 Wi‑Fi is reachable, but no new sensor sample has arrived for over 5 seconds.")
    elif connected:
        st.info("ESP32 is reachable · waiting for the first sensor sample.")
    elif reconnecting:
        st.warning("Reconnecting to the ESP32. The last values are kept on screen temporarily.")
    else:
        if latest:
            st.warning("ESP32 is not reachable. Values below are the last received sample, not live readings.")
        else:
            st.info("Waiting for Wi‑Fi telemetry. The dashboard will fill in automatically when the ESP32 is reachable.")

    st.subheader("Current readings" if readings_live else "Last readings (may be stale)")
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
        label_prefix = "Live" if readings_live else "Last known"
        if state is True:
            col.success(f"{label_prefix} · {label}: OK")
        elif state is False:
            col.error(f"{label_prefix} · {label}: check")
        else:
            col.info(f"{label_prefix} · {label}: waiting")

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

    if history:
        last_time = history[-1]["time"].astimezone().strftime("%H:%M:%S")
        st.caption(f"Last sample received at {last_time} · {sample_age_text} · {data['valid_rows']} samples received")
    if data.get("restart_count", 0):
        st.warning(
            "The ESP32 uptime restarted during this dashboard session. If that lines up with starting the motor, "
            "check the ESP32 supply and motor wiring for voltage dips or electrical noise; this dashboard detects "
            "the reboot but cannot identify its cause by itself."
        )
    st.caption("Readings are shown as sent by the sensors. Calibration and fault limits have not been applied here.")


@st.fragment(run_every=1.0)
def live_dashboard() -> None:
    render_dashboard()


live_dashboard()
