# RC FPV Drone Communication Protocol Analysis & Reverse-Engineering Report

**Target APK**: `reverse engineering/base.apk`  
**Application Title**: RC FPV  
**Analysis Date**: September 2026  
**Target Architecture**: Android DEX Bytecode (Dalvik / ART), Pure Java Socket Implementation  

---

## Executive Summary

Static reverse-engineering of `reverse engineering/base.apk` revealed that the physical Wi-Fi quadcopter uses a **pure UDP-based command and telemetry architecture** paired with an **RTSP/H.264/MJPEG live video stream** on dedicated ports. No native proprietary C/C++ libraries (`.so`) are required for the standard Wi-Fi communication; all socket handling, joystick coordinate normalization, packet construction, XOR checksum calculations, and command loops are implemented in Java under package `com.cooingdv.rcfpv`.

The drone hosts a Wi-Fi Access Point acting as a DHCP server (assigning the mobile client an IP on `192.168.1.x`), while the drone itself resides statically at `192.168.1.1`.

---

## Systematic Protocol Specification (Items 1 – 21)

### 1. Android Package Name
* **Package Identifier**: `com.cooingdv.rcfpv`
* **Application Class**: `com.cooingdv.rcfpv.base.MainApplication`
* **Primary Flight Activity**: `com.cooingdv.rcfpv.activity.GenericActivity`
* **Primary Flight Fragment**: `com.cooingdv.rcfpv.fragment.DeviceBLFragment`
* **Declared Version**: `2.3.6` (versionCode `236`)

---

### 2. Drone IP Address
* **Static IP**: `192.168.1.1`
* **Code Reference**:
  * `com.cooingdv.rcfpv.socket.Config.SERVER_IP = "192.168.1.1"`
  * `com.cooingdv.rcfpv.socket.Config.TCP_SERVER_HOST = "192.168.1.1"`
  * `com.cooingdv.rcfpv.socket.Config.FTP_HOST = "192.168.1.1"`
  * Hardcoded in `com.cooingdv.rcfpv.socket.SocketClient.startUdpTask()`:
    ```java
    UdpComm.getInstance("192.168.1.1", 7099);
    ```

---

### 3. UDP and TCP Ports
The drone firmware exposes multiple standard and proprietary ports:

| Service / Function | Protocol | Port | Description / Source Class |
| :--- | :--- | :--- | :--- |
| **Flight Control & Commands** | **UDP** | **`7099`** | Primary bidirectional command channel (`SocketClient.java`, `UdpComm.java`). |
| **Live FPV Video Streaming** | **RTSP** | **`7070`** | RTSP server delivering camera stream (`Config.PREVIEW_ADDRESS`). |
| **HTTP Web Server** | **TCP** | **`80`** | Photo/Thumbnail access (`Config.PHOTO_HTTP_PATH`). |
| **FTP File Server** | **TCP** | **`21`** | Media download (`Config.FTP_HOST`, user: `ftp`, pass: `ftp`). |
| **Reserved TCP Port** | **TCP** | **`5000`** | Defined in `Config.TCP_SERVER_PORT = 5000` (heartbeat interval 5000ms). |

---

### 4. RTSP / Video Streaming Address
* **Live Camera Stream URL**:
  ```text
  rtsp://192.168.1.1:7070/webcam
  ```
  * Defined in `com.cooingdv.rcfpv.socket.Config.PREVIEW_ADDRESS`.
  * Initialized in `com.cooingdv.rcfpv.socket.SocketClient.initVideoView()`:
    ```java
    mVideoView.setVideoPath("rtsp://192.168.1.1:7070/webcam");
    ```
* **Recorded Video Playback Stream**:
  ```text
  rtsp://192.168.1.1:7070/file/DCIM/{filename}
  ```
  * Defined in `com.cooingdv.rcfpv.socket.Config.VIDEO_LIVE_PATH(String filename)`.
