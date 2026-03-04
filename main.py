"""
============================================================
  ITMS — Intelligent Traffic Management System
  Emergency Vehicle (Ambulance) Signal Preemption
============================================================

DRAWBACKS FIXED FROM ORIGINAL CODE:
  1.  No debounce      → Button press could register multiple times; fixed with lock + cooldown timer
  2.  No debounce      → RF scan could loop-detect same ambulance; fixed with last-detection timestamp
  3.  No safety pause  → Lights could flip directly green without clearing intersection; fixed with ALL-RED pause
  4.  No yellow trans. → Abrupt green→red caused confusion; fixed with yellow transition before every state change
  5.  No timeout       → System could wait forever for ambulance to pass; fixed with 120s auto-resume
  6.  No thread safety → Concurrent light changes could corrupt state; fixed with threading.Lock()
  7.  No interruption  → Normal cycle could not be cleanly paused; fixed with threading.Event flags
  8.  No logging       → No audit trail; fixed with logging to console + itms_log.txt
  9.  No input valid.  → Bad input crashed the program; fixed with looped validated prompts
  10. No shutdown safe → GPIO left in undefined state; fixed with ALL-RED + cleanup on exit
  11. No multi-ambu.   → Only one ambulance handled; fixed with re-entrant loop
  12. No direction ctl → Original had 1 signal, no 4-way logic; fixed with per-direction signal objects
  13. ML removed       → Linear regression was irrelevant to the scenario; removed entirely
  14. Hardware dep.    → RPi GPIO / RTL-SDR not always available; fully simulated with manual input

WORKFLOW (Sequential):
  [1] System boots → Normal 4-way traffic cycle starts (background thread)
  [2] Ambulance operator presses physical button → RF at 434 MHz transmitted
  [3] Intersection receiver detects 434 MHz → Ambulance confirmed
  [4] User selects ambulance approach direction
  [5] Emergency preemption: ALL signals → RED (safety), then ambulance lane → GREEN
  [6] System waits for ambulance to clear (user confirm or 120s timeout)
  [7] Transition: ambulance lane → YELLOW → RED → resume normal cycle
  [8] Repeat or exit cleanly
"""

import time
import threading
import logging
import sys
from datetime import datetime
from enum import Enum

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("itms_log.txt", mode="a"),
    ],
)
log = logging.getLogger("ITMS")


# ─────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────
class Signal(Enum):
    RED    = "RED"
    YELLOW = "YELLOW"
    GREEN  = "GREEN"


class Direction(Enum):
    NORTH = "North"
    SOUTH = "South"
    EAST  = "East"
    WEST  = "West"


# ─────────────────────────────────────────────
#  CONSTANTS  (adjust to real timings as needed)
# ─────────────────────────────────────────────
GREEN_DURATION          = 20    # seconds each direction pair stays green
YELLOW_DURATION         = 3     # seconds yellow transition
RED_DURATION            = 2     # seconds all-red before next green phase
AMBULANCE_FREQ_MHZ      = 434   # MHz
SIGNAL_THRESHOLD_DB     = 10    # dB – RF detection threshold
DEBOUNCE_WINDOW_SEC     = 5     # seconds – ignore repeat button presses
AMBULANCE_TIMEOUT_SEC   = 120   # seconds – auto-resume if ambulance doesn't clear
SAFETY_PAUSE_SEC        = 2     # seconds all-RED before giving green to ambulance


# ─────────────────────────────────────────────
#  SIMULATED LED  (represents a GPIO-connected LED on RPi)
# ─────────────────────────────────────────────
class SimulatedLED:
    def __init__(self, pin: int, color: str):
        self.pin   = pin
        self.color = color
        self.state = False

    def on(self):
        self.state = True

    def off(self):
        self.state = False


# ─────────────────────────────────────────────
#  SIMULATED RF TRANSMITTER  (on ambulance)
# ─────────────────────────────────────────────
class AmbulanceTransmitter:
    """
    Simulates the ambulance-side RF transmitter.
    In real hardware: a 434 MHz module triggered by a GPIO button on RPi.
    """

    def broadcast(self, freq_mhz: int) -> bool:
        log.info(f"[AMBULANCE TX]  Broadcasting RF signal at {freq_mhz} MHz ...")
        time.sleep(0.5)  # simulates transmission delay
        log.info(f"[AMBULANCE TX]  Signal sent successfully at {freq_mhz} MHz.")
        return True


