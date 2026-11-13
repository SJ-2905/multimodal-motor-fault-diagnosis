"""Persistent HTTP telemetry client for the ESP32 MotorMonitor access point."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

import requests


FIELDS = ("vibration_rms_g", "voltage_v", "current_a", "temperature_c")
MAX_HISTORY = 600
POLL_SECONDS = 0.8


def _numeric(value: Any) -> float:
    if value is None:
        return math.nan
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


class WifiTelemetryClient:
    """Poll the ESP32 HTTP endpoint and keep a bounded, timestamped sample history."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "Waiting"
        self._error = ""
        self._device = ""
        self._firmware = ""
        self._sensor_status: dict[str, bool | None] = {
            "adxl345": None,
            "ina219": None,
            "ds18b20": None,
        }
        self._history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)
        self._latest: dict[str, Any] | None = None
        self._last_sample_id: int | str | None = None
        self._valid_rows = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event = threading.Event()
            self._status = "Waiting"
            self._error = ""
            self._thread = threading.Thread(
                target=self._poll_loop,
                daemon=True,
                name="esp32-wifi-telemetry",
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        with self._lock:
            self._thread = None
            self._status = "Waiting"

    def _poll_loop(self) -> None:
        session = requests.Session()
        session.headers.update({"Cache-Control": "no-cache"})
        while not self._stop_event.is_set():
            try:
                response = session.get(self.endpoint, timeout=(1.0, 3.0))
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not all(field in payload for field in FIELDS):
                    raise ValueError("ESP32 telemetry response did not contain all four sensor fields")

                sample_id = payload.get("sample_id")
                sample = {
                    "time": datetime.now().astimezone(),
                    **{field: _numeric(payload.get(field)) for field in FIELDS},
                }
                statuses = payload.get("sensor_status", {})
                if not isinstance(statuses, dict):
                    statuses = {}

                with self._lock:
                    self._status = "Connected"
                    self._error = ""
                    self._device = str(payload.get("device") or "ESP32")
                    self._firmware = str(payload.get("firmware") or "Wi-Fi telemetry")
                    self._sensor_status = {
                        key: bool(statuses[key]) if key in statuses else None
                        for key in ("adxl345", "ina219", "ds18b20")
                    }
                    if sample_id != self._last_sample_id:
                        self._latest = sample
                        self._history.append(sample)
                        self._last_sample_id = sample_id
                        self._valid_rows += 1
            except (requests.RequestException, ValueError) as exc:
                with self._lock:
                    self._status = "Waiting"
                    self._error = str(exc)

            self._stop_event.wait(POLL_SECONDS)

        session.close()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "endpoint": self.endpoint,
                "error": self._error,
                "device": self._device,
                "firmware": self._firmware,
                "sensor_status": dict(self._sensor_status),
                "history": list(self._history),
                "latest": dict(self._latest) if self._latest else None,
                "valid_rows": self._valid_rows,
            }