* **Photo HTTP Download Paths**:
  * Full resolution: `http://192.168.1.1/PHOTO/O/{filename}`
  * Thumbnail: `http://192.168.1.1/PHOTO/T/{filename}`

---

### 5. Network Communication Classes
All network transmission logic is encapsulated in the following classes:

1. **`com.cooingdv.rcfpv.socket.Config`**:
   Static repository of IP addresses, ports, URLs, buffer limits, and timer constants.
2. **`com.cooingdv.rcfpv.socket.UdpComm`**:
   Low-level UDP socket manager wrapping `java.net.DatagramSocket`. Runs dedicated asynchronous sender (`SendDataThread`) and receiver (`RecvDataThread`) threads.
3. **`com.cooingdv.rcfpv.socket.SocketClient`**:
   High-level connection manager (Singleton). Manages the `1000ms` heartbeat task (`HeartBeatTask`), camera switching requests, and UDP transmission locks.
4. **`com.cooingdv.rcfpv.tools.FlyController`**:
   Flight control state machine. Holds current axis values (Roll, Pitch, Throttle, Yaw) and boolean states (Takeoff, Land, Emergency Stop, Headless, Gyro Calibration).
5. **`com.cooingdv.rcfpv.tools.FlyController$FlyControlTask`**:
   `java.util.TimerTask` running every `50ms` (20 Hz). Performs deadzone processing, clamps values, calculates the 8-bit XOR checksum, packages the frame, and triggers transmission.
6. **`com.cooingdv.rcfpv.tools.FlyCommand`**:
   Interface containing command identifiers, protocol action strings, and CTP IDs.

---

### 6. Socket Implementation Details
* **Socket Type**: Standard non-blocking `java.net.DatagramSocket` over UDP.
* **Threading Architecture**:
  * **`SendDataThread`**: Uses an internal queue (`LinkedBlockingQueue`) or direct call via `UdpComm.sendData(byte[] data)`. Constructs a `java.net.DatagramPacket(data, data.length, InetAddress.getByName("192.168.1.1"), 7099)` and calls `socket.send(packet)`.
  * **`RecvDataThread`**: Runs in a `while (isRunning)` loop calling `socket.receive(packet)` into a `1024`-byte buffer. Upon reception, forwards the byte array to `UdpCommCallback.onReceiveData(byte[] data)`.
  * **Concurrency Protection**: `SocketClient` uses a `java.util.concurrent.locks.ReentrantLock` (`sendLock`) to serialize all calls into `udpComm.send([B)`.

---

### 7. Command Constants
Defined in `com.cooingdv.rcfpv.tools.FlyCommand`:

| Constant Name | Value | Purpose / Notes |
| :--- | :--- | :--- |
| **`CTP_ID_FLYING`** | `"3"` (byte `0x03`) | Message Type ID prepended to flight control packets. |
| **`CMD_FLYING_CONTROL`**| `"0136"` | Flight control subsystem identifier. |
| **`CMD_FLYING_CTRL`** | `"FLYING_CTRL"` | Action string for control state toggling. |
| **`CMD_TAKE_OFF`** | `"0143"` | Auto-takeoff command code. |
| **`CMD_FAST_DROP`** | `"0144"` | Auto-landing command code. |
| **`CMD_EMERGENCY_STOP`**| `"0145"` | Emergency motor kill code. |
| **`CMD_360_TURN`** | `"0146"` | 360 degree aerial flip. |
| **`CMD_CHANGE_WORK_MODE`**| `"0147"` | Work mode transition. |
| **`CMD_COME_BACK`** | `"0142"` | Return to home (RTH). |
| **`CMD_FIXED_HEIGHT_MODE`**| `"0141"` | Altitude hold toggle. |
| **`CMD_NO_HEAD_MODE`** | `"0139"` | Headless orientation mode. |
| **`CMD_GYRO_CORRECTION`**| `"0138"` | Accelerometer / Gyroscope calibration. |
| **`CMD_GRAVITY_SENSOR`**| `"0137"` | Tilt-phone gravity sensor steering. |
| **`CMD_SEND_HEART`** | `"140"` | Heartbeat identifier (`[0x01, 0x01]`). |
| **`CMD_POWER_CONTROL`** | `"0129"` | Drone speed rate selection (30%, 60%, 100%). |
| **`CMD_SWITCH_CAMERA`** | `"SWITCH_CAMERA"` | Front vs bottom camera toggle (`[0x06, 0x01]` / `[0x06, 0x02]`). |

