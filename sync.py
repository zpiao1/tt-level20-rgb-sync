"""
Keep the Thermaltake Level 20 RGB backlight matching the Windows accent colour
(or the desktop wallpaper), optionally pulsing the outer light frame on every
keypress.

    python sync.py                        # follow the Windows accent colour
    python sync.py --source wallpaper     # follow the wallpaper instead
    python sync.py --reactive             # + brightness pulse on keypress
    python sync.py --once                 # apply current colour and exit
    python sync.py --reactive --boost 0.9 --decay 0.18
"""
import argparse
import socket
import sys
import threading
import time
from datetime import datetime

import accent
import wallpaper
from ledcolor import hexcolor, normalize_for_leds
from leds import OUTER_FRAME
from reactive import KeypressWatcher, PulseEnvelope, boost
from tt_level20 import Level20

# Binding a fixed loopback port is a cheap cross-process lock: only one process
# can hold it, so a manual run and the autostart entry cannot fight over the
# keyboard. The socket is never read from or written to.
SINGLE_INSTANCE_PORT = 49731

FRAME_TICK = 1 / 60          # target cadence while a pulse is decaying
RECHECK_WITH_WATCHER = 60.0  # safety re-check when change notifications work
RECHECK_WITHOUT = 2.0        # poll interval if notifications are unavailable
LEVEL_EPSILON = 0.02  # smallest brightness change worth a USB write

# Each source offers token() - a cheap value that changes when the colour
# does (registry DWORD / file mtime) - color(), the possibly-expensive read of
# the actual colour, and watcher(), a Win32 change notification. The watcher
# wakes the loop instantly; the token comparison then decides whether the
# colour really changed (the watched key/folder holds other things too).
SOURCES = {"accent": accent, "wallpaper": wallpaper}


_log_file = None


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3] + f"] {msg}"
    print(line, flush=True)
    if _log_file is not None:
        try:
            with open(_log_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def acquire_single_instance():
    """Return the lock socket, or None if another instance already holds it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        sock.listen(1)
        return sock
    except OSError:
        sock.close()
        return None


def read_base(source):
    """Return (raw, led) - the source colour and its LED-adapted version."""
    raw = source.color()
    return raw, normalize_for_leds(raw)


def connect():
    kb = Level20()
    kb.enter_software_mode()
    return kb


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=sorted(SOURCES), default="accent",
                    help="colour source (default: accent)")
    ap.add_argument("--interval", type=float, default=None,
                    help="seconds between safety re-checks of the colour "
                         "(default 60, or 2 if change notifications are "
                         "unavailable)")
    ap.add_argument("--once", action="store_true", help="apply once and exit")
    ap.add_argument("--reactive", action="store_true",
                    help="pulse the outer frame on keypress")
    ap.add_argument("--boost", type=float, default=0.6,
                    help="pulse strength, 0-2 (default 0.6)")
    ap.add_argument("--decay", type=float, default=0.12,
                    help="pulse decay time constant in seconds (default 0.12)")
    ap.add_argument("--log", metavar="FILE",
                    help="also append output to FILE (used by the autostart entry, "
                         "which runs without a console)")
    args = ap.parse_args()

    global _log_file
    _log_file = args.log

    lock = acquire_single_instance()
    if lock is None:
        log("another instance is already running; exiting")
        return 0

    try:
        kb = connect()
    except Exception as exc:
        log(f"ERROR: cannot open keyboard: {exc}")
        return 1
    log("keyboard opened, software mode active")

    source = SOURCES[args.source]
    raw, base = read_base(source)
    kb.set_solid(*base)
    log(f"{args.source} {hexcolor(raw)} -> led {hexcolor(base)}")
    if args.once:
        kb.close()
        return 0

    # Everything that should make the loop act - a colour-change notification
    # or a keypress - sets this one event. At rest the loop blocks on it, so
    # there are no idle wakeups and reactions start immediately.
    wake = threading.Event()
    # Set only by the colour watcher, so keypresses and pulse frames don't
    # re-read the colour source - only a notification or a re-check does.
    colour_dirty = threading.Event()

    def on_colour_change():
        colour_dirty.set()
        wake.set()

    colour_watcher = source.watcher(on_colour_change)
    try:
        colour_watcher.start()
        interval = args.interval or RECHECK_WITH_WATCHER
        mode = f"event-driven, safety re-check every {interval:g}s"
    except OSError as exc:
        colour_watcher = None
        interval = args.interval or RECHECK_WITHOUT
        mode = f"notifications unavailable ({exc}); polling every {interval:g}s"

    envelope = watcher = None
    if args.reactive:
        envelope = PulseEnvelope(decay_tau=args.decay)
        watcher = KeypressWatcher(envelope, on_press=wake.set)
        watcher.start()
        log(f"reactive pulse on ({len(OUTER_FRAME)} outer LEDs, "
            f"boost {args.boost:g}, decay {args.decay:g}s)")

    last_token = source.token()
    last_level = 0.0
    recheck = False
    log(f"watching {args.source} ({mode})")

    try:
        while True:
            # Clear before reading state: anything that fires from here on
            # leaves the event set, so the wait below returns at once.
            wake.clear()

            if recheck or colour_dirty.is_set():
                colour_dirty.clear()
                recheck = False
                current = source.token()
            else:
                current = last_token
            if current is not None and current != last_token:
                last_token = current
                try:
                    raw, base = read_base(source)
                    kb.set_solid(*base)
                    last_level = 0.0
                    log(f"{args.source} changed -> {hexcolor(raw)} "
                        f"-> led {hexcolor(base)}")
                except Exception as exc:
                    log(f"  {args.source} update failed: {exc}")

            level = envelope.level() if envelope is not None else 0.0
            pulse_moved = (abs(level - last_level) >= LEVEL_EPSILON
                           or level < LEVEL_EPSILON < last_level)
            if pulse_moved:
                lit = boost(base, level, args.boost)
                try:
                    kb.set_leds({i: lit for i in OUTER_FRAME})
                    last_level = level
                except Exception as exc:
                    log(f"  write failed ({exc}); reconnecting")
                    try:
                        kb.close()
                    except Exception:
                        pass
                    kb = connect()
                    kb.set_solid(*base)
                    last_level = 0.0

            if level >= LEVEL_EPSILON:
                time.sleep(FRAME_TICK)          # pulse decaying: keep animating
            else:
                # At rest: block until woken. A timeout means nothing fired
                # for a whole interval, so re-check the colour just in case.
                recheck = not wake.wait(interval)

    except KeyboardInterrupt:
        log("stopped")
    finally:
        if watcher is not None:
            watcher.stop()
        if colour_watcher is not None:
            colour_watcher.stop()
        try:
            kb.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
