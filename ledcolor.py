"""Adapt a screen colour for display on the keyboard's LEDs.

Screen colours and LED colours are not the same thing: LEDs render dark and
muted colours as a dim, muddy glow, so every colour source passes through
normalize_for_leds() before reaching the keyboard. Hue is never changed -
only saturation and brightness are raised to a floor that reads well.

Per-zone brightness (keys vs. logo/light strips) is a separate step, in
render.py.

Note: this means the keyboard deliberately does NOT match the source colour
exactly (e.g. #69250C is normalized to #8C3110, then render.py applies
per-zone gains). If exact numeric fidelity is ever wanted, skip
normalize_for_leds() in sync.py; the pulse still works, but dark colours
will look dim and muted ones washed out.
"""
import colorsys
import math

MIN_SATURATION = 0.45   # below this LEDs look washed out / whitish
MIN_VALUE = 0.55        # below this LEDs look dim and muddy


def to_hsv(rgb):
    """(r, g, b) in 0-255 -> (h, s, v) in 0-1."""
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))


def normalize_for_leds(rgb):
    h, s, v = to_hsv(rgb)
    if s >= MIN_SATURATION and v >= MIN_VALUE:
        # Already fine; return as-is rather than let an HSV round trip
        # nudge a channel by one step.
        return tuple(rgb)
    s = max(s, MIN_SATURATION)
    v = max(v, MIN_VALUE)
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))


def scale(rgb, factor):
    """Scale brightness by `factor` without changing hue.

    Clamping each channel to 255 independently would let the dimmer channels
    keep rising after the brightest one saturates, shifting the hue. Capping
    the factor at 255/max(channel) scales all channels together and stops
    them together.
    """
    peak = max(rgb)
    if peak == 0:
        return tuple(rgb)
    factor = min(factor, 255 / peak)
    return tuple(min(255, round(c * factor)) for c in rgb)


def boost(rgb, level, amount):
    """Keypress pulse: brighten by up to (1 + level*amount), hue unchanged."""
    return scale(rgb, 1.0 + level * amount)


def hexcolor(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


# -- transitions ---------------------------------------------------------------
#
# Colour changes fade rather than snap. The path matters: consecutive accents
# are often near-opposite hues (rust -> teal), and a straight crossfade in RGB
# - or even in perceptual OKLab - passes through a dull grey in the middle
# (saturation ~0.2, well under what reads well on LEDs). Blending in OKLCh
# instead interpolates lightness and chroma but *rotates* hue along the short
# arc, so the colour stays vivid and passes briefly through an in-between hue.

def _srgb_to_linear(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c):
    c = min(max(c, 0.0), 1.0)
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return round(c * 255)


def _to_oklch(rgb):
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.atan2(bb, a)


def _from_oklch(L, C, h):
    a, b = C * math.cos(h), C * math.sin(h)
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (_linear_to_srgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
            _linear_to_srgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            _linear_to_srgb(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s))


_ACHROMATIC = 0.02   # below this chroma, hue is meaningless noise


def blend(a, b, t):
    """Colour a fraction t (0-1) of the way from a to b, hue on the short arc."""
    if t <= 0:
        return tuple(a)
    if t >= 1:
        return tuple(b)
    L1, C1, h1 = _to_oklch(a)
    L2, C2, h2 = _to_oklch(b)
    # A grey has no real hue; borrow the other end's so it doesn't swing.
    if C1 < _ACHROMATIC:
        h1 = h2
    if C2 < _ACHROMATIC:
        h2 = h1
    dh = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi      # shortest arc
    return _from_oklch(L1 + (L2 - L1) * t, C1 + (C2 - C1) * t, h1 + dh * t)


def ease(t):
    """Smoothstep: starts and ends gently instead of moving at constant speed."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


class Fade:
    """A timed transition between two colours."""

    def __init__(self, start_color, end_color, start, duration):
        self.start_color, self.end_color = start_color, end_color
        self.start, self.duration = start, duration

    def done(self, now):
        return now >= self.start + self.duration

    def color_at(self, now):
        if self.done(now):
            return tuple(self.end_color)
        return blend(self.start_color, self.end_color,
                     ease((now - self.start) / self.duration))
