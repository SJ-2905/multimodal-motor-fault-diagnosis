from __future__ import annotations

import html
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
    page_title="Motor Condition Monitor",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      :root {
        --ink: #17241f;
        --muted: #64736c;
        --line: #dce6e0;
        --surface: #ffffff;
        --canvas: #f4f7f5;
        --green: #18794e;
        --green-bg: #e8f5ed;
        --amber: #9a5b00;
        --amber-bg: #fff4dc;
        --red: #b42318;
        --red-bg: #fff0ed;
        --blue: #2557a7;
        --blue-bg: #edf4ff;
      }
      .stApp { background: var(--canvas); color: var(--ink); }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stMainBlockContainer"] { padding-top: 1.8rem; max-width: 1450px; }
      h1, h2, h3, p { color: var(--ink); }
      .page-kicker {
        color: var(--green); font-size: .74rem; font-weight: 750;
        letter-spacing: .13em; text-transform: uppercase; margin-bottom: .25rem;
      }
      .page-subtitle { color: var(--muted); font-size: .98rem; margin-top: -.55rem; }
      .link-pill {
        display: inline-flex; align-items: center; gap: .55rem; float: right;
        margin-top: .9rem; border: 1px solid var(--line); border-radius: 999px;
        padding: .45rem .8rem; background: var(--surface); color: var(--muted);
        font-size: .8rem; font-weight: 650;
      }
      .dot { width: .55rem; height: .55rem; border-radius: 50%; display: inline-block; }
      .dot-green { background: #20a464; box-shadow: 0 0 0 3px #e5f5ec; }
      .dot-amber { background: #dc9500; box-shadow: 0 0 0 3px #fff4dc; }
      .dot-red { background: #d64545; box-shadow: 0 0 0 3px #fff0ed; }
      .dot-gray { background: #84928b; box-shadow: 0 0 0 3px #eef1ef; }
      .condition-card {
        border: 1px solid var(--line); border-left: 7px solid var(--green);
        background: var(--surface); border-radius: 16px; padding: 1.35rem 1.55rem;
        box-shadow: 0 5px 18px rgba(23, 36, 31, .045); margin: .5rem 0 1rem;
      }
      .condition-card.warning { border-left-color: #d99000; }
      .condition-card.alert { border-left-color: #d04437; }
      .condition-card.info { border-left-color: #5f7897; }
      .condition-top { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
      .condition-label { color: var(--muted); font-size: .72rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
      .condition-title { color: var(--ink); font-size: clamp(1.45rem, 2.8vw, 2rem); font-weight: 760; line-height: 1.2; margin: .25rem 0 .45rem; }
      .condition-detail { color: #43534b; font-size: .98rem; margin: 0; }
      .condition-action { color: var(--muted); font-size: .86rem; margin: .85rem 0 0; padding-top: .75rem; border-top: 1px solid #edf1ee; }
      .condition-badge {
        flex: 0 0 auto; border-radius: 999px; padding: .4rem .7rem; font-size: .73rem;
        font-weight: 750; letter-spacing: .04em; text-transform: uppercase;
        color: var(--green); background: var(--green-bg);
      }
      .condition-card.warning .condition-badge { color: var(--amber); background: var(--amber-bg); }
      .condition-card.alert .condition-badge { color: var(--red); background: var(--red-bg); }
      .condition-card.info .condition-badge { color: var(--blue); background: var(--blue-bg); }
      [data-testid="stMetric"] {
        background: var(--surface); border: 1px solid var(--line); border-radius: 13px;
        padding: .9rem 1rem; box-shadow: 0 3px 12px rgba(23, 36, 31, .025);
      }
      [data-testid="stMetricLabel"] p { color: var(--muted); font-size: .8rem; font-weight: 650; }
      [data-testid="stMetricValue"] { color: var(--ink); font-size: 1.45rem; }
      [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] { gap: 1rem; }
      .section-heading { font-size: 1.03rem; font-weight: 720; margin: .85rem 0 .15rem; }
      .threshold-note { color: var(--muted); font-size: .78rem; margin-top: -.2rem; }
      .stPlotlyChart, [data-testid="stLineChart"] {
        border: 1px solid var(--line); border-radius: 12px; background: var(--surface);
        padding: .4rem; box-shadow: 0 3px 12px rgba(23, 36, 31, .025);
      }
      [data-testid="stSidebar"] { background: var(--surface); }
      [data-testid="stSidebar"] p { color: var(--muted); }
      footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
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


def assess_motor_condition(
    sensor_status: dict[str, bool | None],
    vibration_ms2: float,
    voltage_v: float,
    current_load_ratio: float,
    current_baseline_supported: bool,
) -> tuple[str, str, str, str]:
    """Return a concise status, severity, explanation, and next step."""
    failed = [
        name
        for key, name in (("adxl345", "ADXL345"), ("ina219", "INA219"))
        if sensor_status.get(key) is False
    ]
    if failed:
        return (
            "Sensor check required",
            "alert",
            f"{', '.join(failed)} is not reporting reliably, so motor condition cannot be assessed.",
            "Inspect sensor power, shared ground, I²C wiring, and mounting before relying on this reading.",
        )
    if sensor_status.get("adxl345") is not True or sensor_status.get("ina219") is not True:
        return (
            "Checking monitoring system",
            "info",
            "Waiting for valid vibration and electrical measurements.",
            "Keep the motor unloaded while the sensors and current baseline initialize.",
        )
    if not math.isfinite(voltage_v):
        return (
            "Motor supply unavailable",
            "info",
            "The current sample does not contain a valid motor-supply voltage.",
            "Check the motor supply and INA219 voltage path.",
        )
    if voltage_v < 1.0:
        return (
            "Motor stopped",
            "info",
            "The monitored motor supply is below the running threshold.",
            "Start the motor safely to assess its operating condition.",
        )
    if not math.isfinite(vibration_ms2):
        return (
            "Condition unavailable",
            "info",
            "No valid vibration measurement is available.",
            "Check that the accelerometer is firmly mounted and reporting samples.",
        )

    vibration_alert = vibration_ms2 >= VIBRATION_ALERT_MS2
    current_alert = (
        math.isfinite(current_load_ratio)
        and current_load_ratio >= CURRENT_ALERT_MULTIPLIER
    )
    vibration_warning = vibration_ms2 >= VIBRATION_WARNING_MS2
    current_warning = (
        math.isfinite(current_load_ratio)
        and current_load_ratio >= CURRENT_WARNING_MULTIPLIER
    )
    if vibration_alert or current_alert:
        indicators = []
        if vibration_alert:
            indicators.append(f"vibration is {vibration_ms2:.2f} m/s²")
        if current_alert:
            indicators.append(f"current is {current_load_ratio:.2f}× the unloaded baseline")
        return (
            "Possible overload",
            "alert",
            f"Alert threshold reached: {' and '.join(indicators)}.",
            "Stop increasing the load. If the rise is unexpected, stop the motor and inspect the setup.",
        )
    if vibration_warning or current_warning:
        indicators = []
        if vibration_warning:
            indicators.append(f"vibration is {vibration_ms2:.2f} m/s²")
        if current_warning:
            indicators.append(f"current is {current_load_ratio:.2f}× the unloaded baseline")
        return (
            "Maintenance check recommended",
            "warning",
            f"Early warning: {' and '.join(indicators)} is above its demonstration range.",
            "Check motor mounting, load, alignment, and repeat the same test condition for comparison.",
        )
    if not math.isfinite(current_load_ratio):
        if not current_baseline_supported:
            return (
                "Current diagnosis unavailable",
                "info",
                "The connected firmware does not provide the unloaded-current baseline.",
                "Update the ESP32 sketch to enable current-based load assessment.",
            )
        return (
            "Capturing baseline",
            "info",
            "The motor is running, but its no-load current baseline is not ready yet.",
            "Keep the motor unloaded until the first baseline reading is available.",
        )
    return (
        "Healthy within configured limits",
        "healthy",
        f"No configured alert is active. Vibration is {vibration_ms2:.2f} m/s² and current is {current_load_ratio:.2f}× baseline.",
        "Continue monitoring. This prototype status is based on demonstration thresholds, not a certified motor-health assessment.",
    )


def recent_trend(values: list[float]) -> str:
    """Small descriptive trend cue; deliberately not a diagnosis."""
    values = [value for value in values if math.isfinite(value)]
    if len(values) < 12:
        return "Trend building"
    previous = median(values[-12:-6])
    recent = median(values[-6:])
    denominator = max(abs(previous), 0.05)
    change = (recent - previous) / denominator * 100
    if change > 10:
        return f"Rising · {change:+.0f}%"
    if change < -10:
        return f"Falling · {change:+.0f}%"
    return "Stable"


def valid_values(history: list[dict], field: str) -> list[float]:
    result = []
    for row in history:
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            result.append(value)
    return result


def render_dashboard() -> None:
    data = monitor.snapshot()
    status = data["status"]
    latest = data["latest"] or {}
    history = data["history"]
    sensor_status = data["sensor_status"]
    sample_age = data.get("sample_age_s")
    sample_fresh = sample_age is not None and sample_age <= 5.0
    readings_live = status == "Connected" and sample_fresh

    link_states = {
        "Connected": ("Connected", "dot-green"),
        "Reconnecting": ("Reconnecting", "dot-amber"),
        "Waiting": ("Not connected", "dot-gray"),
    }
    link_label, link_dot = link_states.get(status, ("Not connected", "dot-gray"))
    if status == "Connected" and latest and not sample_fresh:
        link_label, link_dot = "Data delayed", "dot-amber"

    title_col, link_col = st.columns([3.5, 1.2], vertical_alignment="center")
    with title_col:
        st.markdown('<div class="page-kicker">Condition monitoring</div>', unsafe_allow_html=True)
        st.title("Electric motor")
        st.markdown('<div class="page-subtitle">Fault indicators and operating trends</div>', unsafe_allow_html=True)
    with link_col:
        st.markdown(
            f'<div class="link-pill"><span class="dot {link_dot}"></span>{html.escape(link_label)}</div>',
            unsafe_allow_html=True,
        )

    if latest:
        try:
            vibration_ms2 = float(latest.get("vibration_rms_g")) * STANDARD_GRAVITY
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

        condition, severity, explanation, action = assess_motor_condition(
            sensor_status,
            vibration_ms2,
            voltage_v,
            current_load_ratio,
            current_baseline_supported,
        )
        if readings_live:
            shown_condition = condition
            badge = "Live assessment"
            display_severity = severity
            shown_explanation = explanation
            shown_action = action
        elif status == "Connected":
            shown_condition = "Data delayed"
            badge = "Last known status: " + condition
            display_severity = "warning"
            shown_explanation = "No new sensor sample has arrived recently; the values below are retained from the last sample."
            shown_action = "Check that the ESP32 is still sampling. Treat this as historical status until fresh data resumes."
        else:
            shown_condition = "ESP32 connection lost"
            badge = "Last known status: " + condition
            display_severity = "warning"
            shown_explanation = "Live assessment paused. The dashboard is retaining the last received readings."
            shown_action = "Reconnect this computer to the MotorMonitor Wi-Fi network; the dashboard will retry automatically."

        severity_class = {"healthy": "healthy", "warning": "warning", "alert": "alert", "info": "info"}.get(display_severity, "info")
        badge_text = "Live" if readings_live else "Last known"
        st.markdown(
            f"""
            <section class="condition-card {severity_class}">
              <div class="condition-top">
                <div>
                  <div class="condition-label">Motor health status</div>
                  <div class="condition-title">{html.escape(shown_condition)}</div>
                </div>
                <span class="condition-badge">{html.escape(badge_text)}</span>
              </div>
              <p class="condition-detail">{html.escape(shown_explanation)}</p>
              <p class="condition-action"><strong>Recommended action:</strong> {html.escape(shown_action)}</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <section class="condition-card info">
              <div class="condition-top"><div>
                <div class="condition-label">Motor health status</div>
                <div class="condition-title">Waiting for live measurements</div>
              </div><span class="condition-badge">Connecting</span></div>
              <p class="condition-detail">The dashboard will show a condition as soon as it receives the ESP32 sensor data.</p>
              <p class="condition-action"><strong>Next step:</strong> Join the MotorMonitor Wi-Fi network and keep the ESP32 powered.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )

    if latest:
        try:
            vibration_g = float(latest.get("vibration_rms_g"))
            vibration_ms2 = vibration_g * STANDARD_GRAVITY
        except (TypeError, ValueError):
            vibration_g, vibration_ms2 = math.nan, math.nan
        current = latest.get("current_a")
        temperature = latest.get("temperature_c")
        current_ratio = latest.get("current_load_ratio")
        try:
            current_ratio = float(current_ratio)
        except (TypeError, ValueError):
            current_ratio = math.nan

        st.markdown('<div class="section-heading">Key measurements</div>', unsafe_allow_html=True)
        value_columns = st.columns(3)
        value_columns[0].metric("Vibration RMS", display(vibration_ms2, 2, "m/s²"))
        value_columns[1].metric("Motor current", display(current, 3, "A"))
        value_columns[2].metric("Motor temperature", display(temperature, 1, "°C"))
        if math.isfinite(current_ratio):
            ratio_note = f"Current is {current_ratio:.2f}× the captured no-load baseline."
        elif latest.get("current_baseline_supported"):
            ratio_note = "No-load current baseline is still being captured."
        else:
            ratio_note = "Relative current comparison is unavailable with the current firmware."
        voltage_label = display(latest.get("voltage_v"), 2, "V")
        st.caption(f"Motor supply: {voltage_label}  ·  {ratio_note}")

        st.markdown('<div class="section-heading">Operating trends</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="threshold-note">Recent samples · warning/alert references use demonstration thresholds, not certified motor limits.</div>',
            unsafe_allow_html=True,
        )
        if history:
            frame = pd.DataFrame(history).set_index("time").tail(120)
            frame["Vibration · m/s²"] = frame["vibration_rms_g"] * STANDARD_GRAVITY
            frame["Current · A"] = frame["current_a"]
            chart_cols = st.columns(2)
            with chart_cols[0]:
                st.caption(f"VIBRATION  ·  {recent_trend(valid_values(history, 'vibration_rms_g'))}")
                values = frame[["Vibration · m/s²"]].dropna()
                if values.empty:
                    st.info("Waiting for vibration samples.")
                else:
                    st.line_chart(values, height=250, y_label="m/s²", color="#23845a")
            with chart_cols[1]:
                st.caption(f"MOTOR CURRENT  ·  {recent_trend(valid_values(history, 'current_a'))}")
                values = frame[["Current · A"]].dropna()
                if values.empty:
                    st.info("Waiting for current samples.")
                else:
                    st.line_chart(values, height=250, y_label="A", color="#2864b4")
        else:
            st.info("Trend charts will appear when the first samples arrive.")

        if not readings_live:
            age = f"{sample_age:.1f} seconds ago" if sample_age is not None else "unknown time"
            st.caption(f"Last sensor sample received {age}. Values are retained but are not live.")
    else:
        st.info("Connect the dashboard computer to the ESP32 Wi-Fi to begin monitoring.")

    with st.sidebar:
        st.subheader("Connection details")
        if status == "Connected":
            st.success("ESP32 reachable over Wi-Fi")
        elif status == "Reconnecting":
            st.warning("Reconnecting to ESP32")
        else:
            st.info("Waiting for ESP32")
        st.caption(f"Device: {data['device'] or 'ESP32'}")
        st.caption(f"Firmware: {data['firmware'] or 'not identified'}")
        st.code(data["endpoint"], language=None)
        st.caption("Join the MotorMonitor Wi-Fi network on this computer. USB is used to upload firmware, not for live dashboard data.")
        if data["error"]:
            with st.expander("Technical connection message"):
                st.code(data["error"], language=None)

    st.caption(
        "Prototype decision support only. Healthy means no configured demonstration threshold is active; "
        "it is not a certified or calibrated diagnosis."
    )


@st.fragment(run_every=1.0)
def live_dashboard() -> None:
    render_dashboard()


live_dashboard()
