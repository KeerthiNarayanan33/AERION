# ESP32 + LD2450 24GHz mmWave Radar Hardware Integration Guide

## 1. System Overview
The ESP32 microcontroller acts as the edge IoT sensor node for the **Hilink LD2450 24GHz FMCW mmWave Radar**. It continuously ingests high-frequency binary tracking packets from the LD2450 over UART, parses multi-target spatial telemetry (lateral offset $X$, depth $Y$, approach velocity $V$, and resolution), and streams JSON packets over Wi-Fi to the central surveillance server at `/api/radar/ingest`.

---

## 2. Hardware Requirements & Specifications
1. **ESP32 Microcontroller**: NodeMCU-32S / ESP32 DevKit V1 (2.4 GHz 802.11 b/g/n Wi-Fi).
2. **Hilink LD2450 mmWave Radar**:
   - Operating Frequency: 24.00 GHz – 24.25 GHz
   - Maximum Tracking Range: 8.0 meters
   - Azimuth FOV: $\pm 60^\circ$ ($120^\circ$ total sweep cone)
   - Max Targets: 3 simultaneous targets tracked
   - Operating Voltage: 5V DC ($\ge 200\text{ mA}$ continuous)
   - Interface: 3.3V TTL UART (Factory Default: **256000 baud, 8-N-1**)
3. **Power Supply**: Stable 5V 2A micro-USB or external buck converter.

---

## 3. Physical Wiring Pinout

| ESP32 DevKit Pin | LD2450 Radar Pin | Signal Function | Notes |
| :--- | :--- | :--- | :--- |
| **VIN / 5V** | **VCC** | 5V Power In | **CRITICAL**: Do NOT power from 3.3V pin; LD2450 needs 5V rail |
| **GND** | **GND** | Ground Reference | Common ground with ESP32 |
| **GPIO 16 (RX2)** | **TX** | Radar Transmit Data | 3.3V logic level |
| **GPIO 17 (TX2)** | **RX** | Radar Receive Data | 3.3V logic level |
| **GPIO 2 (Built-in)** | — | Status LED | Blinks on telemetry transmission; Solid on Wi-Fi connected |

> [!WARNING]
> **Power Supply Stability**: The LD2450 draws current spikes during high-frequency FMCW chirping. If powered from a noisy USB port or thin jumper wires, the ESP32 or radar may brown out. Use high-quality jumper wires directly to the 5V/VIN pin.

---

## 4. Software Setup & Flashing Instructions

### Option A: Arduino IDE
1. Open **Arduino IDE** (v2.x or v1.8.x).
2. Open **Boards Manager** and install **`esp32 by Espressif Systems`** (v2.0.x or v3.0.x).
3. Select Board: **`DOIT ESP32 DEVKIT V1`** or **`ESP32 Dev Module`**.
4. Open sketch: `esp32/ld2450_sensor_node/ld2450_sensor_node.ino`.
5. Update your local network credentials:
   ```cpp
   const char* WIFI_SSID  = "YOUR_WIFI_NAME";
   const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";
   const char* SERVER_URL = "http://192.168.1.XXX:8000/api/radar/ingest";
   ```
6. Click **Upload**.
7. Open Serial Monitor at **115200 baud** to view real-time connection status and IP address.

### Option B: PlatformIO
Add the following to your `platformio.ini`:
```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
src_dir = esp32/ld2450_sensor_node
```

---

## 5. Protocol & JSON Ingest Packet Format

The ESP32 transmits telemetry packets to the backend via HTTP POST:
```http
POST /api/radar/ingest HTTP/1.1
Host: 192.168.1.100:8000
Content-Type: application/json

{
  "sensor_id": "RADAR_01",
  "targets": [
    {
      "id": 1,
      "x": 80,
      "y": 320,
      "speed": -120,
      "resolution": 15
    }
  ]
}
```

- `sensor_id`: Identifier configured in the backend database.
- `x`: Lateral offset in centimeters (negative = left, positive = right).
- `y`: Forward depth distance in centimeters.
- `speed`: Radial velocity in cm/s (negative = approaching, positive = retreating).
- `resolution`: Target signal strength / confidence indicator.

---

## 6. Troubleshooting

1. **Radar Not Sending Data (Serial2 Silent)**:
   - Verify LD2450 baud rate is set to **256000**.
   - Swap TX and RX pins: ESP32 RX (16) must connect to LD2450 TX; ESP32 TX (17) connects to LD2450 RX.
2. **Wi-Fi Connection Fails**:
   - Ensure the Wi-Fi network is **2.4 GHz**. ESP32 does not support 5 GHz Wi-Fi.
3. **HTTP 404 / Connection Refused from Server**:
   - Verify your laptop's local IP using `ipconfig` (Windows) or `ifconfig` (Linux).
   - Ensure the FastAPI server is running with `--host 0.0.0.0` or bound to your local IP address so external devices on the LAN can reach it.
