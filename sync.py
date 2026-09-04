"""
Keep the Thermaltake Level 20 RGB backlight matching the desktop wallpaper,
optionally pulsing the outer light frame on every keypress.

    python sync.py                  # wallpaper sync only
    python sync.py --reactive       # + brightness pulse on keypress
    python sync.py --once           # apply current colour and exit
    python sync.py --reactive --boost 0.9 --decay 0.18
"""
import argparse
import socket
import sys
import time
from datetime import datetime

import wallpaper
from leds import OUTER_FRAME
from reactive import KeypressWatcher, PulseEnvelope, boost
from tt_level20 import Level20

# Binding a fixed loopback port is a cheap cross-process lock: only one process
# can hold it, so a manual run and the autostart entry cannot fight over the
# keyboard. The socket is never read from or written to.
SINGLE_INSTANCE_PORT = 49731

IDLE_TICK = 0.05      # seconds between polls when nothing is animating
FRAME_TICK = 1 / 60   # target cadence while a pulse is decaying
LEVEL_EPSILON = 0.02  # smallest brightness change worth a USB write


_log_file = None


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
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


def connect():
    kb = Level20()
    kb.enter_software_mode()
    return kb


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=10.0,
                    help="seconds between wallpaper checks (default 10)")
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

    base = wallpaper.dominant_color()
    kb.set_solid(*base)
    log(f"base rgb{base}  #{base[0]:02X}{base[1]:02X}{base[2]:02X}")
    if args.once:
        kb.close()
        return 0

    envelope = watcher = None
    if args.reactive:
        envelope = PulseEnvelope(decay_tau=args.decay)
        watcher = KeypressWatcher(envelope)
        watcher.start()
        log(f"reactive pulse on ({len(OUTER_FRAME)} outer LEDs, "
            f"boost {args.boost:g}, decay {args.decay:g}s)")

    last_mtime = wallpaper.mtime()
    last_check = time.monotonic()
    last_level = 0.0
    log(f"watching wallpaper every {args.interval:g}s (Ctrl+C to stop)")

    try:
        while True:
            now = time.monotonic()

            if now - last_check >= args.interval:
                last_check = now
                current = wallpaper.mtime()
                if current is not None and current != last_mtime:
                    last_mtime = current
                    try:
                        base = wallpaper.dominant_color()
                        kb.set_solid(*base)
                        last_level = 0.0
                        log(f"wallpaper changed -> rgb{base}  "
                            f"#{base[0]:02X}{base[1]:02X}{base[2]:02X}")
                    except Exception as exc:
                        log(f"  wallpaper update failed: {exc}")

            if envelope is None:
                time.sleep(IDLE_TICK)
                continue

            level = envelope.level()
            if abs(level - last_level) >= LEVEL_EPSILON or (
                level < LEVEL_EPSILON < last_level
            ):
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

            time.sleep(FRAME_TICK if level >= LEVEL_EPSILON else IDLE_TICK)

    except KeyboardInterrupt:
        log("stopped")
    finally:
        if watcher is not None:
            watcher.stop()
        try:
            kb.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