# ─────────────────────────────────────────────
#  SIMULATED RF RECEIVER  (at intersection)
# ─────────────────────────────────────────────
class IntersectionReceiver:
    """
    Simulates the RTL-SDR dongle at the intersection.
    In real hardware: performs FFT on I/Q samples, checks PSD at 434 MHz.
    Here: user input simulates whether the signal is physically present.
    """

    def scan(self, freq_mhz: int, threshold_db: int) -> bool:
        log.info(f"[RECEIVER]      Scanning for RF at {freq_mhz} MHz (threshold: {threshold_db} dB) ...")
        while True:
            resp = input(
                f"    [SIMULATE HARDWARE] Signal detected at {freq_mhz} MHz? (yes / no): "
            ).strip().lower()
            if resp in ("yes", "y"):
                log.info(f"[RECEIVER]      ✅  Signal CONFIRMED at {freq_mhz} MHz.")
                return True
            elif resp in ("no", "n"):
                log.info(f"[RECEIVER]      ❌  No signal detected at {freq_mhz} MHz.")
                return False
            else:
                print("    ⚠  Please enter 'yes' or 'no'.")


# ─────────────────────────────────────────────
#  4-WAY TRAFFIC INTERSECTION
# ─────────────────────────────────────────────
class TrafficIntersection:
    """
    Models a 4-direction intersection.
    Each direction has independent RED / YELLOW / GREEN LEDs.
    Thread-safe via a single lock.
    """

    SIGNAL_ICONS = {Signal.RED: "🔴", Signal.YELLOW: "🟡", Signal.GREEN: "🟢"}

    # GPIO pin map: (direction, color) → pin number
    PIN_MAP = {
        (Direction.NORTH, Signal.RED):    11,
        (Direction.NORTH, Signal.YELLOW): 12,
        (Direction.NORTH, Signal.GREEN):  13,
        (Direction.SOUTH, Signal.RED):    14,
        (Direction.SOUTH, Signal.YELLOW): 15,
        (Direction.SOUTH, Signal.GREEN):  16,
        (Direction.EAST,  Signal.RED):    17,
        (Direction.EAST,  Signal.YELLOW): 18,
        (Direction.EAST,  Signal.GREEN):  19,
        (Direction.WEST,  Signal.RED):    20,
        (Direction.WEST,  Signal.YELLOW): 21,
        (Direction.WEST,  Signal.GREEN):  22,
    }

    def __init__(self, intersection_id: str):
        self.id    = intersection_id
        self._lock = threading.Lock()
        self._leds = {
            (d, c): SimulatedLED(pin, f"{d.value}-{c.value}")
            for (d, c), pin in self.PIN_MAP.items()
        }
        self._state: dict[Direction, Signal] = {d: Signal.RED for d in Direction}
        log.info(f"[INTERSECTION]  '{self.id}' initialised with all signals RED.")

    def set_signal(self, direction: Direction, color: Signal):
        """Set a single direction to a given signal color."""
        with self._lock:
            for sig in Signal:
                self._leds[(direction, sig)].off()
            self._leds[(direction, color)].on()
            self._state[direction] = color

    def set_all(self, color: Signal):
        """Set every direction to the same signal color."""
        for direction in Direction:
            self.set_signal(direction, color)

    def display(self):
        """Print a clean visual summary of all signal states."""
        border = "─" * 52
        print(f"\n  ┌{border}┐")
        print(f"  │  INTERSECTION [{self.id}]  —  {datetime.now().strftime('%H:%M:%S')}{'':>14}│")
        print(f"  ├{border}┤")
        for direction in Direction:
            color = self._state[direction]
            icon  = self.SIGNAL_ICONS[color]
            print(f"  │   {direction.value:<8}  {icon}  {color.value:<8}{'':>23}│")
        print(f"  └{border}┘\n")


