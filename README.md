# Automated Traffic Management System (ATMS)
### Emergency Vehicle Signal Preemption Module

---

## Overview

This project implements a software simulation of an Automated Traffic Management System designed to provide unobstructed passage to emergency vehicles, specifically ambulances, at controlled four-way intersections.

Upon detection of a 434 MHz radio frequency signal broadcast by the emergency vehicle, the system suspends the standard traffic signal cycle, clears the intersection, and assigns a green signal exclusively to the ambulance approach corridor. Normal operation resumes automatically upon clearance.

The system is developed for deployment on Raspberry Pi hardware with GPIO-connected traffic signal LEDs and an RTL-SDR receiver unit. In the absence of physical hardware, all external dependencies are replaced with manual user input for simulation purposes.

---

## Scope

- Four-directional intersection signal control (North, South, East, West)
- Emergency vehicle detection via 434 MHz RF signal
- Automatic preemption of normal traffic cycle
- Safe transition sequences with all-red intermediate states
- Automatic timeout and cycle resumption if clearance is not confirmed
- Persistent event logging to file and console

---

## System Workflow

```
[1] System starts       Normal four-way signal cycle begins
[2] Ambulance TX        Operator presses RF broadcast button at 434 MHz
[3] Receiver scan       Intersection receiver confirms signal presence
[4] Direction input     Operator selects ambulance approach direction
[5] Preemption          All signals set to RED (safety pause)
                        Ambulance corridor set to GREEN
[6] Clearance wait      System waits for operator confirmation or auto-timeout (120s)
[7] Transition          Ambulance corridor: GREEN to YELLOW to RED
[8] Resumption          Normal signal cycle resumes
```

---

## Requirements

**Software**

- Python 3.10 or later
- No third-party libraries required for simulation mode

**Hardware (for physical deployment)**

| Component | Specification |
|---|---|
| Single-board computer | Raspberry Pi 3B or later |
| RF transmitter module | 434 MHz ASK/OOK module |
| RF receiver module | RTL-SDR USB dongle |
| Signal LEDs | Red, Yellow, Green per direction (12 total) |
| GPIO connections | As per PIN_MAP in source file |

---

## Installation and Execution

```bash
git clone https://github.com/<organisation>/atms.git
cd atms
python itms_system.py
```

No additional installation steps are required for simulation mode. The system runs entirely through standard library modules.

---

## File Structure

```
atms/
|-- itms_system.py       Main system file
|-- itms_log.txt         Auto-generated event log (created on first run)
|-- README.md            Project documentation
```

---

## Configuration Parameters

The following constants are defined at the top of `itms_system.py` and may be adjusted prior to deployment.

| Parameter | Default | Description |
|---|---|---|
| GREEN_DURATION | 20 s | Duration of green phase per direction pair |
| YELLOW_DURATION | 3 s | Duration of yellow transition |
| RED_DURATION | 2 s | All-red inter-phase gap |
| SAFETY_PAUSE_SEC | 2 s | All-red pause before ambulance green |
| AMBULANCE_TIMEOUT_SEC | 120 s | Auto-resume if clearance not confirmed |
| DEBOUNCE_WINDOW_SEC | 5 s | Minimum interval between valid RF detections |
| AMBULANCE_FREQ_MHZ | 434 MHz | RF detection frequency |
| SIGNAL_THRESHOLD_DB | 10 dB | Minimum signal power for detection |

---

## Known Limitations

1. The current implementation simulates RF detection through manual user input. Integration with RTL-SDR hardware requires the `pyrtlsdr` library and appropriate driver installation.
2. GPIO control is simulated through in-memory LED objects. Physical LED control requires the `gpiozero` and `RPi.GPIO` libraries with correct pin wiring as per `PIN_MAP`.
3. The system currently handles one emergency event at a time. Concurrent multi-ambulance scenarios are not supported in this version.

---

## Drawbacks Addressed

The following deficiencies present in the original prototype have been corrected in this implementation.

| Issue | Resolution |
|---|---|
| No button debounce | Lock and timestamp-based cooldown window |
| Abrupt signal transitions | Yellow intermediate state before every phase change |
| No intersection clearing | Mandatory all-red safety pause before ambulance green |
| Indefinite system freeze | 120-second auto-timeout with automatic resumption |
| Race conditions on signal state | Threading lock on all LED state operations |
| Unrecoverable on keyboard interrupt | Finally block ensures all-red state on exit |
| No audit trail | Timestamped logging to console and itms_log.txt |
| Unvalidated user input | Looped prompt with explicit error handling |
| Irrelevant ML module | Removed; not applicable to signal preemption logic |

---

# How to Use the ITMS Simulation 

---

- To use this Intelligent Traffic Management System (ITMS) simulation, execute the main() function. The system will first initialize the traffic intersection and begin a normal, alternating four-way traffic cycle. You will see the current traffic light states printed in your output.

- You will then be presented with a menu. To simulate an ambulance emergency, select option 1. To exit the program, choose option 2.

- Selecting option 1 will prompt you to simulate an ambulance's RF broadcast by pressing Enter. The system will then ask you to confirm if a signal was detected (respond 'yes' or 'no'). If confirmed, you'll choose the ambulance's direction (North, South, East, or West) by entering a corresponding number. The traffic lights will then switch to an all-red safety pause, followed by a green light for the ambulance's direction.

- After the ambulance lane turns green, you'll be asked to press Enter once the ambulance has cleared the intersection. If no input is received within 120 seconds, the system will automatically resume normal operation. Upon clearance (manual or timed), the ambulance lane's green light will transition through yellow to red, and the system will return to its regular traffic cycle.

- You can initiate a clean shutdown at any time by selecting option 2 from the main menu or by pressing Ctrl+C (KeyboardInterrupt). The system ensures all lights turn red before terminating.

---

## Authors

Developed as part of an academic project under the subject domain of Automated Transportation Systems.

---

## License

This project is released for academic and non-commercial use only. Project maintained and developed by Mihir Panchal.
