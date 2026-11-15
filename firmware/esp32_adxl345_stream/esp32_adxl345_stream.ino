#include <Wire.h>
#include <Adafruit_ADXL345_U.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_INA219.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <math.h>
#include <WiFi.h>
#include <WebServer.h>

// ESP32 DevKit V1 sensor and status LED pins.
constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;
constexpr uint8_t DS18B20_DATA_PIN = 4;
constexpr uint8_t LED_GREEN_PIN = 25;
constexpr uint8_t LED_YELLOW_PIN = 26;
constexpr uint8_t LED_RED_PIN = 27;

constexpr uint16_t VIBRATION_SAMPLES = 200;
constexpr uint16_t SAMPLE_INTERVAL_MS = 5;
constexpr float STANDARD_GRAVITY = 9.80665f;
constexpr uint32_t TEMPERATURE_RETRY_INTERVAL_MS = 2000;
constexpr uint32_t SENSOR_RETRY_INTERVAL_MS = 2000;
constexpr uint8_t PERSISTENT_FAILURE_LIMIT = 3;
constexpr float MOTOR_BUS_PRESENT_THRESHOLD_V = 1.0f;
// Demonstration thresholds only; confirm against repeatable healthy-motor data.
constexpr float VIBRATION_WARNING_MS2 = 0.15f;
constexpr float VIBRATION_ALERT_MS2 = 0.30f;
constexpr uint8_t CONDITION_CONFIRM_SAMPLES = 3;
constexpr uint32_t CURRENT_BASELINE_SETTLE_MS = 5000;
constexpr uint32_t MOTOR_SUPPLY_OFF_RESET_MS = 3000;
constexpr uint8_t CURRENT_BASELINE_SAMPLE_COUNT = 5;
constexpr float CURRENT_WARNING_MULTIPLIER = 1.5f;
constexpr float CURRENT_ALERT_MULTIPLIER = 2.0f;
constexpr float CURRENT_BASELINE_MIN_A = 0.02f;

// The ESP32 creates a local Wi-Fi network for the dashboard. Change these if
// you want a different network name/password. Password must be at least 8 chars.
const char *WIFI_AP_SSID = "MotorMonitor";
const char *WIFI_AP_PASSWORD = "motorlab24";
WebServer server(80);

// Replace these after completing the six-position ADXL345 calibration in
// firmware/adxl345_static_calibration. Units for offsets are g. Defaults are
// neutral (pass-through); the dashboard never applies calibration by itself.
constexpr float ADXL_BIAS_X_G = 0.0f;
constexpr float ADXL_BIAS_Y_G = 0.0f;
constexpr float ADXL_BIAS_Z_G = 0.0f;
constexpr float ADXL_SCALE_X = 1.0f;
constexpr float ADXL_SCALE_Y = 1.0f;
constexpr float ADXL_SCALE_Z = 1.0f;

// Reference-check these against a trusted meter/thermometer before changing.
// INA219 correction form is (library_reading - offset) * scale.
constexpr float INA_BUS_VOLTAGE_OFFSET_V = 0.0f;
constexpr float INA_BUS_VOLTAGE_SCALE = 1.0f;
constexpr float INA_CURRENT_OFFSET_A = 0.0f;
constexpr float INA_CURRENT_SCALE = 1.0f;
constexpr float DS18B20_OFFSET_C = 0.0f;

Adafruit_ADXL345_Unified adxl(12345);
Adafruit_INA219 ina219;
OneWire oneWire(DS18B20_DATA_PIN);
DallasTemperature temperatureSensor(&oneWire);

