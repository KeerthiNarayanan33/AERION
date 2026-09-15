/*
 * ==============================================================================
 * SENTINEL-AI: ESP32 + Hilink LD2450 mmWave Radar Wi-Fi Node
 * Smart India Hackathon (SIH) 2026 Prototype
 * ==============================================================================
 * 
 * Hardware Connections:
 * LD2450 VCC  -> ESP32 5V (or external 5V regulator, >=250mA)
 * LD2450 GND  -> ESP32 GND
 * LD2450 TX   -> ESP32 RX2 (Default GPIO 16, configurable)
 * LD2450 RX   -> ESP32 TX2 (Default GPIO 17, configurable)
 * 
 * Serial Protocol:
 * Baud Rate: 256000 bps, 8-N-1
 * Packet Header: 0xAA 0xFF 0x03 0x00
 * Packet Tail:   0x55 0xCC
 * Maximum Concurrent Targets: 3 (Target 1, Target 2, Target 3)
 */

#include <WiFi.h>
#include <HTTPClient.h>

// --- Network Configuration ---
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_URL   = "http://10.146.49.142:8000/api/radar/ingest";

// --- Hardware Pins (Configurable) ---
#define RADAR_RX_PIN 16
#define RADAR_TX_PIN 17
#define RADAR_BAUD   256000

// Target Data Model
struct RadarTarget {
    bool valid;
    int16_t x;       // mm (signed: negative is left, positive is right)
    int16_t y;       // mm (distance forward)
    int16_t speed;   // cm/s (signed: positive is approaching, negative is departing)
    uint16_t dist_res; // mm distance resolution
};

RadarTarget targets[3];
HardwareSerial RadarSerial(2);

unsigned long lastPostTime = 0;
const unsigned long POST_INTERVAL_MS = 100; // 10Hz radar transmission

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n[ESP32] Initializing LD2450 Radar Ingestion Node...");

    // Initialize Radar Hardware UART
    RadarSerial.begin(RADAR_BAUD, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);
    Serial.printf("[ESP32] Radar UART initialized on RX:%d, TX:%d at %d bps\n", RADAR_RX_PIN, RADAR_TX_PIN, RADAR_BAUD);

    // Connect to Wi-Fi
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("[ESP32] Connecting to Wi-Fi: %s", WIFI_SSID);
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[ESP32] Connected! IP Address: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[ESP32] Wi-Fi connection timeout. Continuing radar parsing in offline/serial mode.");
    }
}

void loop() {
    readRadarFrames();

    if (millis() - lastPostTime >= POST_INTERVAL_MS) {
        lastPostTime = millis();
        sendRadarData();
    }
}

// Parses raw LD2450 frame: 0xAA 0xFF 0x03 0x00 ... 0x55 0xCC
void readRadarFrames() {
    static uint8_t buffer[64];
    static int bufIdx = 0;

    while (RadarSerial.available() > 0) {
        uint8_t b = RadarSerial.read();

        // Check for 4-byte header: 0xAA 0xFF 0x03 0x00
        if (bufIdx == 0 && b != 0xAA) continue;
        if (bufIdx == 1 && b != 0xFF) { bufIdx = 0; continue; }
        if (bufIdx == 2 && b != 0x03) { bufIdx = 0; continue; }
        if (bufIdx == 3 && b != 0x00) { bufIdx = 0; continue; }

        buffer[bufIdx++] = b;

        // Frame total size is 29 bytes for 3 targets + 4 byte header + 2 byte tail
        if (bufIdx >= 29) {
            // Check tail: 0x55 0xCC
            if (buffer[27] == 0x55 && buffer[28] == 0xCC) {
                parseTargetData(&buffer[4]); // Target payload starts at index 4
            }
            bufIdx = 0;
        }
    }
}

void parseTargetData(uint8_t* p) {
    // LD2450 reports up to 3 targets, 8 bytes per target
    for (int i = 0; i < 3; i++) {
        int offset = i * 8;

        // X coordinate (2 bytes signed)
        int16_t x_raw = (int16_t)(p[offset] | (p[offset + 1] << 8));
        if (x_raw & 0x8000) {
            targets[i].x = -(x_raw & 0x7FFF);
        } else {
            targets[i].x = x_raw;
        }

        // Y coordinate (2 bytes signed)
        int16_t y_raw = (int16_t)(p[offset + 2] | (p[offset + 3] << 8));
        if (y_raw & 0x8000) {
            targets[i].y = -(y_raw & 0x7FFF);
        } else {
            targets[i].y = y_raw;
        }

        // Speed (2 bytes signed, cm/s)
        int16_t speed_raw = (int16_t)(p[offset + 4] | (p[offset + 5] << 8));
        if (speed_raw & 0x8000) {
            targets[i].speed = -(speed_raw & 0x7FFF);
        } else {
            targets[i].speed = speed_raw;
        }

        // Distance resolution (2 bytes unsigned, mm)
        targets[i].dist_res = (uint16_t)(p[offset + 6] | (p[offset + 7] << 8));

        // Mark target valid if Y distance > 0 and within 8m range
        targets[i].valid = (targets[i].y > 0 && targets[i].y <= 8500);
    }
}

void sendRadarData() {
    if (WiFi.status() != WL_CONNECTED) return;

    // Construct lightweight JSON packet
    String json = "{\"sensor_id\":\"RADAR_01\",\"targets\":[";
    bool first = true;

    for (int i = 0; i < 3; i++) {
        if (!targets[i].valid) continue;
        if (!first) json += ",";
        first = false;

        json += "{\"id\":" + String(i + 1);
        json += ",\"x\":" + String(targets[i].x / 10.0, 1); // convert to cm
        json += ",\"y\":" + String(targets[i].y / 10.0, 1); // convert to cm
        json += ",\"speed\":" + String(targets[i].speed / 100.0, 2); // convert to m/s
        json += "}";
    }
    json += "]}";

    // Send HTTP POST
    HTTPClient http;
    http.begin(BACKEND_URL);
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(json);
    
    if (httpCode > 0 && httpCode != 200) {
        Serial.printf("[ESP32] POST response: %d\n", httpCode);
    }
    http.end();
}