---

### 8. `CMD_TAKE_OFF` Implementation
* **Method**: `com.cooingdv.rcfpv.tools.FlyController.setFastFly(ImageView view)`
* **Byte Layout**: Asserted on **Bit 0 (0x01)** of **Byte 5** of the flight payload.
* **Execution Mechanics**:
  1. Sets `isFastFly = true`.
  2. Sets a 1000ms timer (`Handler.postDelayed`) via `FlyController$1`.
  3. During this 1-second pulse, the periodic 50ms flight loop sends packets with `Byte 5 |= 0x01`.
  4. After 1000ms, `isFastFly` is reset to `false`.
* **Full 9-byte UDP Packet (Neutral Sticks + Takeoff Pulse)**:
  ```text
  Hex:    03  66  80  80  80  80  01  01  99
  Bytes:  [3, 102, 128, 128, 128, 128, 1, 1, 153]
  ```

---

### 9. `CMD_FLYING_CONTROL` Implementation
* **Class & Method**: `com.cooingdv.rcfpv.tools.FlyController$FlyControlTask.run()`
* **Execution Mechanics**:
  * Executed every `50ms` (20 Hz) by `Timer.schedule(task, 50, 50)`.
  * Reads 4 axes:
    * `controlByte1`: Roll
    * `controlByte2`: Pitch
    * `controlAccelerator`: Throttle
    * `controlTurn`: Yaw
  * Computes the Byte 5 flags bitfield.
  * Calculates Byte 6 XOR checksum:
    $$\text{Checksum} = (\text{Roll} \oplus \text{Pitch} \oplus \text{Throttle} \oplus \text{Yaw} \oplus \text{Flags}) \ \& \ \text{0xFF}$$
  * Formats into the 8-byte core payload:
    `[0x66, Roll, Pitch, Throttle, Yaw, Flags, Checksum, 0x99]`
  * Prepends the CTP transport header `0x03` (`CTP_ID_FLYING`), resulting in a 9-byte packet.
  * Dispatches to `SocketClient.getInstance().debugSend(packet)`.

---

### 10. `CMD_FLYING_CTRL` Implementation
* **Method**: `com.cooingdv.rcfpv.tools.FlyController.setController(boolean isControlMode)`
* **Enabling Control (`setController(true)`)**:
  * Spawns a new `java.util.Timer()`.
  * Schedules `FlyControlTask` at fixed rate: `schedule(task, 50, 50)`.
* **Disabling Control (`setController(false)`)**:
  * Cancels `mFlyControlTimer`.
  * Immediately transmits a 2-byte stop packet via UDP to `192.168.1.1:7099`:
    ```text
    Hex:   08  01
    Bytes: [8, 1]
    ```

---

### 11. Landing Command (`CMD_FAST_DROP` / Auto-Land)
* **Method**: `com.cooingdv.rcfpv.tools.FlyController.setFastDrop(ImageView view)`
* **Byte Layout**: Asserted on **Bit 1 (0x02)** of **Byte 5** of the flight payload.
* **Execution Mechanics**:
  1. Sets `isFastDrop = true`.
  2. Posts a delayed runnable (`FlyController$2`) to clear `isFastDrop` after 1000ms.
  3. The 50ms flight loop sends `Byte 5 |= 0x02` continuously for 1 second.