bool adxlOK = false;
bool inaOK = false;
bool temperatureOK = false;
uint8_t adxlAddress = 0;
uint32_t lastTemperatureRetryMs = 0;
uint32_t lastSensorRetryMs = 0;
uint32_t sampleSequence = 0;
uint8_t adxlReadFailures = 0;
float latestVibrationRmsG = NAN;
float latestVoltageV = NAN;
float latestCurrentA = NAN;
float currentBaselineSamples[CURRENT_BASELINE_SAMPLE_COUNT] = {};
float currentBaselineA = NAN;
float currentLoadRatio = NAN;
float latestTemperatureC = NAN;
bool latestAdxlReadingOK = false;
bool latestInaOK = false;
bool temperatureHasValidReading = false;
bool currentBaselineReady = false;
bool currentBaselineInvalidWarned = false;
uint8_t currentBaselineSampleCount = 0;
uint8_t warningConditionCount = 0;
uint8_t alertConditionCount = 0;
uint32_t motorSupplyPresentSinceMs = 0;
uint32_t motorSupplyMissingSinceMs = 0;

void setStatusLeds(bool green, bool yellow, bool red) {
  digitalWrite(LED_GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(LED_YELLOW_PIN, yellow ? HIGH : LOW);
  digitalWrite(LED_RED_PIN, red ? HIGH : LOW);
}

String jsonNumber(float value, uint8_t digits) {
  if (!isfinite(value)) return "null";
  return String(value, static_cast<unsigned int>(digits));
}

float medianCurrentBaseline() {
  float sorted[CURRENT_BASELINE_SAMPLE_COUNT];
  for (uint8_t i = 0; i < CURRENT_BASELINE_SAMPLE_COUNT; i++) {
    sorted[i] = currentBaselineSamples[i];
  }
  for (uint8_t i = 1; i < CURRENT_BASELINE_SAMPLE_COUNT; i++) {
    const float value = sorted[i];
    int8_t j = static_cast<int8_t>(i) - 1;
    while (j >= 0 && sorted[j] > value) {
      sorted[j + 1] = sorted[j];
      j--;
    }
    sorted[j + 1] = value;
  }
  return sorted[CURRENT_BASELINE_SAMPLE_COUNT / 2];
}

void updateCurrentBaseline(float busVoltageV, float currentA) {
  const bool motorSupplyPresent =
      isfinite(busVoltageV) && busVoltageV >= MOTOR_BUS_PRESENT_THRESHOLD_V;
  if (!motorSupplyPresent) {
    if (motorSupplyMissingSinceMs == 0) motorSupplyMissingSinceMs = millis();
    if (currentBaselineReady &&
        millis() - motorSupplyMissingSinceMs < MOTOR_SUPPLY_OFF_RESET_MS) {
      currentLoadRatio = isfinite(currentA) ? currentA / currentBaselineA : NAN;
      return;
    }
    motorSupplyPresentSinceMs = 0;
    currentBaselineSampleCount = 0;
    currentBaselineReady = false;
    currentBaselineInvalidWarned = false;
    currentBaselineA = NAN;
    currentLoadRatio = NAN;
    return;
  }

  motorSupplyMissingSinceMs = 0;
  if (motorSupplyPresentSinceMs == 0) motorSupplyPresentSinceMs = millis();
  if (currentBaselineReady) {
    currentLoadRatio = isfinite(currentA) ? currentA / currentBaselineA : NAN;
    return;
  }

  // Capture only after the motor has run unloaded long enough to pass startup.
  if (millis() - motorSupplyPresentSinceMs < CURRENT_BASELINE_SETTLE_MS ||
      !isfinite(currentA)) {
    currentLoadRatio = NAN;
    return;
  }

  currentBaselineSamples[currentBaselineSampleCount++] = currentA;
  if (currentBaselineSampleCount < CURRENT_BASELINE_SAMPLE_COUNT) return;

  currentBaselineA = medianCurrentBaseline();
  if (currentBaselineA < CURRENT_BASELINE_MIN_A) {
    // A near-zero or negative baseline usually means the shunt path/polarity
    // needs checking. Do not turn it into an overload ratio.
    currentBaselineA = NAN;
    currentBaselineSampleCount = 0;
    currentLoadRatio = NAN;
    if (!currentBaselineInvalidWarned) {
      Serial.println("Current baseline invalid; check unloaded motor path through VIN+ to VIN- and polarity");
      currentBaselineInvalidWarned = true;
    }
    return;
  }

  currentBaselineReady = true;
  currentLoadRatio = currentA / currentBaselineA;
  Serial.print("Unloaded current baseline ready: ");
  Serial.print(currentBaselineA, 3);
  Serial.println(" A; gradual load test may begin");
}

void handleTelemetry() {
  String json;
  json.reserve(320);
  json = "{\"device\":\"ESP32 DevKit V1\",\"firmware\":\"MotorMonitor Wi-Fi\",\"sample_id\":";
  json += String(sampleSequence);
  json += ",\"uptime_ms\":";
  json += String(millis());
  json += ",\"vibration_rms_g\":";
  json += jsonNumber(latestVibrationRmsG, 4);
  json += ",\"voltage_v\":";
  json += jsonNumber(latestVoltageV, 3);
  json += ",\"current_a\":";
  json += jsonNumber(latestCurrentA, 4);
  json += ",\"current_baseline_a\":";
  json += jsonNumber(currentBaselineReady ? currentBaselineA : NAN, 4);
  json += ",\"current_load_ratio\":";
  json += jsonNumber(currentLoadRatio, 3);
  json += ",\"temperature_c\":";
  json += jsonNumber(latestTemperatureC, 2);
  json += ",\"sensor_status\":{\"adxl345\":";
  json += latestAdxlReadingOK ? "true" : "false";
  json += ",\"ina219\":";
  json += latestInaOK ? "true" : "false";
  json += ",\"ds18b20\":";
  // This field means a temperature has been read at least once this boot.
  // Transient probe disconnects are intentionally hidden from the live UI.
  json += temperatureHasValidReading ? "true" : "false";
  json += "}}";
  server.sendHeader("Cache-Control", "no-store, max-age=0");
  server.send(200, "application/json", json);
}

void handleRoot() {
  server.send(200, "text/plain", "MotorMonitor ESP32 is online. Read /api/telemetry for live sensor data.");
}

void startWifiTelemetry() {
  WiFi.mode(WIFI_AP);
  const bool apStarted = WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD, 1, false, 4);
  server.on("/", HTTP_GET, handleRoot);
  server.on("/health", HTTP_GET, []() {
    server.send(200, "text/plain", "ok");
  });
  server.on("/api/telemetry", HTTP_GET, handleTelemetry);
  server.onNotFound([]() {
    server.send(404, "application/json", "{\"error\":\"not found\"}");
  });
  server.begin();

  Serial.println(apStarted ? "Wi-Fi access point ready" : "Wi-Fi access point failed");
  Serial.print("Wi-Fi name: ");
  Serial.println(WIFI_AP_SSID);
  Serial.print("Wi-Fi password: ");
  Serial.println(WIFI_AP_PASSWORD);
  Serial.print("Telemetry URL: http://");
  Serial.print(WiFi.softAPIP());
  Serial.println("/api/telemetry");
}

