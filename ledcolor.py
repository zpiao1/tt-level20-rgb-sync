"""Adapt a screen colour for display on the keyboard's LEDs.

Screen colours and LED colours are not the same thing: LEDs render dark and
muted colours as a dim, muddy glow, and a colour that is already near full
brightness leaves the reactive pulse no room to brighten. So every colour
source passes through normalize_for_leds() before reaching the keyboard.

Hue is never changed - only saturation and brightness are clamped into a
range that reads well on the LEDs.

Note: this means the keyboard deliberately does NOT match the source colour
exactly (e.g. #69250C is shown as #8C3110). If exact numeric fidelity
is ever wanted, skip normalize_for_leds() in sync.py; the pulse still works,
but dark colours will look dim and very bright ones will pulse weakly.
"""
import colorsys

MIN_SATURATION = 0.45   # below this LEDs look washed out / whitish
MIN_VALUE = 0.55        # below this LEDs look dim and muddy
MAX_VALUE = 0.80        # headroom so the keypress pulse can visibly brighten


def to_hsv(rgb):
    """(r, g, b) in 0-255 -> (h, s, v) in 0-1."""
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))


def normalize_for_leds(rgb):
    h, s, v = to_hsv(rgb)
    if s >= MIN_SATURATION and MIN_VALUE <= v <= MAX_VALUE:
        # Already fine; return as-is rather than let an HSV round trip
        # nudge a channel by one step.
        return tuple(rgb)
    s = max(s, MIN_SATURATION)
    v = min(max(v, MIN_VALUE), MAX_VALUE)
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))


def hexcolor(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)
