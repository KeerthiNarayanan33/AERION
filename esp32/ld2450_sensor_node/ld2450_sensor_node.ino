/**
 * ============================================================================
 * SIH 2026: AI-POWERED MULTI-SENSOR BORDER SURVEILLANCE & INTRUSION DETECTION
 * ESP32 + LD2450 24GHz mmWave Radar IoT Sensor Node Firmware
 * ============================================================================
 * 
 * Hardware:
 *   - ESP32 NodeMCU / DevKit V1 (38-pin or 30-pin)
 *   - Hilink LD2450 24GHz FMCW mmWave Radar Module
 * 
 * Wiring Configuration:
 *   - LD2450 VCC  <---> ESP32 5V / VIN (Requires dedicated 5V 200mA+ rail)
 *   - LD2450 GND  <---> ESP32 GND
 *   - LD2450 TX   <---> ESP32 GPIO 16 (Serial2 RX)
 *   - LD2450 RX   <---> ESP32 GPIO 17 (Serial2 TX)
 *   - Status LED  <---> ESP32 GPIO 2 (Built-in Blue LED)
 * 
 * Communication:
 *   - UART2: 256000 Baud, 8-N-1 (LD2450 Factory Default)
 *   - Wi-Fi: 802.11 b/g/n (2.4 GHz)
 *   - Protocol: HTTP REST JSON POST -> http://<LAPTOP_IP>:8000/api/radar/ingest
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ============================================================================
// 1. CONFIGURATION PARAMETERS (User Configurable)
// ============================================================================
const char* WIFI_SSID     = "BORDER_SURVEILLANCE_WIFI";
const char* WIFI_PASS     = "SecureTactical2026";
const char* SERVER_URL    = "http://192.168.1.100:8000/api/radar/ingest";
const char* SENSOR_ID     = "RADAR_01";

#define RADAR_RX_PIN 16
#define RADAR_TX_PIN 17
#define STATUS_LED_PIN 2

#define LD2450_BAUD_RATE 256000
#define REPORT_INTERVAL_MS 200  // 5 Hz Telemetry Stream

// ============================================================================
// 2. DATA STRUCTURES
// ============================================================================
struct RadarTarget {
  int id;
  int16_t x_cm;        // Lateral displacement (+/- cm)
  int16_t y_cm;        // Forward distance (cm)
  int16_t speed_cms;   // Radial approach/departure velocity (+/- cm/s)
  uint16_t resolution; // Distance resolution / confidence
  bool valid;
};

RadarTarget targets[3];
HardwareSerial RadarSerial(2);

unsigned long lastSendTime = 0;
unsigned long lastLedBlink = 0;

// ============================================================================
// 3. SETUP
// ============================================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("==================================================");
  Serial.println("  SIH 2026: LD2450 RADAR SENSOR NODE INITIALIZING ");
  Serial.println("==================================================");

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);

  // Initialize Radar UART2
  RadarSerial.begin(LD2450_BAUD_RATE, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);
  Serial.printf("[RADAR] Serial2 configured on RX:%d, TX:%d at %d baud.\n", RADAR_RX_PIN, RADAR_TX_PIN, LD2450_BAUD_RATE);

  // Connect to Wi-Fi
  connectWiFi();
}

// ============================================================================
// 4. MAIN LOOP
// ============================================================================
void loop() {
  // 1. Maintain Wi-Fi Connection
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(STATUS_LED_PIN, LOW);
    connectWiFi();
  }

  // 2. Ingest LD2450 Binary Packets
  readRadarPackets();

  // 3. Periodically Transmit JSON Telemetry to Central Command
  unsigned long now = millis();
  if (now - lastSendTime >= REPORT_INTERVAL_MS) {
    lastSendTime = now;
    transmitRadarData();
  }
}

// ============================================================================
// 5. RADAR PROTOCOL DECODER
// ============================================================================
void readRadarPackets() {
  // LD2450 Standard Frame is 30 bytes:
  // Header: 0xAA 0xFF 0x03 0x00 (4 bytes)
  // Target 1: X(2), Y(2), Speed(2), Res(2) = 8 bytes
  // Target 2: 8 bytes
  // Target 3: 8 bytes
  // Tail: 0x55 0xCC (2 bytes)

  while (RadarSerial.available() >= 30) {
    // Search for 4-byte frame header
    if (RadarSerial.read() == 0xAA) {
      if (RadarSerial.read() == 0xFF) {
        if (RadarSerial.read() == 0x03) {
          if (RadarSerial.read() == 0x00) {
            uint8_t payload[26];
            int bytesRead = RadarSerial.readBytes(payload, 26);
            if (bytesRead == 26 && payload[24] == 0x55 && payload[25] == 0xCC) {
              parseFrame(payload);
            }
          }
        }
      }
    }
  }
}

void parseFrame(uint8_t* buf) {
  for (int i = 0; i < 3; i++) {
    int offset = i * 8;
    int16_t raw_x = buf[offset] | (buf[offset + 1] << 8);
    int16_t raw_y = buf[offset + 2] | (buf[offset + 3] << 8);
    int16_t raw_speed = buf[offset + 4] | (buf[offset + 5] << 8);
    uint16_t raw_res = buf[offset + 6] | (buf[offset + 7] << 8);

    targets[i].id = i + 1;

    // LD2450 Sign Bit Decoding: MSB indicates negative coordinate
    if (raw_x & 0x8000) {
      targets[i].x_cm = -(raw_x & 0x7FFF);
    } else {
      targets[i].x_cm = raw_x;
    }

    if (raw_speed & 0x8000) {
      targets[i].speed_cms = -(raw_speed & 0x7FFF);
    } else {
      targets[i].speed_cms = raw_speed;
    }

    targets[i].y_cm = raw_y;
    targets[i].resolution = raw_res;

    // Valid if target has positive depth
    targets[i].valid = (raw_y > 20 && raw_y < 850);
  }
}

// ============================================================================
// 6. JSON TELEMETRY TRANSMITTER
// ============================================================================
void transmitRadarData() {
  int activeCount = 0;
  for (int i = 0; i < 3; i++) {
    if (targets[i].valid) activeCount++;
  }

  // If no targets present, transmit empty keepalive heartbeat
  String json = "{";
  json += "\"sensor_id\":\"" + String(SENSOR_ID) + "\",";
  json += "\"targets\":[";

  bool first = true;
  for (int i = 0; i < 3; i++) {
    if (targets[i].valid) {
      if (!first) json += ",";
      first = false;
      json += "{";
      json += "\"id\":" + String(targets[i].id) + ",";
      json += "\"x\":" + String(targets[i].x_cm) + ",";
      json += "\"y\":" + String(targets[i].y_cm) + ",";
      json += "\"speed\":" + String(targets[i].speed_cms) + ",";
      json += "\"resolution\":" + String(targets[i].resolution);
      json += "}";
    }
  }
  json += "]}";

  // Transmit HTTP POST
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");

    int httpCode = http.POST(json);
    if (httpCode == 200) {
      digitalWrite(STATUS_LED_PIN, HIGH);
    } else {
      digitalWrite(STATUS_LED_PIN, LOW);
      Serial.printf("[HTTP] POST failed, code: %d\n", httpCode);
    }
    http.end();
  }
}

// ============================================================================
// 7. WI-FI MANAGER
// ============================================================================
void connectWiFi() {
  Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected successfully!");
    Serial.printf("[WIFI] Node IP: %s\n", WiFi.localIP().toString().c_str());
    digitalWrite(STATUS_LED_PIN, HIGH);
  } else {
    Serial.println("\n[WIFI] Connection failed. Retrying in background...");
  }
}