uint8_t scanI2CBus() {
  uint8_t foundAdxlAddress = 0;
  uint8_t foundCount = 0;
  Serial.println("I2C scan:");

  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      Serial.print("  Device at 0x");
      if (address < 0x10) Serial.print('0');
      Serial.println(address, HEX);
      foundCount++;

      if (address == 0x40) {
        Serial.println("    INA219 address");
      } else if (address == 0x53 || address == 0x1D) {
        Serial.println("    ADXL345 address");
        foundAdxlAddress = address;
      }
    }
  }

  if (foundCount == 0) Serial.println("  No I2C devices found");
  return foundAdxlAddress;
}

bool i2cDeviceResponds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool readVibration(float &axG, float &ayG, float &azG, float &rmsG) {
  double sumX = 0.0, sumY = 0.0, sumZ = 0.0;
  double sumSquaresX = 0.0, sumSquaresY = 0.0, sumSquaresZ = 0.0;

  for (uint16_t i = 0; i < VIBRATION_SAMPLES; i++) {
    sensors_event_t event;
    if (!adxl.getEvent(&event)) return false;

    const double rawXG = event.acceleration.x / STANDARD_GRAVITY;
    const double rawYG = event.acceleration.y / STANDARD_GRAVITY;
    const double rawZG = event.acceleration.z / STANDARD_GRAVITY;
    const double x = (rawXG - ADXL_BIAS_X_G) * ADXL_SCALE_X;
    const double y = (rawYG - ADXL_BIAS_Y_G) * ADXL_SCALE_Y;
    const double z = (rawZG - ADXL_BIAS_Z_G) * ADXL_SCALE_Z;
    sumX += x;
    sumY += y;
    sumZ += z;
    sumSquaresX += x * x;
    sumSquaresY += y * y;
    sumSquaresZ += z * z;
    if ((i % 20) == 0) server.handleClient();
    delay(SAMPLE_INTERVAL_MS);
  }

  const double count = static_cast<double>(VIBRATION_SAMPLES);
  const double meanX = sumX / count;
  const double meanY = sumY / count;
  const double meanZ = sumZ / count;
  axG = static_cast<float>(meanX);
  ayG = static_cast<float>(meanY);
  azG = static_cast<float>(meanZ);

  const double varianceX = (sumSquaresX / count) - meanX * meanX;
  const double varianceY = (sumSquaresY / count) - meanY * meanY;
  const double varianceZ = (sumSquaresZ / count) - meanZ * meanZ;
  const double totalVariance = fmax(0.0, varianceX) +
                               fmax(0.0, varianceY) +
                               fmax(0.0, varianceZ);
  rmsG = static_cast<float>(sqrt(totalVariance));
  return true;
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_YELLOW_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  setStatusLeds(false, false, false);
  delay(1500);

  Serial.println();
  Serial.println("ESP32 motor sensor monitor starting");
  startWifiTelemetry();

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(100000);

  adxlAddress = scanI2CBus();
  if (adxlAddress != 0) adxlOK = adxl.begin(adxlAddress);
  if (adxlOK) {
    adxl.setRange(ADXL345_RANGE_8_G);
    adxl.setDataRate(ADXL345_DATARATE_200_HZ);
    Serial.print("ADXL345: OK at 0x");
    Serial.println(adxlAddress, HEX);
  } else {
    Serial.println("ADXL345: NOT FOUND (expected 0x53 or 0x1D)");
  }

  inaOK = ina219.begin(&Wire);
  Serial.println(inaOK ? "INA219: OK on I2C" : "INA219: NOT FOUND on I2C");
  if (inaOK) Serial.println("INA219 readings are not motor measurements unless the motor supply passes through VIN+ to VIN-");

  temperatureSensor.begin();
  temperatureOK = temperatureSensor.getDeviceCount() > 0;
  lastTemperatureRetryMs = millis();
  lastSensorRetryMs = millis();

}

