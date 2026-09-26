"""
Keypress-reactive brightness pulse.

Listens for key events purely to know that *a* key was pressed. The identity of
the key is never inspected, recorded, or stored - the effect does not need it,
and not collecting it is the right default for something watching a keyboard.
"""
import math
import threading
import time

from pynput import keyboard


class PulseEnvelope:
    """Brightness multiplier that jumps on a keypress and decays back to rest.

    Repeated presses re-trigger toward the ceiling rather than summing, so
    fast typing produces a steady shimmer instead of runaway glare.
    """

    def __init__(self, decay_tau=0.12, impulse=1.0, ceiling=1.0):
        self.decay_tau = decay_tau
        self.impulse = impulse
        self.ceiling = ceiling
        self._level_at_mark = 0.0
        self._marked_at = time.monotonic()
        self._lock = threading.Lock()

    def _decayed(self, now):
        dt = now - self._marked_at
        if dt <= 0:
            return self._level_at_mark
        return self._level_at_mark * math.exp(-dt / self.decay_tau)

    def trigger(self):
        now = time.monotonic()
        with self._lock:
            self._level_at_mark = min(self.ceiling, self._decayed(now) + self.impulse)
            self._marked_at = now

    def level(self):
        with self._lock:
            return self._decayed(time.monotonic())

    def is_at_rest(self, epsilon=0.01):
        return self.level() < epsilon


class KeypressWatcher:
    """Fires envelope.trigger() once per physical key press.

    Windows auto-repeat emits a continuous stream of key-down events while a key
    is held, which would pulse forever. To fire only on the up->down transition
    we must tell keys apart, so held keys are kept in a set as opaque dedupe
    tokens. That set is in-memory only, never logged or persisted, and entries
    are dropped on release - key identity is not used for anything else.
    """

    def __init__(self, envelope, on_press=None):
        self.envelope = envelope
        self.on_press = on_press        # e.g. wakes the idle render loop
        self._listener = None
        self._held = set()
        self._lock = threading.Lock()

    def _on_press(self, key):
        with self._lock:
            if key in self._held:       # auto-repeat, not a new press
                return
            self._held.add(key)
        self.envelope.trigger()
        if self.on_press is not None:
            self.on_press()

    def _on_release(self, key):
        with self._lock:
            self._held.discard(key)

    def start(self):
        self._listener = keyboard.Listener(on_press=self._on_press,
                                           on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()


def boost(rgb, level, amount):
    """Brighten a colour by up to (1 + level*amount) without changing its hue.

    Clamping each channel to 255 independently would let the dimmer channels
    keep rising after the brightest one saturates, shifting the hue on every
    keystroke. Capping the factor at 255/max(channel) scales all channels
    together and stops them together.
    """
    peak = max(rgb)
    if peak == 0:
        return tuple(rgb)
    factor = min(1.0 + level * amount, 255 / peak)
    return tuple(min(255, round(c * factor)) for c in rgb)


if __name__ == "__main__":
    env = PulseEnvelope()
    watcher = KeypressWatcher(env)
    watcher.start()
    print("Type anywhere; showing envelope level. Ctrl+C to stop.")
    try:
        while True:
            lvl = env.level()
            bar = "#" * int(lvl * 50)
            print(f"\r  {lvl:5.3f} |{bar:<50}|", end="", flush=True)
            time.sleep(1 / 30)
    except KeyboardInterrupt:
        watcher.stop()
        print("\nstopped")