* **Full 9-byte UDP Packet (Neutral Sticks + Land Pulse)**:
  ```text
  Hex:    03  66  80  80  80  80  02  02  99
  Bytes:  [3, 102, 128, 128, 128, 128, 2, 2, 153]
  ```

---

### 12. Emergency-Stop Command (`CMD_EMERGENCY_STOP`)
* **Method**: `com.cooingdv.rcfpv.tools.FlyController.setEmergencyStop(ImageView view)`
* **Byte Layout**: Asserted on **Bit 2 (0x04)** of **Byte 5** of the flight payload.
* **Execution Mechanics**:
  1. Sets `isEmergencyStop = true`.
  2. Posts a delayed runnable (`FlyController$3`) to clear `isEmergencyStop` after 1000ms.
  3. Sends `Byte 5 |= 0x04` in the flight loop, commanding the flight controller to cut motor PWM outputs immediately.
* **Full 9-byte UDP Packet (Emergency Stop Pulse)**:
  ```text
  Hex:    03  66  80  80  80  80  04  04  99
  Bytes:  [3, 102, 128, 128, 128, 128, 4, 4, 153]
  ```

---

### 13. Forward / Backward Control (Pitch)
* **Variable**: `FlyController.controlByte2`
* **Packet Position**: **Byte 2** of 8-byte payload (index 3 in 9-byte UDP packet).
* **Direction & Value Range**:
  * **Neutral / Level**: `128` (`0x80`)
  * **Forward**: `129` to `255` (`0x81` to `0xFF`). Maximum forward pitch is `255`.
  * **Backward**: `127` to `1` (`0x7F` to `0x01`). Maximum backward pitch is `1`.
* **Clamping**: Enforced in `FlyControlTask`:
  ```java
  if (controlByte2 > 255) controlByte2 = 255;
  if (controlByte2 < 1)   controlByte2 = 1;
  ```

---

### 14. Left / Right Control (Roll)
* **Variable**: `FlyController.controlByte1`
* **Packet Position**: **Byte 1** of 8-byte payload (index 2 in 9-byte UDP packet).
* **Direction & Value Range**:
  * **Neutral / Level**: `128` (`0x80`)
  * **Bank Right**: `129` to `255` (`0x81` to `0xFF`). Maximum right roll is `255`.
  * **Bank Left**: `127` to `1` (`0x7F` to `0x01`). Maximum left roll is `1`.
* **Clamping**: Clamped to `[1, 255]`.

---

### 15. Up / Down Control (Throttle)
* **Variable**: `FlyController.controlAccelerator`
* **Packet Position**: **Byte 3** of 8-byte payload (index 4 in 9-byte UDP packet).
* **Behavior by Flight Mode**:
  1. **Fixed-Height Mode (`isFixedHeightMode = true`)**:
     * Altitude hold active (barometer / optical flow).
     * **Hover (Zero vertical velocity)**: `128` (`0x80`).
     * **Climb (Ascend)**: `129` to `255` (`0x81` to `0xFF`).
     * **Descend**: `127` to `1` (`0x7F` to `0x01`).
  2. **Manual Throttle Mode (`isFixedHeightMode = false`)**:
     * Absolute motor power.
     * Bottom / Idle: `0` (`0x00`).
     * Note on clamping: In `FlyControlTask`, if `controlAccelerator == 1`, it is reset to `0`. Range: `0` to `255`.

---

### 16. Yaw / Rotation Control
* **Variable**: `FlyController.controlTurn`
* **Packet Position**: **Byte 4** of 8-byte payload (index 5 in 9-byte UDP packet).
* **Direction & Value Range**:
  * **Neutral (No rotation)**: `128` (`0x80`)
  * **Rotate Clockwise (Turn Right)**: `153` to `255` (`0x99` to `0xFF`).
  * **Rotate Counter-Clockwise (Turn Left)**: `1` to `103` (`0x01` to `0x67`).
