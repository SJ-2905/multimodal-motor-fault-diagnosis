from __future__ import annotations

import math
import os
from statistics import median

import pandas as pd
import streamlit as st

from wifi_monitor import WifiTelemetryClient


ESP32_ENDPOINT = os.getenv("ESP32_TELEMETRY_URL", "http://192.168.4.1/api/telemetry")
STANDARD_GRAVITY = 9.80665
VIBRATION_WARNING_MS2 = 0.15
VIBRATION_ALERT_MS2 = 0.30
CURRENT_WARNING_MULTIPLIER = 1.5
CURRENT_ALERT_MULTIPLIER = 2.0

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


def assess_motor_condition(
    sensor_status: dict[str, bool | None],
    vibration_ms2: float,
    voltage_v: float,
    current_load_ratio: float,
    current_baseline_supported: bool,
) -> tuple[str, str, str]:
    """Return a rule-based prototype condition, severity, and reason."""
    failed = [
        name
        for key, name in (("adxl345", "ADXL345"), ("ina219", "INA219"))
        if sensor_status.get(key) is False
    ]
    if failed:
        return (
            "Condition unavailable — sensor fault",
            "error",
            f"{', '.join(failed)} reported a fault, so the motor condition cannot be assessed reliably.",
        )
    if sensor_status.get("adxl345") is not True or sensor_status.get("ina219") is not True:
        return (
            "Condition unknown — sensor status unavailable",
            "info",
            "Waiting for valid ADXL345 and INA219 readings.",
        )
    if not math.isfinite(voltage_v):
        return (
            "Condition unknown — motor voltage unavailable",
            "info",
            "INA219 bus voltage is not available in this sample.",
        )
    if voltage_v < 1.0:
        return (
            "Motor off or supply not detected",
            "info",
            "INA219 bus voltage is below 1.0 V, so a running-motor condition cannot be assessed.",
        )
    if not math.isfinite(vibration_ms2):
        return (
            "Condition unknown — vibration reading unavailable",
            "info",
            "No valid vibration reading is available.",
        )
    vibration_alert = vibration_ms2 >= VIBRATION_ALERT_MS2
    current_alert = (
        math.isfinite(current_load_ratio)
        and current_load_ratio >= CURRENT_ALERT_MULTIPLIER
    )
    if vibration_alert or current_alert:
        reasons = []
        if vibration_alert:
            reasons.append(f"vibration {vibration_ms2:.2f} m/s²")
        if current_alert:
            reasons.append(f"current {current_load_ratio:.2f}× unloaded baseline")
        if current_alert and vibration_alert:
            title = "Possible overload — high current and vibration"
        elif current_alert:
            title = "Possible overload — current sharply elevated"
        else:
            title = "High vibration — inspect motor"
        return (
            title,
            "error",
            (
                f"Alert indicators: {', '.join(reasons)}. Stop and inspect if unexpected. "
                "The current comparison is relative to startup baseline, not the motor's rated limit."
            ),
        )
    vibration_warning = vibration_ms2 >= VIBRATION_WARNING_MS2
    current_warning = (
        math.isfinite(current_load_ratio)
        and current_load_ratio >= CURRENT_WARNING_MULTIPLIER
    )
    if vibration_warning or current_warning:
        reasons = []
        if vibration_warning:
            reasons.append(f"vibration {vibration_ms2:.2f} m/s²")
        if current_warning:
            reasons.append(f"current {current_load_ratio:.2f}× unloaded baseline")
        return (
            "Load or vibration rising — maintenance check recommended",
            "warning",
            (
                f"Warning indicators: {', '.join(reasons)}. Compare with a repeatable known-good run."
            ),
        )
    if not math.isfinite(current_load_ratio):
        if not current_baseline_supported:
            return (
                "Current-load diagnosis unavailable — update ESP32 firmware",
                "info",
                "Upload the latest ADXL345 streaming sketch to enable no-load current baseline monitoring.",
            )
        return (
            "Vibration within demo limit — current baseline pending",
            "info",
            "Keep the motor unloaded while the ESP32 captures its startup current baseline; then apply load gradually.",
        )
    return (
        "Baseline ready — no alert currently active",
        "success",
        (
            f"Vibration {vibration_ms2:.2f} m/s²; current {current_load_ratio:.2f}× unloaded baseline. "
            "No configured alert is active; this is not a validated diagnosis."
        ),
    )


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
    vibration_g = latest.get("vibration_rms_g")
    try:
        vibration_ms2 = float(vibration_g) * STANDARD_GRAVITY
    except (TypeError, ValueError):
        vibration_ms2 = math.nan
    try:
        voltage_v = float(latest.get("voltage_v"))
    except (TypeError, ValueError):
        voltage_v = math.nan
    try:
        current_load_ratio = float(latest.get("current_load_ratio"))
    except (TypeError, ValueError):
        current_load_ratio = math.nan
    current_baseline_supported = bool(latest.get("current_baseline_supported", False))

    condition_title, condition_level, condition_detail = assess_motor_condition(
        sensor_status,
        vibration_ms2,
        voltage_v,
        current_load_ratio,
        current_baseline_supported,
    )
    st.subheader("Motor condition")
    if readings_live:
        getattr(st, condition_level)(condition_title)
        st.caption(condition_detail)
    elif latest:
        st.warning(f"Last known: {condition_title} · sample {sample_age_text}; this is not a live assessment.")
        st.caption(condition_detail)
    else:
        st.info("Condition unknown · waiting for a valid live sensor sample.")
    st.caption(
        "Demonstration rules: vibration warning at 0.15 m/s², alert at 0.30 m/s²; "
        "current warning at 1.5× and possible-overload alert at 2× the unloaded baseline. "
        "These are not calibrated motor limits."
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric("Vibration RMS", display(vibration_ms2, 2, "m/s²"))
    metric_columns[1].metric("Motor voltage", display(latest.get("voltage_v"), 2, "V"))
    metric_columns[2].metric("Motor current", display(latest.get("current_a"), 3, "A"))
    metric_columns[3].metric("Probe temperature", display(latest.get("temperature_c"), 2, "°C"))

    status_columns = st.columns(2)
    for col, key, label in zip(
        status_columns[:2],
        ("adxl345", "ina219"),
        ("ADXL345 vibration", "INA219 voltage/current"),
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
        frame["vibration_rms_ms2"] = frame["vibration_rms_g"] * STANDARD_GRAVITY
        left, right = st.columns(2)
        for col, title, field, unit in (
            (left, "Vibration RMS", "vibration_rms_ms2", "m/s²"),
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