# ─────────────────────────────────────────────
#  TRAFFIC CONTROLLER
# ─────────────────────────────────────────────
class TrafficController:
    """
    Drives the normal signal cycle and handles emergency preemption.

    Normal cycle (opposing pairs alternate green):
      Phase A: North + South → GREEN,  East + West → RED
      Phase B: East  + West  → GREEN,  North + South → RED

    Emergency override:
      ALL → RED (safety pause) → ambulance direction → GREEN
      On clearance: ambulance direction → YELLOW → ALL RED → resume normal
    """

    # Pairs of opposing directions that share a green phase
    CYCLE_PHASES = [
        (Direction.NORTH, Direction.SOUTH),
        (Direction.EAST,  Direction.WEST),
    ]

    def __init__(self, intersection: TrafficIntersection):
        self.intersection          = intersection
        self._stop_evt             = threading.Event()
        self._emergency_evt        = threading.Event()
        self._cycle_thread: threading.Thread | None = None
        self._phase_index          = 0
        self._active_green_dir: Direction | None = None

    # ── Normal Cycle ──────────────────────────────────────────────────────────

    def start(self):
        log.info("[CONTROLLER]    Normal traffic cycle STARTED.")
        self._cycle_thread = threading.Thread(
            target=self._run_cycle, daemon=True, name="NormalCycle"
        )
        self._cycle_thread.start()

    def _run_cycle(self):
        while not self._stop_evt.is_set():

            # Pause cleanly during emergency
            if self._emergency_evt.is_set():
                time.sleep(0.3)
                continue

            green_pair = self.CYCLE_PHASES[self._phase_index]
            red_dirs   = [d for d in Direction if d not in green_pair]

            # Set RED for the perpendicular pair first (avoid two greens at once)
            for d in red_dirs:
                self.intersection.set_signal(d, Signal.RED)
            # Set GREEN for the current phase pair
            for d in green_pair:
                self.intersection.set_signal(d, Signal.GREEN)

            log.info(f"[CYCLE]         GREEN → {[d.value for d in green_pair]}")
            self.intersection.display()

            # GREEN phase (interruptible every 0.3 s)
            self._interruptible_sleep(GREEN_DURATION)
            if self._emergency_evt.is_set() or self._stop_evt.is_set():
                continue

            # YELLOW transition
            for d in green_pair:
                self.intersection.set_signal(d, Signal.YELLOW)
            log.info(f"[CYCLE]         YELLOW → {[d.value for d in green_pair]}")
            self.intersection.display()

            self._interruptible_sleep(YELLOW_DURATION)
            if self._emergency_evt.is_set() or self._stop_evt.is_set():
                continue

            # ALL RED gap
            self.intersection.set_all(Signal.RED)
            log.info("[CYCLE]         RED → ALL  (inter-phase gap)")
            self.intersection.display()

            self._interruptible_sleep(RED_DURATION)

            # Advance phase
            self._phase_index = (self._phase_index + 1) % len(self.CYCLE_PHASES)

        log.info("[CONTROLLER]    Normal cycle thread exited.")

    def _interruptible_sleep(self, seconds: float):
        """Sleep in short ticks so we can react to events quickly."""
        ticks = int(seconds / 0.3)
        for _ in range(ticks):
            if self._emergency_evt.is_set() or self._stop_evt.is_set():
                return
            time.sleep(0.3)

    # ── Emergency Preemption ──────────────────────────────────────────────────

    def activate_preemption(self, direction: Direction):
        """Pause normal cycle and give green to ambulance direction."""
        log.warning(f"[EMERGENCY]     ⚠  PREEMPTION ACTIVATED — ambulance from {direction.value.upper()}")
        self._emergency_evt.set()

        # Wait briefly for the normal cycle thread to notice and pause
        time.sleep(0.5)

        # Safety ALL-RED pause before changing
        self.intersection.set_all(Signal.RED)
        log.info(f"[EMERGENCY]     All signals → RED  ({SAFETY_PAUSE_SEC}s safety pause)")
        self.intersection.display()
        time.sleep(SAFETY_PAUSE_SEC)

        # Give GREEN to ambulance direction only
        self.intersection.set_signal(direction, Signal.GREEN)
        self._active_green_dir = direction
        log.info(f"[EMERGENCY]     GREEN → {direction.value}  (ambulance corridor open)")
        self.intersection.display()

    def deactivate_preemption(self):
        """Transition back to normal cycle after ambulance clears."""
        log.info("[EMERGENCY]     Ambulance cleared — transitioning back to normal cycle ...")

        # YELLOW on ambulance direction before removing green
        if self._active_green_dir:
            self.intersection.set_signal(self._active_green_dir, Signal.YELLOW)
            log.info(f"[EMERGENCY]     YELLOW → {self._active_green_dir.value}  (transition)")
            self.intersection.display()
            time.sleep(YELLOW_DURATION)

        # ALL RED cooldown
        self.intersection.set_all(Signal.RED)
        log.info("[EMERGENCY]     All signals → RED  (cooldown before resuming normal cycle)")
        self.intersection.display()
        time.sleep(RED_DURATION)

        self._active_green_dir = None
        self._emergency_evt.clear()
        log.info("[CONTROLLER]    Normal traffic cycle RESUMED.")

    def stop(self):
        """Cleanly stop the controller and set all signals to RED."""
        log.info("[CONTROLLER]    Shutdown requested ...")
        self._stop_evt.set()
        self._emergency_evt.set()   # unblock cycle thread if paused in emergency
        if self._cycle_thread:
            self._cycle_thread.join(timeout=3)
        self.intersection.set_all(Signal.RED)
        log.info("[CONTROLLER]    All signals → RED. Controller stopped.")