void loop() {
  server.handleClient();

  // Retry failed sensor initialization periodically so one startup race or
  // brief I2C interruption does not leave the status LED red forever.
  if (millis() - lastSensorRetryMs >= SENSOR_RETRY_INTERVAL_MS) {
    lastSensorRetryMs = millis();
    if (!adxlOK) {
      if (adxlAddress == 0) adxlAddress = scanI2CBus();
      if (adxlAddress != 0 && adxl.begin(adxlAddress)) {
        adxl.setRange(ADXL345_RANGE_8_G);
        adxl.setDataRate(ADXL345_DATARATE_200_HZ);
        adxlOK = true;
        Serial.println("ADXL345: recovered");
      }
    }
    if (inaOK && !i2cDeviceResponds(0x40)) {
      inaOK = false;
      Serial.println("INA219: disconnected from I2C");
    }
    if (!inaOK && ina219.begin(&Wire)) {
      inaOK = true;
      Serial.println("INA219: recovered");
    }
  }

  float axG = NAN, ayG = NAN, azG = NAN, vibrationRmsG = NAN;
  float voltageV = NAN, currentA = NAN, temperatureC = NAN;

  bool adxlReadingOK = adxlOK && readVibration(axG, ayG, azG, vibrationRmsG);
  if (adxlReadingOK) {
    adxlReadFailures = 0;
  } else if (adxlReadFailures < 255) {
    adxlReadFailures++;
    if (adxlReadFailures >= PERSISTENT_FAILURE_LIMIT) adxlOK = false;
  }

  if (inaOK) {
    const float measuredVoltageV = ina219.getBusVoltage_V();
    const float measuredCurrentA = ina219.getCurrent_mA() / 1000.0f;
    voltageV = (measuredVoltageV - INA_BUS_VOLTAGE_OFFSET_V) * INA_BUS_VOLTAGE_SCALE;
    currentA = (measuredCurrentA - INA_CURRENT_OFFSET_A) * INA_CURRENT_SCALE;
  }
  updateCurrentBaseline(voltageV, currentA);

  if (!temperatureOK && millis() - lastTemperatureRetryMs >= TEMPERATURE_RETRY_INTERVAL_MS) {
    lastTemperatureRetryMs = millis();
    temperatureSensor.begin();
    temperatureOK = temperatureSensor.getDeviceCount() > 0;
  }

  bool temperatureReadingOK = false;
  if (temperatureOK) {
    temperatureSensor.requestTemperatures();
    const float measuredTemperature = temperatureSensor.getTempCByIndex(0);
    if (measuredTemperature != DEVICE_DISCONNECTED_C) {
      temperatureC = measuredTemperature + DS18B20_OFFSET_C;
      temperatureReadingOK = true;
      temperatureHasValidReading = true;
    } else {
      temperatureOK = false;
      lastTemperatureRetryMs = millis();
    }
  }

  latestVibrationRmsG = vibrationRmsG;
  latestVoltageV = voltageV;
  latestCurrentA = currentA;
  // Hold the last valid temperature through a brief loose-wire interruption.
  if (temperatureReadingOK) latestTemperatureC = temperatureC;
  latestAdxlReadingOK = adxlReadingOK;
  latestInaOK = inaOK;
  sampleSequence++;

  // Test indication only: this is not yet a calibrated motor-fault classifier.
  const float vibrationRmsMs2 = vibrationRmsG * STANDARD_GRAVITY;
  const bool motorPowerPresent =
      isfinite(voltageV) && voltageV >= MOTOR_BUS_PRESENT_THRESHOLD_V;
  uint8_t conditionLevel = 0;
  if (motorPowerPresent) {
    if (isfinite(vibrationRmsMs2) && vibrationRmsMs2 >= VIBRATION_WARNING_MS2) {
      conditionLevel = 1;
    }
    if (isfinite(vibrationRmsMs2) && vibrationRmsMs2 >= VIBRATION_ALERT_MS2) {
      conditionLevel = 2;
    }
    if (isfinite(currentLoadRatio) && currentLoadRatio >= CURRENT_WARNING_MULTIPLIER) {
      if (conditionLevel < 1) conditionLevel = 1;
    }
    if (isfinite(currentLoadRatio) && currentLoadRatio >= CURRENT_ALERT_MULTIPLIER) {
      conditionLevel = 2;
    }
  }

  if (conditionLevel >= 2) {
    if (alertConditionCount < CONDITION_CONFIRM_SAMPLES) alertConditionCount++;
    if (warningConditionCount < CONDITION_CONFIRM_SAMPLES) warningConditionCount++;
  } else if (conditionLevel == 1) {
    alertConditionCount = 0;
    if (warningConditionCount < CONDITION_CONFIRM_SAMPLES) warningConditionCount++;
  } else {
    warningConditionCount = 0;
    alertConditionCount = 0;
  }

  if (!adxlOK || !inaOK || adxlReadFailures >= PERSISTENT_FAILURE_LIMIT ||
      alertConditionCount >= CONDITION_CONFIRM_SAMPLES) {
    setStatusLeds(false, false, true);  // red: sensor fault or sustained load/vibration alert
  } else if (warningConditionCount >= CONDITION_CONFIRM_SAMPLES ||
             !motorPowerPresent) {
    setStatusLeds(false, true, false);  // yellow: rising load/vibration or motor supply absent
  } else {
    setStatusLeds(true, false, false);  // green: sensors work and voltage is present at INA bus
  }

  server.handleClient();
  delay(250);
}
