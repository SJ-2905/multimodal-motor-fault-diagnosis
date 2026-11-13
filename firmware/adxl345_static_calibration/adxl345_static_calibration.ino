#include <Wire.h>
#include <Adafruit_ADXL345_U.h>
#include <Adafruit_Sensor.h>

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;
constexpr float STANDARD_GRAVITY = 9.80665f;

Adafruit_ADXL345_Unified adxl(23456);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  bool found = adxl.begin(0x53);
  if (!found) found = adxl.begin(0x1D);
  if (!found) {
    Serial.println("ADXL345 not found at 0x53 or 0x1D. Check VCC, GND, SDA=21, SCL=22.");
    while (true) delay(1000);
  }

  adxl.setRange(ADXL345_RANGE_2_G);
  adxl.setDataRate(ADXL345_DATARATE_100_HZ);
  Serial.println("ADXL345 static calibration; hold still, then record mean values for each orientation.");
  Serial.println("Place each labeled axis pointing up (+1g), then down (-1g). Keep the other axes level.");
  Serial.println("ax_g,ay_g,az_g");
}

void loop() {
  sensors_event_t event;
  adxl.getEvent(&event);
  Serial.print(event.acceleration.x / STANDARD_GRAVITY, 5);
  Serial.print(',');
  Serial.print(event.acceleration.y / STANDARD_GRAVITY, 5);
  Serial.print(',');
  Serial.println(event.acceleration.z / STANDARD_GRAVITY, 5);
  delay(100);
}
