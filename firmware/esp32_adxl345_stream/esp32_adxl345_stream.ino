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
constexpr float MOTOR_BUS_PRESENT_THRESHOLD_V = 1.0f;

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
uint32_t sampleSequence = 0;
float latestVibrationRmsG = NAN;
float latestVoltageV = NAN;
float latestCurrentA = NAN;
float latestTemperatureC = NAN;
bool latestAdxlReadingOK = false;
bool latestInaOK = false;
bool latestTemperatureReadingOK = false;

void setStatusLeds(bool green, bool yellow, bool red) {
  digitalWrite(LED_GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(LED_YELLOW_PIN, yellow ? HIGH : LOW);
  digitalWrite(LED_RED_PIN, red ? HIGH : LOW);
}

void testStatusLeds() {
  Serial.println("LED self-test: green, yellow, red");
  setStatusLeds(true, false, false);
  delay(500);
  setStatusLeds(false, true, false);
  delay(500);
  setStatusLeds(false, false, true);
  delay(500);
  setStatusLeds(false, false, false);
}

String jsonNumber(float value, uint8_t digits) {
  if (!isfinite(value)) return "null";
  return String(value, static_cast<unsigned int>(digits));
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
  json += ",\"temperature_c\":";
  json += jsonNumber(latestTemperatureC, 2);
  json += ",\"sensor_status\":{\"adxl345\":";
  json += latestAdxlReadingOK ? "true" : "false";
  json += ",\"ina219\":";
  json += latestInaOK ? "true" : "false";
  json += ",\"ds18b20\":";
  json += latestTemperatureReadingOK ? "true" : "false";
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
  testStatusLeds();
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
  Serial.println(temperatureOK ? "DS18B20: OK" : "DS18B20: NOT FOUND");
  lastTemperatureRetryMs = millis();

}

void loop() {
  server.handleClient();

  float axG = NAN, ayG = NAN, azG = NAN, vibrationRmsG = NAN;
  float voltageV = NAN, currentA = NAN, temperatureC = NAN;

  bool adxlReadingOK = adxlOK && readVibration(axG, ayG, azG, vibrationRmsG);
  if (adxlOK && !adxlReadingOK) adxlOK = false;

  if (inaOK) {
    const float measuredVoltageV = ina219.getBusVoltage_V();
    const float measuredCurrentA = ina219.getCurrent_mA() / 1000.0f;
    voltageV = (measuredVoltageV - INA_BUS_VOLTAGE_OFFSET_V) * INA_BUS_VOLTAGE_SCALE;
    currentA = (measuredCurrentA - INA_CURRENT_OFFSET_A) * INA_CURRENT_SCALE;
  }

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
    } else {
      temperatureOK = false;
      lastTemperatureRetryMs = millis();
    }
  }

  latestVibrationRmsG = vibrationRmsG;
  latestVoltageV = voltageV;
  latestCurrentA = currentA;
  latestTemperatureC = temperatureC;
  latestAdxlReadingOK = adxlReadingOK;
  latestInaOK = inaOK;
  latestTemperatureReadingOK = temperatureReadingOK;
  sampleSequence++;

  // Test indication only: this is not yet a calibrated motor-fault classifier.
  if (!adxlReadingOK || !inaOK || !temperatureReadingOK) {
    setStatusLeds(false, false, true);  // red: sensor missing/read failed
  } else if (voltageV < MOTOR_BUS_PRESENT_THRESHOLD_V) {
    setStatusLeds(false, true, false);  // yellow: sensors work, motor supply not present at INA bus
  } else {
    setStatusLeds(true, false, false);  // green: sensors work and voltage is present at INA bus
  }

  server.handleClient();
  delay(250);
}