* **Hardware Deadzone**:
  In `FlyControlTask.run()`, a deadzone window of $\pm 24$ counts around center is hardcoded:
  ```java
  if (controlTurn >= 104 && controlTurn <= 152) {
      controlTurn = 128; // Force neutral
  }
  ```

---

### 17. Hover / Stop Behavior
* **Hover State**:
  When all virtual joystick controls are released and fixed-height mode is active:
  * Roll = `128` (`0x80`)
  * Pitch = `128` (`0x80`)
  * Throttle = `128` (`0x80`)
  * Yaw = `128` (`0x80`)
  * Flags = `0` (`0x00`)
  * Checksum = $128 \oplus 128 \oplus 128 \oplus 128 \oplus 0 = 0$ (`0x00`)
* **Hover UDP Packet (Sent continuously at 20 Hz)**:
  ```text
  Hex:    03  66  80  80  80  80  00  00  99
  Bytes:  [3, 102, 128, 128, 128, 128, 0, 0, 153]
  ```
* **Exit Control / Motor Disarm**:
  When user turns off virtual controllers:
  ```text
  Hex:    08  01
  Bytes:  [8, 1]
  ```

---

### 18. Packet Structure and Byte Layout

#### A. Continuous Flight Control Packet (9 Bytes UDP to `192.168.1.1:7099`)
| Packet Index | Payload Field | Data Type | Range | Default / Neutral | Description |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **0** | **CTP Message ID** | `uint8` | `0x03` | `0x03` | Protocol packet identifier (`CTP_ID_FLYING`). |
| **1** | **Payload Header** | `uint8` | `0x66` | `0x66` | Start frame sentinel (Decimal: `102`). |
| **2** | **Roll (Left/Right)** | `uint8` | `1 – 255` | `128` (`0x80`) | `1`=Full Left, `128`=Neutral, `255`=Full Right. |
| **3** | **Pitch (Fwd/Back)** | `uint8` | `1 – 255` | `128` (`0x80`) | `1`=Full Backward, `128`=Neutral, `255`=Full Forward. |
| **4** | **Throttle (Up/Down)** | `uint8` | `0 – 255` | `128` (`0x80`) | `0`=Zero power, `128`=Hover, `255`=Max climb. |
| **5** | **Yaw (Rotation)** | `uint8` | `1 – 255` | `128` (`0x80`) | `1`=CCW Left, `128`=Neutral, `255`=CW Right. |
| **6** | **Flags Bitfield** | `uint8` | `0 – 255` | `0x00` | Takeoff, Land, Stop, Flip, Calibration bits. |
| **7** | **XOR Checksum** | `uint8` | `0 – 255` | Varies | `Byte[2] ^ Byte[3] ^ Byte[4] ^ Byte[5] ^ Byte[6]` |
| **8** | **Payload Footer** | `uint8` | `0x99` | `0x99` | End frame sentinel (Decimal: `153`). |

#### B. Byte 6 (Payload Byte 5) Flags Bitfield Decomposition
```text
  Bit 7      Bit 6      Bit 5      Bit 4      Bit 3      Bit 2      Bit 1      Bit 0
+----------+----------+----------+----------+----------+----------+----------+----------+
| Gyro Cal | Reserved | UnLock / | Headless | 360 Flip | Emer.Stop| Landing  | Take-Off |
|  (0x80)  |  (0x40)  | RTH(0x20)|  (0x10)  | End(0x08)|  (0x04)  |  (0x02)  |  (0x01)  |
+----------+----------+----------+----------+----------+----------+----------+----------+
```
* **Bit 0 (`0x01`)**: `isFastFly` — Auto Take-Off (1 second pulse).
* **Bit 1 (`0x02`)**: `isFastDrop` — Auto Land (1 second pulse).
* **Bit 2 (`0x04`)**: `isEmergencyStop` — Emergency Stop (cut motors).
* **Bit 3 (`0x08`)**: `isCircleTurnEnd` — 360 Degree Flip Trigger.
* **Bit 4 (`0x10`)**: `isNoHeadMode` — Headless Mode (maintained toggle).
* **Bit 5 (`0x20`)**: `isFastReturn` / `isUnLock` — Return-to-Home / Motor Arm.
* **Bit 6 (`0x40`)**: Reserved (always `0`).
* **Bit 7 (`0x80`)**: `isGyroCorrection` — Gyroscope Calibration (2 second pulse).

