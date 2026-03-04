# Automated Traffic Management System (ATMS)

**Version:** 2.5  
**Classification:** Research and Development Prototype  
**Technology Domain:** Intelligent Transportation Systems  
**Primary Language:** Python 3.10+, JavaScript (ES2022)  
**Interface Protocol:** WebSocket (RFC 6455)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Repository Structure](#3-repository-structure)
4. [Technical Specifications](#4-technical-specifications)
5. [Dependencies and Requirements](#5-dependencies-and-requirements)
6. [Installation and Deployment](#6-installation-and-deployment)
7. [Configuration Parameters](#7-configuration-parameters)
8. [WebSocket Communication Protocol](#8-websocket-communication-protocol)
9. [Signal Control Logic](#9-signal-control-logic)
10. [Emergency Vehicle Preemption](#10-emergency-vehicle-preemption)
11. [RF Detection Subsystem](#11-rf-detection-subsystem)
12. [Dashboard Interface](#12-dashboard-interface)
13. [Hardware Integration](#13-hardware-integration)
14. [Known Limitations](#14-known-limitations)
15. [License](#15-license)

---

## 1. Project Overview

This repository contains the source code for an Automated Traffic Management System developed as an intelligent intersection control prototype. The system simulates and manages a four-way signalised intersection using a server-side simulation engine, real-time WebSocket data streaming, and a browser-based monitoring and control dashboard.

The primary objective of this system is to demonstrate a software architecture suitable for deployment in smart city traffic infrastructure, specifically addressing the following operational requirements:

- Automated four-phase signal cycling with configurable phase durations
- Manual signal override capability for traffic control operators
- Emergency vehicle detection via radio frequency (RF) signal at 434 MHz, with automatic signal preemption restricted to the approach direction of the detected vehicle
- Per-direction signal state management ensuring that only one approach direction holds a green signal at any given time
- Real-time monitoring accessible from desktop and mobile terminals without requiring client-side application installation

The simulation engine operates entirely on the server. The browser client performs no traffic computation; it receives state snapshots via WebSocket and renders the received data. This separation ensures that browser performance does not affect simulation accuracy and allows multiple simultaneous observers on a shared intersection state.

---

## 2. System Architecture

### 2.1 Component Overview

The system consists of three principal components:

**Backend Simulation Engine (`simulation.py`)**  
A pure Python module containing all traffic logic. It maintains the signal state machine, vehicle spawn and movement physics, stop-line enforcement, car-following model, emergency override state, and historical data aggregation. The engine is stateless with respect to the network layer; it exposes a single `tick(dt)` method that advances simulation time by `dt` seconds and returns a complete state snapshot.

**WebSocket Server (`server.py`)**  
A FastAPI application that hosts the frontend, accepts WebSocket connections, runs a background asyncio ticker at 10 Hz, and broadcasts the engine snapshot to all connected clients after each tick. Incoming client messages are dispatched to the engine as commands.

**Browser Dashboard (`frontend/index.html`)**  
A single-file HTML application that connects to the WebSocket endpoint, renders the intersection canvas, signal state indicators, RF receiver visualisation, historical charts, and operator controls. The file contains no simulation logic. All rendered state originates from the server.

### 2.2 Data Flow

```
Operator Action (browser)
        |
        | JSON command over WebSocket
        v
server.py  ->  _handle_command()  ->  engine.set_mode() / set_duration() / trigger_ambulance()
        |
        | asyncio tick loop (100 ms interval)
        v
engine.tick(dt)
        |
        | returns snapshot dict
        v
server.py broadcasts JSON payload to all connected WebSocket clients
        |
        v
Browser receives {"type": "tick", "data": <snapshot>}
        |
        v
apply(data) -> renderFrame() + update DOM panels
```

### 2.3 Concurrency Model

The server uses a single asyncio event loop. The simulation engine is synchronous and not thread-safe. All mutations to engine state occur within the event loop, serialised by the asyncio scheduler. No locks are required under this model. If the system is extended to accept concurrent writes from external hardware integrations, synchronisation mechanisms must be introduced.

---

## 3. Repository Structure

```
atms/
|
|-- backend/
|   |-- server.py          # FastAPI application and WebSocket broadcast loop
|   |-- simulation.py      # Traffic simulation engine and signal state machine
|
|-- frontend/
|   |-- index.html         # Single-file browser dashboard (renderer only)
|
|-- static/                # Directory for additional static assets
|
|-- requirements.txt       # Python package dependencies
|-- README.md              # This document
```

---

## 4. Technical Specifications

### 4.1 Simulation Engine

| Parameter | Value |
|---|---|
| Virtual coordinate space | 800 x 600 units |
| Intersection centre | (400, 300) |
| Road width | 130 units |
| Stop margin from intersection edge | 30 units |
| Minimum vehicle gap (car-following) | 38 units |
| Vehicle speed range | 55 to 80 units per second |
| Maximum concurrent vehicles | 30 |
| Vehicle spawn interval | 4.0 seconds |
| Simulation tick rate | 10 Hz (100 ms intervals) |
| History buffer length | 70 samples (approximately 70 seconds) |

### 4.2 Signal Timing Defaults

| Phase | Default Duration |
|---|---|
| Green (active direction pair) | 20 seconds |
| Yellow (transitioning direction pair) | 3 seconds |
| Red (opposing direction pair) | Equal to active green duration |

All durations are configurable at runtime via the operator dashboard or via WebSocket command. Accepted range: green 5 to 60 seconds, yellow 2 to 10 seconds.

### 4.3 Phase Sequence

The four-phase signal sequence is fixed as follows:

```
NS_green -> NS_yellow -> EW_green -> EW_yellow -> (repeat)
```

During `NS_green`, the North and South approaches hold green; East and West hold red.  
During `EW_green`, the East and West approaches hold green; North and South hold red.  
Yellow phases apply only to the direction pair that is transitioning from green; the opposing pair remains on red throughout.

At no point in the normal cycle do more than two opposing directions share a green state simultaneously.

### 4.4 Emergency Preemption Timing

| Parameter | Value |
|---|---|
| Emergency override duration | 12 seconds |
| Directions granted green during override | 1 (approach direction only) |
| Directions held red during override | 3 (all remaining approaches) |
| Post-clearance resumption | Automatic return to NS_green with standard auto cycle |

---

## 5. Dependencies and Requirements

### 5.1 Server Requirements

| Requirement | Minimum Version |
|---|---|
| Python | 3.10 |
| fastapi | 0.110.0 |
| uvicorn (with standard extras) | 0.29.0 |
| websockets | 12.0 |

### 5.2 Client Requirements

The browser client requires no installation. The following browser versions support all features used:

| Browser | Minimum Version |
|---|---|
| Google Chrome | 94 |
| Mozilla Firefox | 93 |
| Apple Safari | 15.4 |
| Microsoft Edge | 94 |

Features used: WebSocket API, Canvas 2D API, CSS Custom Properties, `roundRect()` canvas method, CSS `clip-path`.

### 5.3 Network Requirements

The server and client must be reachable over a network that permits WebSocket connections on the configured port (default 8000). Reverse proxy configurations must be set to pass `Upgrade: websocket` headers without modification.

---

## 6. Installation and Deployment

### 6.1 Cloning the Repository

```bash
git clone https://github.com/<organisation>/<repository>.git
cd atms
```

### 6.2 Installing Python Dependencies

It is recommended to use a Python virtual environment to isolate dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 6.3 Starting the Server

```bash
cd backend
uvicorn server:app --host 0.0.0.0 --port 8000
```

For development with automatic reload on file changes:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 6.4 Accessing the Dashboard

Open a web browser and navigate to:

```
http://localhost:8000
```

If accessing from a device on the same local network, replace `localhost` with the server's local IP address. Multiple browser sessions may connect simultaneously; all sessions will observe the same shared simulation state.

### 6.5 Production Deployment

For production deployment, it is recommended to place uvicorn behind a reverse proxy such as Nginx. A minimal Nginx configuration for WebSocket proxying is provided below.

```nginx
server {
    listen 80;
    server_name your.domain.example;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400;
    }
}
```

For TLS termination, configure the certificate at the Nginx layer. The application itself requires no TLS configuration changes.

---

## 7. Configuration Parameters

The following constants in `backend/simulation.py` may be adjusted prior to deployment. Runtime adjustment is not supported for these values; a server restart is required.

| Constant | Default | Description |
|---|---|---|
| `MAX_CARS` | 30 | Maximum number of vehicles in the simulation at any time |
| `SPAWN_INTERVAL` | 4.0 | Seconds between vehicle spawn attempts |
| `CAR_SPEED_MIN` | 55 | Minimum vehicle speed in virtual units per second |
| `CAR_SPEED_MAX` | 80 | Maximum vehicle speed in virtual units per second |
| `ROAD_WIDTH` | 130 | Width of each road in virtual units |
| `STOP_MARGIN` | 30 | Distance from intersection edge at which vehicles stop |
| `FOLLOW_GAP` | 38 | Minimum headway gap enforced by the car-following model |
| `TICK_RATE` | 0.10 | Simulation tick interval in seconds (in `server.py`) |

Default phase durations are set in the `DEFAULT_DURATIONS` dictionary and may also be adjusted in `simulation.py`. These serve as the initial values loaded at server startup; operators may override them at runtime via the dashboard.

---

## 8. WebSocket Communication Protocol

The server and client communicate using JSON-encoded text frames over a single WebSocket connection per client session.

### 8.1 Endpoint

```
ws://<host>:<port>/ws
```

### 8.2 Server-to-Client Messages

The server emits one message type at the broadcast tick rate (10 Hz).

**Message type: `tick`**

```json
{
  "type": "tick",
  "data": {
    "signal": {
      "phase": "NS_green",
      "label": "GREEN",
      "color": "#00ff88",
      "countdown": 14.2,
      "max_dur": 20.0,
      "auto_mode": true,
      "emg_active": false,
      "emg_dir": null,
      "cycle_count": 3,
      "dirs": {
        "N": "green",
        "S": "green",
        "E": "red",
        "W": "red"
      }
    },
    "cars": [
      {
        "id": 12,
        "dir": "N",
        "x": 432.0,
        "y": 287.3,
        "color": "#3af",
        "is_emg": false,
        "waiting": false
      }
    ],
    "stats": {
      "total": 8,
      "waiting": 3,
      "moving": 5,
      "avg_wait": 4.2,
      "total_cleared": 47,
      "total_emg": 1,
      "vehicles_hr": 440
    },
    "queues": {
      "N": 2,
      "S": 0,
      "E": 1,
      "W": 0
    },
    "history": {
      "vehicles": [4, 5, 6, 7, 8],
      "wait": [1.2, 2.0, 3.1],
      "cleared": [0, 5, 10]
    },
    "events": [
      {
        "msg": "Phase NS_green to NS_yellow (3s)",
        "type": "info",
        "ts": "14:22:05"
      }
    ]
  }
}
```

Field descriptions for the `signal` object:

| Field | Type | Description |
|---|---|---|
| `phase` | string | Current phase identifier. One of: `NS_green`, `NS_yellow`, `EW_green`, `EW_yellow` |
| `label` | string | Display label. One of: `GREEN`, `YELLOW`, `RED`, `EMERGENCY` |
| `color` | string | Hex colour code corresponding to the current label |
| `countdown` | float | Remaining seconds in the current phase |
| `max_dur` | float | Total duration of the current phase in seconds |
| `auto_mode` | boolean | True when the signal is cycling automatically |
| `emg_active` | boolean | True when emergency preemption is in effect |
| `emg_dir` | string or null | Direction code of the emergency approach, or null |
| `cycle_count` | integer | Number of complete signal cycles completed since server start |
| `dirs` | object | Per-direction signal state. Keys: `N`, `S`, `E`, `W`. Values: `green`, `yellow`, or `red` |

### 8.3 Client-to-Server Commands

Clients send JSON objects to issue commands to the engine. The server does not send acknowledgement responses; the result of any command will be observable in the subsequent tick broadcasts.

**Set signal mode**

```json
{ "cmd": "set_mode", "mode": "auto" }
{ "cmd": "set_mode", "mode": "NS" }
{ "cmd": "set_mode", "mode": "EW" }
{ "cmd": "set_mode", "mode": "allred" }
```

| Mode value | Effect |
|---|---|
| `auto` | Resumes automatic four-phase cycling |
| `NS` | Forces North and South approaches to green immediately |
| `EW` | Forces East and West approaches to green immediately |
| `allred` | Holds all approaches on red until mode is changed |

**Set phase duration**

```json
{ "cmd": "set_duration", "dtype": "green", "value": 25 }
{ "cmd": "set_duration", "dtype": "yellow", "value": 4 }
{ "cmd": "set_duration", "dtype": "red", "value": 20 }
```

The `value` field is an integer in seconds. Accepted range: 2 to 120. Values outside this range are clamped by the engine.

**Trigger emergency preemption**

```json
{ "cmd": "trigger_ambulance" }
```

Initiates emergency vehicle preemption. If a preemption event is already active, this command is ignored. The approach direction is assigned randomly by the server for simulation purposes. In a hardware-integrated deployment, this command would be issued by the RF detection subsystem upon confirmed signal detection.

---

## 9. Signal Control Logic

### 9.1 Normal Operation

Under automatic mode, the signal controller advances through the four-phase sequence on countdown expiry. Each transition is logged to the event stream with the outgoing phase, incoming phase, and incoming phase duration.

The countdown is decremented in real time by the elapsed wall-clock interval between server ticks. The tick interval is nominally 100 milliseconds, but the actual elapsed time `dt` is measured using `time.perf_counter()` to avoid cumulative drift.

### 9.2 Stop-Line Enforcement

Each approach direction has a computed stop-line position based on the intersection centre coordinates, road half-width, and stop margin. A vehicle is evaluated for stop-line enforcement if the following conditions are all true:

- The vehicle's approach direction does not have a green signal
- The vehicle has not yet crossed the stop line in the current traversal
- The vehicle is within the stop-detection zone (within 45 virtual units of the stop line)

If enforcement applies, the vehicle's velocity is set to zero. Once a vehicle has crossed the stop line, the `passed` flag is set and enforcement is no longer applied for that traversal. This allows vehicles already committed to the intersection to clear without interruption when a phase changes.

### 9.3 Car-Following Model

In addition to stop-line enforcement, vehicles are subject to a simplified car-following constraint. Before advancing, each vehicle checks whether any preceding vehicle in the same lane is stationary within the minimum headway gap. If so, the following vehicle also holds its position. This produces realistic queue formation upstream of the stop line.

### 9.4 Manual Override

Manual override commands immediately cancel the automatic cycle timer and set the signal to the requested state. The `allred` mode does not set a countdown; the signal remains in the all-red state until a subsequent mode command is received. Manual overrides are blocked while emergency preemption is active.

---

## 10. Emergency Vehicle Preemption

### 10.1 Preemption Sequence

Upon detection of an emergency RF signal, the following sequence is executed by the engine:

1. The emergency flag is set and the approach direction is recorded.
2. Automatic cycling is suspended.
3. The signal state is evaluated using the emergency branch: the approach direction is granted green; all other directions are held on red.
4. An emergency vehicle is introduced into the simulation at the approach direction entry point.
5. An internal timer begins counting down from the configured emergency time-to-live (12 seconds).
6. All operator manual override commands are blocked for the duration of the preemption.
7. Upon timer expiry, the emergency flag is cleared, automatic cycling resumes from `NS_green`, and normal operations continue.

### 10.2 State Isolation

The signal state evaluation function `dir_is_green()` uses the emergency branch exclusively when `emg_active` is true. This ensures that no other code path can inadvertently grant green to a non-emergency direction during preemption, regardless of the recorded `phase` field.

The `phase` field is set to `NS_yellow` during preemption as a neutral state. Its value is not used for signal determination while the emergency branch is active; it serves only to ensure a valid phase identifier is present in the serialised snapshot for client display purposes.

---

## 11. RF Detection Subsystem

### 11.1 Simulation Mode

In the current prototype, the RF detection subsystem is simulated. The operator dashboard provides a "Simulate Ambulance" control that issues a `trigger_ambulance` command to the server. The dashboard also renders a waveform visualisation representing the 434 MHz receiver signal, transitioning from a low-amplitude noise baseline to a high-amplitude sinusoidal signal during an active preemption event.

The visualised power spectral density value transitions from a baseline of approximately -30 dB to +18.4 dB upon detection, consistent with the threshold comparison described in the original hardware specification.

### 11.2 Hardware Integration Path

To replace the simulated RF trigger with a physical RTL-SDR receiver, the following integration approach is recommended. This code is provided as a reference implementation and is not included in the production codebase.

```python
# Requires: pyrtlsdr
# pip install pyrtlsdr

from rtlsdr import RtlSdr
import numpy as np
import asyncio

async def rf_monitor(engine):
    sdr = RtlSdr()
    sdr.sample_rate = 2.4e6
    sdr.center_freq = 434e6
    sdr.gain = 'auto'

    while True:
        samples = sdr.read_samples(256 * 1024)
        power = np.abs(np.fft.fft(samples)) ** 2
        power_db = 10 * np.log10(power[0] + 1e-12)

        if power_db > 10.0:
            engine.trigger_ambulance()

        await asyncio.sleep(0.5)

    sdr.close()
```

This coroutine should be registered as an asyncio task at server startup alongside the existing ticker task. The threshold of 10 dB is consistent with the value defined in the original hardware project specification.

### 11.3 GPIO Integration for Physical Signal Heads

To drive physical traffic signal LEDs from a Raspberry Pi via GPIO, the following reference implementation applies. It is not included in the production codebase.

```python
# Requires: gpiozero
# pip install gpiozero

from gpiozero import LED

GPIO_MAP = {
    'N': {'red': LED(17), 'yellow': LED(18), 'green': LED(27)},
    'S': {'red': LED(22), 'yellow': LED(23), 'green': LED(24)},
    'E': {'red': LED(5),  'yellow': LED(6),  'green': LED(13)},
    'W': {'red': LED(19), 'yellow': LED(26), 'green': LED(21)},
}

def apply_gpio(signal_snapshot: dict):
    for direction, state in signal_snapshot['dirs'].items():
        for colour, led in GPIO_MAP[direction].items():
            if colour == state:
                led.on()
            else:
                led.off()
```

This function should be called once per tick within the broadcast loop in `server.py`, passing the `signal` portion of the snapshot dictionary.

---

## 12. Dashboard Interface

### 12.1 Responsive Layout

The dashboard is implemented as a single HTML file with no external JavaScript frameworks or build tools required. The layout adapts to three screen width breakpoints:

| Breakpoint | Layout |
|---|---|
| Below 640 px (mobile) | Single-column canvas view with bottom navigation bar and slide-up information sheets |
| 640 px to 959 px (tablet) | Two-column layout with canvas and right panel (RF receiver, counters, event log) |
| 960 px and above (desktop) | Three-column layout with left panel (signal controls), canvas, and right panel |

### 12.2 Left Panel (Desktop)

Contains the following controls and displays:

- Active signal phase indicator with traffic light widget, phase label, countdown timer, and progress bar
- Current active green direction indicator
- Per-direction signal state badges for all four approaches (N, S, E, W)
- Manual override mode buttons (Auto, N/S Green, E/W Green, All Red)
- Phase duration sliders for green, yellow, and red phases
- Live vehicle counters (total, waiting, moving, emergency)
- Per-approach queue length bars

### 12.3 Right Panel (Tablet and Desktop)

Contains the following:

- RF receiver canvas with live waveform, signal power display, and detection status indicator
- Emergency simulation control button
- Live counters (tablet only, when left panel is not visible)
- Timestamped event log with colour-coded entry types (info, ok, warn, alert)

### 12.4 Mobile Navigation

On screens below 640 px, four navigation tabs are presented at the bottom of the screen:

| Tab | Content |
|---|---|
| Map | Full-screen intersection canvas with signal overlay bar |
| Signal | Active phase widget, per-direction badges, live counters |
| Control | Manual override buttons, phase duration sliders, queue bars |
| RF / Log | RF receiver visualisation, emergency simulation button, event log |

Each tab opens a slide-up sheet that can be dismissed by tapping the close button or by dragging the sheet downward.

### 12.5 Canvas Rendering

The intersection canvas uses the HTML5 Canvas 2D API. Rendering operates at the rate of incoming WebSocket frames, nominally 10 Hz. The static road geometry is pre-rendered to an offscreen canvas on first draw and on every window resize; subsequent frames blit this cached image and draw only the dynamic elements (stop lines, signal heads, vehicles).

Vehicle positions are drawn using the coordinate values received in each snapshot. Coordinate transformation from the virtual 800 x 600 space to the physical canvas pixel dimensions is applied at render time using linear scaling functions, ensuring correct proportions at any window size.

---

## 13. Hardware Integration

The following table summarises the integration points available for connecting the software system to physical infrastructure components.

| Component | Integration Point | Method |
|---|---|---|
| RTL-SDR RF receiver (434 MHz) | `engine.trigger_ambulance()` | asyncio coroutine reading SDR samples |
| Raspberry Pi GPIO (signal LEDs) | Post-tick callback with `signal.dirs` snapshot | `gpiozero` LED objects keyed by direction and colour |
| External sensor input (inductive loop, IR, camera) | `engine._spawn_car()` or vehicle count feed | Direct method call or WebSocket command extension |
| Database event logging | `engine.events` list | SQLite or InfluxDB write on each tick |
| Remote monitoring | WebSocket `/ws` endpoint | Any WebSocket-capable client |

Reference implementations for RTL-SDR and GPIO integration are provided in Section 11 of this document.

---

## 14. Known Limitations

**Single intersection.** The current simulation models one four-way intersection. Multi-intersection coordination, green wave synchronisation, and arterial signal timing are not implemented.

**No persistent storage.** Simulation state is held in memory. A server restart resets all counters, cycle counts, and history buffers. No database integration is included in the base installation.

**Simplified vehicle model.** Vehicles travel in straight lines only. Turn movements, U-turns, and lane changes are not modelled. Each direction has one lane.

**No authentication or access control.** The WebSocket endpoint and operator controls are accessible to any client that can reach the server. In a production deployment, authentication middleware must be added.

**Single process, no failover.** The application runs as a single uvicorn process. No clustering, process supervision, or failover configuration is provided.

**Emergency direction is randomised in simulation mode.** The approach direction assigned during a simulated ambulance event is selected at random by the server. In a hardware-integrated deployment this would be determined by direction-specific RF sensor placement or a separate localisation mechanism.

**CORS policy is open.** The server is configured to accept cross-origin requests from any origin. This should be restricted to known origins in production.

---

## 15. License

This project is released for research, educational, and prototype evaluation purposes. Refer to the `LICENSE` file included in the repository for the terms of use, redistribution conditions, and warranty disclaimer.

For enquiries regarding deployment, integration, or adaptation for operational use in public infrastructure, contact the maintaining organisation through the repository issue tracker.