# ─────────────────────────────────────────────
#  AMBULANCE RF HANDLER
# ─────────────────────────────────────────────
class AmbulanceRFHandler:
    """
    Coordinates the transmitter (ambulance) and receiver (intersection).
    Includes debounce protection to prevent multiple rapid triggers.
    """

    def __init__(self):
        self._transmitter        = AmbulanceTransmitter()
        self._receiver           = IntersectionReceiver()
        self._debounce_lock      = threading.Lock()
        self._last_detection_ts  = 0.0

    def simulate_button_press(self) -> bool:
        """
        Simulate ambulance operator pressing the physical RF broadcast button.
        A ENTER-press here represents the hardware button trigger.
        """
        print("\n" + "─" * 60)
        input("  [AMBULANCE]  Press ENTER to simulate the RF broadcast button press ...")
        return self._transmitter.broadcast(AMBULANCE_FREQ_MHZ)

    def detect_signal(self) -> bool:
        """
        Scan for 434 MHz signal with debounce guard.
        FIX: prevents a single ambulance from triggering preemption twice
             if the button is accidentally pressed multiple times rapidly.
        """
        with self._debounce_lock:
            now = time.time()
            elapsed = now - self._last_detection_ts
            if elapsed < DEBOUNCE_WINDOW_SEC:
                log.warning(
                    f"[DEBOUNCE]      Signal ignored — last detection was {elapsed:.1f}s ago "
                    f"(debounce window: {DEBOUNCE_WINDOW_SEC}s)."
                )
                return False

            detected = self._receiver.scan(AMBULANCE_FREQ_MHZ, SIGNAL_THRESHOLD_DB)
            if detected:
                self._last_detection_ts = now
            return detected


# ─────────────────────────────────────────────
#  HELPER: GET AMBULANCE DIRECTION
# ─────────────────────────────────────────────
def prompt_direction() -> Direction:
    """Prompt the operator to select the ambulance's approach direction."""
    options = {str(i + 1): d for i, d in enumerate(Direction)}
    print("\n  [INPUT]  Select the ambulance approach direction:")
    for key, d in options.items():
        print(f"           {key}. {d.value}")
    while True:
        choice = input("           Enter choice (1–4): ").strip()
        if choice in options:
            selected = options[choice]
            log.info(f"[INPUT]         Ambulance direction: {selected.value.upper()}")
            return selected
        print("           ⚠  Invalid choice. Enter a number between 1 and 4.")