#### C. Auxiliary Packets (Sent to `192.168.1.1:7099`)
* **Heartbeat Packet** (Every 1000ms):
  ```text
  Hex: 01 01
  ```
* **Stop Flying / Exit Control Mode**:
  ```text
  Hex: 08 01
  ```
* **Camera Switch**:
  ```text
  Hex: 06 01  (Front Camera)
  Hex: 06 02  (Bottom Camera)
  ```
* **Hardware Button Response Acknowledgements**:
  * Photo trigger ack: `Hex: 09 01`
  * Video trigger ack: `Hex: 09 02`

---

### 19. Checksums or CRC
* **Algorithm**: 8-bit XOR Checksum.
* **Formula**:
  $$\text{Checksum} = (\text{Roll} \oplus \text{Pitch} \oplus \text{Throttle} \oplus \text{Yaw} \oplus \text{Flags}) \ \& \ \text{0xFF}$$
* **Decompiled Code Verification** (`FlyControlTask.run()` lines 118–134):
  ```java
  int v1 = controlByte1 ^ controlByte2;
  v1 ^= controlAccelerator;
  v1 ^= controlTurn;
  v1 ^= (flags & 0xFF);
  byte checksum = (byte) v1;
  ```
* **Scope**: Evaluated **only** across the 5 dynamic control bytes (Indices 2 through 6). The protocol headers (`0x03`, `0x66`) and footer (`0x99`) are excluded from the checksum.

---

### 20. Command Timing and Frequency
* **Flight Control Packet Interval**:
  * Timer scheduled at: **`50 ms`** (20 packets/sec, 20 Hz).
  * `Config.SEND_COMMAND_INTERVAL` is configured at `40 ms` (25 Hz); the active timer schedules at `50 ms`.
* **Heartbeat Interval**:
  * Transmitted every **`1000 ms`** (1 Hz).
* **Action Pulse Durations**:
  * Takeoff pulse: `1000 ms`
  * Landing pulse: `1000 ms`
  * Emergency stop pulse: `1000 ms`
  * Gyro calibration pulse: `2000 ms`

---

### 21. Joystick-to-Command Conversion Logic
Implemented in `com.cooingdv.rcfpv.libs.RockerView` and `com.cooingdv.rcfpv.fragment.DeviceBLFragment`:

#### Left Virtual Joystick (`rvVertical` — Yaw & Throttle)
The RockerView calculates touch offset $\Delta X, \Delta Y$ relative to joystick radius $R$:
$$\text{normX} = \frac{\Delta X}{R}, \quad \text{normY} = \frac{\Delta Y}{R} \quad \in [-1.0, +1.0]$$
Conversion to byte values:
$$\text{Yaw} = \text{round}(\text{normX} \times 127.0) + 128 + (\text{trim}_{\text{horiz}} \times 4)$$
$$\text{Throttle} = \text{round}(\text{normY} \times 127.0) + 128$$
*(Note: Android touch coordinate $\Delta Y$ is inverted so dragging up increases Throttle).*

#### Right Virtual Joystick (`rvHorizontal` — Roll & Pitch)
Uses speed sensitivity limits governed by `currPower`:
* **Low Speed (30%)**: $L_{\text{half}} = 40 \implies \text{Roll/Pitch} \in [88, 168]$
* **Medium Speed (60%)**: $L_{\text{half}} = 60 \implies \text{Roll/Pitch} \in [68, 188]$
* **High Speed (100%)**: $L_{\text{half}} = 127 \implies \text{Roll/Pitch} \in [1, 255]$

