/*
  Multimodal Motor Fault Diagnosis - ESP32 sensor streamer

  CSV output at 115200 baud:
  Vibration_RMS_g,Voltage_V,Current_A,Temperature_C

  Libraries (Arduino IDE Library Manager):
  - Adafruit MPU6050
  - Adafruit Unified Sensor
  - Adafruit INA219
  - OneWire
  - DallasTemperature

  Wiring:
  MPU6050: VCC->3V3, GND->GND, SDA->GPIO21, SCL->GPIO22
  INA219:  VCC->3V3, GND->GND, SDA->GPIO21, SCL->GPIO22
  DS18B20: VDD->3V3, GND->GND, DATA->GPIO4, 4.7k pull-up DATA-to-3V3
*/
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_INA219.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <math.h>

static const int SDA_PIN = 21;
static const int SCL_PIN = 22;
static const int ONE_WIRE_PIN = 4;
static const uint32_t SERIAL_BAUD = 115200;
static const int VIBRATION_SAMPLES = 100;
static const uint16_t SAMPLE_DELAY_MS = 5;

Adafruit_MPU6050 mpu;
Adafruit_INA219 ina219;
OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature ds18b20(&oneWire);

bool mpuReady = false;
bool inaReady = false;
bool tempReady = false;

float readVibrationRmsG() {
  double sum = 0.0;
  double sumSquares = 0.0;

  for (int i = 0; i < VIBRATION_SAMPLES; i++) {
    sensors_event_t accel, gyro, temp;
    mpu.getEvent(&accel, &gyro, &temp);

    // Magnitude of acceleration (m/s^2); remove the mean magnitude
    // over this short window to reduce the static gravity component.
    const double magnitude = sqrt(
      accel.acceleration.x * accel.acceleration.x +
      accel.acceleration.y * accel.acceleration.y +
      accel.acceleration.z * accel.acceleration.z
    );

    sum += magnitude;
    sumSquares += magnitude * magnitude;
    delay(SAMPLE_DELAY_MS);
  }

  const double mean = sum / VIBRATION_SAMPLES;
  double variance = (sumSquares / VIBRATION_SAMPLES) - (mean * mean);
  if (variance < 0.0) variance = 0.0;

  const double rmsMetersPerSecondSquared = sqrt(variance);
  return (float)(rmsMetersPerSecondSquared / 9.80665);
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);

  mpuReady = mpu.begin(0x68, &Wire);
  if (mpuReady) {
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }

  inaReady = ina219.begin(&Wire);

  ds18b20.begin();
  tempReady = ds18b20.getDeviceCount() > 0;

  // Keep diagnostics on a separate comment-style line. The dashboard
  // ignores anything other than four numeric comma-separated fields.
  Serial.println("# ESP32 motor sensor streamer started");
  Serial.print("# MPU6050: "); Serial.println(mpuReady ? "OK" : "NOT_FOUND");
  Serial.print("# INA219: "); Serial.println(inaReady ? "OK" : "NOT_FOUND");
  Serial.print("# DS18B20: "); Serial.println(tempReady ? "OK" : "NOT_FOUND");
  Serial.println("Vibration_RMS_g,Voltage_V,Current_A,Temperature_C");
}

void loop() {
  if (!(mpuReady && inaReady && tempReady)) {
    delay(1000);
    return;
  }

  const float vibrationRmsG = readVibrationRmsG();

  // INA219 bus voltage is the voltage measured at VIN- relative to GND.
  // Current depends on correct placement and module/shunt ratings.
  const float voltageV = ina219.getBusVoltage_V();
  const float currentA = ina219.getCurrent_mA() / 1000.0f;

  ds18b20.requestTemperatures();
  const float temperatureC = ds18b20.getTempCByIndex(0);

  if (temperatureC == DEVICE_DISCONNECTED_C ||
      !isfinite(vibrationRmsG) || !isfinite(voltageV) ||
      !isfinite(currentA) || !isfinite(temperatureC)) {
    Serial.println("# Invalid sensor reading; check sensor wiring");
    delay(500);
    return;
  }

  Serial.print(vibrationRmsG, 4); Serial.print(",");
  Serial.print(voltageV, 3); Serial.print(",");
  Serial.print(currentA, 4); Serial.print(",");
  Serial.println(temperatureC, 2);

  delay(250);
}