# ─────────────────────────────────────────────
#  HELPER: WAIT FOR AMBULANCE TO CLEAR
# ─────────────────────────────────────────────
def wait_for_ambulance_to_clear() -> bool:
    """
    Wait for the operator to confirm the ambulance has passed.
    FIX: if confirmation never comes, auto-resume after AMBULANCE_TIMEOUT_SEC.
    """
    log.info(f"[WAITING]       Waiting for ambulance to pass ... (auto-resume in {AMBULANCE_TIMEOUT_SEC}s)")
    print(f"\n  Press ENTER once the ambulance has fully cleared the intersection.")
    print(f"  (Auto-resume in {AMBULANCE_TIMEOUT_SEC} seconds if no input.)\n")

    cleared   = threading.Event()
    timed_out = threading.Event()

    def _listen():
        try:
            input("")
            cleared.set()
        except Exception:
            cleared.set()

    def _timeout():
        time.sleep(AMBULANCE_TIMEOUT_SEC)
        if not cleared.is_set():
            timed_out.set()
            cleared.set()  # unblock main wait

    listener = threading.Thread(target=_listen,  daemon=True)
    timer    = threading.Thread(target=_timeout, daemon=True)
    listener.start()
    timer.start()
    cleared.wait()

    if timed_out.is_set():
        log.warning(
            f"[TIMEOUT]       No confirmation received in {AMBULANCE_TIMEOUT_SEC}s — auto-resuming."
        )
        return False
    else:
        log.info("[CONFIRMED]     Ambulance cleared by operator.")
        return True


# ─────────────────────────────────────────────
#  MAIN ITMS WORKFLOW
# ─────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  🚦  ITMS — Intelligent Traffic Management System  🚑")
    print("=" * 60)
    log.info("=" * 55)
    log.info("  ITMS System Starting Up")
    log.info("=" * 55)

    # ── Initialise components ─────────────────────────────────
    intersection = TrafficIntersection(intersection_id="INT-001")
    controller   = TrafficController(intersection)
    rf_handler   = AmbulanceRFHandler()

    # ── Step 1: Start normal traffic cycle ───────────────────
    controller.start()

    try:
        while True:
            print("\n" + "─" * 60)
            print("  SYSTEM MENU")
            print("  1.  Simulate ambulance RF event")
            print("  2.  Quit ITMS")
            print("─" * 60)

            choice = input("  Enter choice: ").strip()

            if choice == "1":

                # ── Step 2: Ambulance presses broadcast button ───────────
                tx_ok = rf_handler.simulate_button_press()
                if not tx_ok:
                    log.error("[ERROR]         RF transmission failed. Aborting this event.")
                    continue

                # ── Step 3: Receiver checks for 434 MHz signal ───────────
                signal_detected = rf_handler.detect_signal()
                if not signal_detected:
                    log.info("[SYSTEM]        No ambulance signal confirmed. Normal cycle continues.")
                    continue

                log.warning("[SYSTEM]        ⚠  AMBULANCE CONFIRMED — initiating emergency preemption.")

                # ── Step 4: Get approach direction ───────────────────────
                direction = prompt_direction()

                # ── Step 5: Activate emergency preemption ────────────────
                controller.activate_preemption(direction)

                # ── Step 6: Wait for ambulance to clear ──────────────────
                wait_for_ambulance_to_clear()

                # ── Step 7: Deactivate and resume normal cycle ───────────
                controller.deactivate_preemption()

                log.info("[SYSTEM]        Emergency event complete. Normal operation resumed.")

            elif choice == "2":
                log.info("[SYSTEM]        User requested shutdown.")
                break

            else:
                print("  ⚠  Invalid option. Please enter 1 or 2.")

    except KeyboardInterrupt:
        print()
        log.warning("[SYSTEM]        KeyboardInterrupt — initiating safe shutdown ...")

    finally:
        # ── Step 8: Safe shutdown ─────────────────────────────────────
        controller.stop()
        log.info("[SYSTEM]        ✅  ITMS safely shut down. All signals RED.")
        print("\n  ✅  ITMS system shut down safely.\n")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