Conversion formulas:
$$\text{Roll} = \text{round}(\text{normX} \times L_{\text{half}}) + 128 + \text{trim}_{\text{roll}}$$
$$\text{Pitch} = \text{round}(\text{normY} \times L_{\text{half}}) + 128 + \text{trim}_{\text{pitch}}$$

---

## Standalone Python Drone Controller Reference

The following Python script implements the complete reverse-engineered protocol without any Android dependencies. It can run on a laptop connected to the drone's Wi-Fi network:

```python
"""
RC FPV Drone Wi-Fi Controller Client
Reverse-Engineered from com.cooingdv.rcfpv (base.apk)
"""

import socket
import threading
import time
from typing import Optional

class DroneController:
    # Network Constants
    DRONE_IP = "192.168.1.1"
    UDP_PORT = 7099
    RTSP_URL = "rtsp://192.168.1.1:7070/webcam"
    
    # Protocol Identifiers
    CTP_ID_FLYING = 0x03
    FRAME_HEADER = 0x66
    FRAME_FOOTER = 0x99
    
    # Flags (Byte 5 bitfield)
    FLAG_TAKEOFF = 0x01
    FLAG_LAND = 0x02
    FLAG_EMERGENCY_STOP = 0x04
    FLAG_FLIP_END = 0x08
    FLAG_HEADLESS = 0x10
    FLAG_UNLOCK_RTH = 0x20
    FLAG_GYRO_CAL = 0x80

    def __init__(self, ip: str = DRONE_IP, port: int = UDP_PORT):
        self.ip = ip
        self.port = port
        self.sock: Optional[socket.socket] = None
        
        # Axis state (1-255, 128 = Neutral)
        self.roll = 128
        self.pitch = 128
        self.throttle = 128
        self.yaw = 128
        self.flags = 0x00
        
        self.is_running = False
        self.tx_thread: Optional[threading.Thread] = None
        self.rx_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def connect(self):
        """Initializes UDP socket and launches transmission & heartbeat threads."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0)) # Ephemeral local port
        self.is_running = True
        
        # Start background threads
        self.tx_thread = threading.Thread(target=self._flight_loop, daemon=True)
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        
        self.tx_thread.start()
        self.rx_thread.start()
        self.heartbeat_thread.start()
        print(f"[+] Connected to drone at {self.ip}:{self.port}")

    def disconnect(self):
        """Stops transmission and issues control stop command."""
        self.is_running = False
        if self.sock:
            # Send stop command: [0x08, 0x01]
            try:
                self.sock.sendto(bytes([0x08, 0x01]), (self.ip, self.port))
            except Exception:
                pass
            self.sock.close()
            self.sock = None
        print("[*] Disconnected from drone.")

    def set_sticks(self, roll: int = 128, pitch: int = 128, throttle: int = 128, yaw: int = 128):
        """
        Updates axis inputs (clamped to 1..255).
        128 = Neutral / Hover.
        """
        with self.lock:
            self.roll = max(1, min(255, roll))
            self.pitch = max(1, min(255, pitch))
            self.throttle = max(0, min(255, throttle))
            
            # Apply built-in yaw deadzone [104, 152] -> 128
            if 104 <= yaw <= 152:
                self.yaw = 128
            else:
                self.yaw = max(1, min(255, yaw))

    def takeoff(self):
        """Sends takeoff pulse for 1.0 second."""
        def _pulse():
            with self.lock:
                self.flags |= self.FLAG_TAKEOFF
            time.sleep(1.0)
            with self.lock:
                self.flags &= ~self.FLAG_TAKEOFF
        threading.Thread(target=_pulse, daemon=True).start()

    def land(self):
        """Sends landing pulse for 1.0 second."""
        def _pulse():
            with self.lock:
                self.flags |= self.FLAG_LAND
            time.sleep(1.0)
            with self.lock:
                self.flags &= ~self.FLAG_LAND
        threading.Thread(target=_pulse, daemon=True).start()

    def emergency_stop(self):
        """Cuts motors immediately."""
        def _pulse():
            with self.lock:
                self.flags |= self.FLAG_EMERGENCY_STOP
            time.sleep(1.0)
            with self.lock:
                self.flags &= ~self.FLAG_EMERGENCY_STOP
        threading.Thread(target=_pulse, daemon=True).start()

    def calibrate_gyro(self):
        """Sends gyro calibration pulse for 2.0 seconds."""
        def _pulse():
            with self.lock:
                self.flags |= self.FLAG_GYRO_CAL
            time.sleep(2.0)
            with self.lock:
                self.flags &= ~self.FLAG_GYRO_CAL
        threading.Thread(target=_pulse, daemon=True).start()

    def switch_camera(self, camera_id: int = 1):
        """Switches front (1) or bottom (2) camera."""
        packet = bytes([0x06, 0x01 if camera_id == 1 else 0x02])
        if self.sock:
            self.sock.sendto(packet, (self.ip, self.port))

    def _build_packet(self) -> bytes:
        """Constructs the 9-byte CTP flight packet with XOR checksum."""
        with self.lock:
            r = self.roll
            p = self.pitch
            t = self.throttle
            y = self.yaw
            f = self.flags
            
        checksum = (r ^ p ^ t ^ y ^ f) & 0xFF
        return bytes([
            self.CTP_ID_FLYING,  # 0x03
            self.FRAME_HEADER,   # 0x66
            r, p, t, y, f,
            checksum,
            self.FRAME_FOOTER    # 0x99
        ])

    def _flight_loop(self):
        """Periodic 50ms (20 Hz) flight control loop."""
        while self.is_running:
            start_time = time.perf_counter()
            pkt = self._build_packet()
            try:
                self.sock.sendto(pkt, (self.ip, self.port))
            except Exception as e:
                print(f"[!] Send error: {e}")
            elapsed = time.perf_counter() - start_time
            sleep_time = max(0.001, 0.050 - elapsed)
            time.sleep(sleep_time)

    def _heartbeat_loop(self):
        """Periodic 1000ms (1 Hz) heartbeat loop."""
        while self.is_running:
            try:
                self.sock.sendto(bytes([0x01, 0x01]), (self.ip, self.port))
            except Exception:
                pass
            time.sleep(1.0)

    def _rx_loop(self):
        """Receives telemetry and hardware button events from drone."""
        while self.is_running:
            try:
                data, _ = self.sock.recvfrom(1024)
                if len(data) >= 3:
                    # Drone hardware button events
                    if data[2] == ord('M'): # 77: Camera photo trigger
                        self.sock.sendto(bytes([0x09, 0x01]), (self.ip, self.port)) # Ack
                    elif data[2] == ord('X'): # 88: Video record trigger
                        self.sock.sendto(bytes([0x09, 0x02]), (self.ip, self.port)) # Ack
            except Exception:
                break

if __name__ == "__main__":
    drone = DroneController()
    drone.connect()
    try:
        print("[*] Calibrating gyroscope...")
        drone.calibrate_gyro()
        time.sleep(2.5)
        
        print("[*] Sending Take-off command...")
        drone.takeoff()
        time.sleep(3.0)
        
        print("[*] Hovering...")
        time.sleep(2.0)
        
        print("[*] Landing...")
        drone.land()
        time.sleep(3.0)
    finally:
        drone.disconnect()
```

---

## Conclusion

The communication protocol for this Wi-Fi RC FPV drone has been completely reverse-engineered from the original Android application's bytecode. The entire flight control stack is implemented over a single UDP socket (`192.168.1.1:7099`) with a 50ms periodic 9-byte packet structure protected by an 8-bit XOR checksum, accompanied by an RTSP H.264 stream on `rtsp://192.168.1.1:7070/webcam`. All parameters, byte maps, and conversion formulas have been documented and validated.
