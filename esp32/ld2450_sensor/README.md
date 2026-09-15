# ESP32 + Hi-Link LD2450 mmWave Radar Integration

## 1. Overview
This module connects the **Hi-Link LD2450 24 GHz mmWave radar** to an **ESP32**, parses the raw 256000 bps binary target frames, formats the data into lightweight JSON, and transmits it to the Python backend over local Wi-Fi.

---

## 2. Hardware Wiring & Pinout

| LD2450 Pin | ESP32 Pin (Default) | Notes |
|:---|:---|:---|
| **VCC** | **5V / VIN** | Requires 5V (peak 250mA during chirp emissions). Do NOT use 3.3V pin. |
| **GND** | **GND** | Common ground with ESP32. |
| **TX** | **GPIO 16 (RX2)** | Radar transmits data to ESP32 RX. Configurable in firmware. |
| **RX** | **GPIO 17 (TX2)** | ESP32 transmits commands/config to Radar. |

> [!IMPORTANT]
> Ensure common ground between the radar and ESP32. If using a separate 5V regulator for the radar, connect regulator GND to ESP32 GND.

---

## 3. LD2450 Radar Protocol Specifications

- **Operating Frequency:** 24.00 GHz – 24.25 GHz (ISM band)
- **Detection Range:** 0.2m – 8.0m (max)
- **Field of View (FOV):** ±60° horizontal azimuth (120° total cone)
- **Baud Rate:** `256000 bps` (8 data bits, no parity, 1 stop bit)
- **Target Tracking Capacity:** Up to 3 independent moving targets concurrently

### Frame Structure (29 bytes total):
```
[Header: 4 bytes] -> 0xAA 0xFF 0x03 0x00
[Target 1: 8 bytes] -> X (2B), Y (2B), Speed (2B), DistRes (2B)
[Target 2: 8 bytes] -> X (2B), Y (2B), Speed (2B), DistRes (2B)
[Target 3: 8 bytes] -> X (2B), Y (2B), Speed (2B), DistRes (2B)
[Tail: 2 bytes]   -> 0x55 0xCC
```

---

## 4. JSON Transmission Format to Backend

The ESP32 sends an HTTP POST request to:
`POST http://<laptop_ip>:8000/api/radar/ingest`

### Payload Example:
```json
{
  "sensor_id": "RADAR_01",
  "targets": [
    {
      "id": 1,
      "x": -45.2,
      "y": 320.0,
      "speed": 1.25
    },
    {
      "id": 2,
      "x": 80.0,
      "y": 480.5,
      "speed": -0.80
    }
  ]
}
```
- `x`: Signed horizontal displacement from sensor centerline in centimeters (negative = left, positive = right).
- `y`: Forward perpendicular distance in centimeters.
- `speed`: Target velocity in meters/second (positive = approaching radar, negative = departing).

---

## 5. Firmware Configuration

In `ld2450_sensor.ino`:
```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_URL   = "http://10.146.49.142:8000/api/radar/ingest";

#define RADAR_RX_PIN 16
#define RADAR_TX_PIN 17
#define RADAR_BAUD   256000
```

---

## 6. Verification & Troubleshooting
1. Open the Arduino IDE Serial Monitor at **115200 bps** to view diagnostic logs.
2. If targets are not reported, ensure the LD2450 is placed horizontally with the antenna facing forward into the surveillance zone.
3. If Wi-Fi fails to connect, the system will fall back to local serial output. In the Python backend, set `SYSTEM_MODE=SIMULATED` to run without hardware.
