"""Turn one base colour into a full per-LED frame for the keyboard.

The same drive level looks very different across the board: key LEDs sit under
opaque keycaps, so only light escaping through the legends and gaps reaches
the eye and they look dim; the logo and light strips are bare diffusers, so
they look bright and washed out. Each zone therefore gets its own gain. The
values were chosen by eye on the real keyboard (calibration option #3).

Keeping the decorative zone dim also gives the keypress pulse - which only
runs on the outer frame - room to brighten visibly, whatever the base colour.
"""
from ledcolor import boost, hexcolor, scale
from leds import DECORATIVE, KEYS, OUTER_FRAME

KEY_GAIN = 1.5      # keys: compensate for opaque keycaps (capped at 255)
DECOR_GAIN = 0.5    # logo + light strips: bare LEDs, tone them down

# Pulse peak = DECOR_GAIN x (1 + PULSE_BOOST) = 1.25x the base colour. Tuned
# together with DECOR_GAIN: at the old 0.6 the dimmed strips peaked at only
# 0.8x base, dimmer than they used to rest before per-zone gains.
PULSE_BOOST = 1.5


def zone_colors(base):
    """(keys, decorative) colours actually displayed for a base colour."""
    return scale(base, KEY_GAIN), scale(base, DECOR_GAIN)


def describe(base):
    keys, decor = zone_colors(base)
    return f"keys {hexcolor(keys)} / strips {hexcolor(decor)}"


def frame_for(base, level=0.0, boost_amount=0.0):
    """Return {led_index: rgb} for every LED, pulse layered on the outer frame."""
    keys, decor = zone_colors(base)
    frame = dict.fromkeys(KEYS, keys)
    frame.update(dict.fromkeys(DECORATIVE, decor))
    if level > 0:
        frame.update(dict.fromkeys(OUTER_FRAME, boost(decor, level, boost_amount)))
    return frame
