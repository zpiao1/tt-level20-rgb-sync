"""Tests for the pure colour logic: registry decode, LED normalization, pulse boost.

    python -m unittest test_color -v
"""
import unittest

from accent import decode_palette
from ledcolor import MIN_SATURATION, MIN_VALUE, boost, normalize_for_leds, scale
from ledcolor import Fade, blend, ease
from ledcolor import to_hsv as hsv
from leds import CENTER_STRIP, KEYS, LOGOS, OUTER_FRAME
from render import DECOR_GAIN, KEY_GAIN, PULSE_BOOST, frame_for


class DecodeAccent(unittest.TestCase):
    # AccentPalette captured from this machine, alongside the value Windows'
    # own API reported at the same moment:
    #   UISettings.GetColorValue(UIColorType.Accent) == #3D806F
    # (DWM\AccentColor read #69250C at that time - stale, not the accent.)
    PALETTE = bytes.fromhex(
        "AEE8DF00" "8DCABE00" "4B9C8A00" "3D806F00"
        "30685700" "1F493800" "0B261400" "88179800")

    def test_accent_is_palette_entry_3_matching_the_official_api(self):
        self.assertEqual(decode_palette(self.PALETTE), (0x3D, 0x80, 0x6F))

    def test_palette_bytes_are_rgb_order(self):
        # Unlike DWM\AccentColor (ABGR), each palette entry is R, G, B, A.
        self.assertEqual(decode_palette(self.PALETTE, index=0), (0xAE, 0xE8, 0xDF))


class NormalizeForLeds(unittest.TestCase):
    def assertSameHue(self, a, b, tol=0.01):
        self.assertAlmostEqual(hsv(a)[0], hsv(b)[0], delta=tol)

    def test_dark_colour_is_lifted_to_floor_keeping_hue(self):
        raw = (105, 37, 12)                          # current accent, V = 0.41
        out = normalize_for_leds(raw)
        self.assertAlmostEqual(hsv(out)[2], MIN_VALUE, delta=0.01)
        self.assertSameHue(raw, out)

    def test_bright_colour_keeps_its_brightness(self):
        # No ceiling any more - headroom for the pulse comes from the dimmer
        # decorative zone (render.DECOR_GAIN), not from dimming every LED.
        raw = (255, 120, 40)
        self.assertEqual(normalize_for_leds(raw), raw)

    def test_muted_colour_gets_saturation_floor(self):
        out = normalize_for_leds((150, 140, 130))     # nearly grey
        self.assertGreaterEqual(hsv(out)[1], MIN_SATURATION - 0.01)

    def test_colour_already_in_range_is_unchanged(self):
        raw = (180, 60, 30)                           # S 0.83, V 0.71
        self.assertEqual(normalize_for_leds(raw), raw)


class HuePreservingScale(unittest.TestCase):
    def test_scales_all_channels_together(self):
        self.assertEqual(scale((100, 50, 20), 0.5), (50, 25, 10))

    def test_stops_at_255_without_shifting_hue(self):
        base = (174, 95, 66)
        out = scale(base, 1.5)                        # red would clip at 261
        self.assertEqual(max(out), 255)
        self.assertAlmostEqual(hsv(out)[0], hsv(base)[0], delta=0.01)

    def test_black_does_not_divide_by_zero(self):
        self.assertEqual(scale((0, 0, 0), 1.5), (0, 0, 0))


class HuePreservingBoost(unittest.TestCase):
    def test_no_pulse_returns_base(self):
        self.assertEqual(boost((140, 49, 16), 0.0, 0.6), (140, 49, 16))

    def test_boost_scales_all_channels_when_there_is_headroom(self):
        self.assertEqual(boost((100, 50, 20), 1.0, 0.5), (150, 75, 30))


class Blend(unittest.TestCase):
    RUST, TEAL = (0xAE, 0x5F, 0x42), (0x43, 0x8C, 0x7A)   # real consecutive accents

    def test_endpoints_are_exact(self):
        self.assertEqual(blend(self.RUST, self.TEAL, 0.0), self.RUST)
        self.assertEqual(blend(self.RUST, self.TEAL, 1.0), self.TEAL)

    def test_opposite_hues_stay_vivid_instead_of_passing_through_grey(self):
        # A straight RGB crossfade gives #78765E here (saturation 0.22) -
        # muddy on LEDs. Rotating hue keeps it near the endpoints' saturation.
        self.assertGreaterEqual(hsv(blend(self.RUST, self.TEAL, 0.5))[1], 0.45)

    def test_hue_takes_the_short_way_round(self):
        # Red -> magenta is a short step; the long way would pass through green.
        h = hsv(blend((255, 0, 0), (255, 0, 255), 0.5))[0]
        self.assertTrue(h > 0.8 or h < 0.05, f"hue {h:.2f} went the long way")

    def test_grey_endpoint_does_not_break(self):
        out = blend((128, 128, 128), (200, 50, 50), 0.5)
        self.assertEqual(len(out), 3)
        self.assertTrue(all(0 <= c <= 255 for c in out))


class Easing(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(ease(0.0), 0.0)
        self.assertEqual(ease(1.0), 1.0)
        self.assertAlmostEqual(ease(0.5), 0.5)
        samples = [ease(i / 20) for i in range(21)]
        self.assertEqual(samples, sorted(samples))          # monotonic

    def test_clamps_outside_the_range(self):
        self.assertEqual(ease(-1.0), 0.0)
        self.assertEqual(ease(2.0), 1.0)


class FadeTest(unittest.TestCase):
    def test_runs_from_start_colour_to_target_over_its_duration(self):
        fade = Fade((10, 20, 30), (200, 100, 50), start=100.0, duration=1.0)
        self.assertEqual(fade.color_at(100.0), (10, 20, 30))
        self.assertFalse(fade.done(100.5))
        self.assertEqual(fade.color_at(101.0), (200, 100, 50))
        self.assertTrue(fade.done(101.0))

    def test_zero_duration_is_an_instant_snap(self):
        fade = Fade((10, 20, 30), (200, 100, 50), start=5.0, duration=0.0)
        self.assertEqual(fade.color_at(5.0), (200, 100, 50))
        self.assertTrue(fade.done(5.0))



class ZoneFrame(unittest.TestCase):
    """Per-zone gains - rationale in render.py."""
    BASE = (0xAE, 0x5F, 0x42)

    def test_keys_brighter_and_decorative_dimmer(self):
        frame = frame_for(self.BASE)
        self.assertEqual(frame[KEYS[0]], scale(self.BASE, KEY_GAIN))
        for group in (LOGOS, CENTER_STRIP, OUTER_FRAME):
            self.assertEqual(frame[group[0]], scale(self.BASE, DECOR_GAIN))

    def test_covers_every_led(self):
        from leds import ALL_INDEXES
        self.assertEqual(set(frame_for(self.BASE)), set(ALL_INDEXES))

    def test_pulse_brightens_only_the_outer_frame(self):
        rest = frame_for(self.BASE)
        lit = frame_for(self.BASE, level=1.0, boost_amount=PULSE_BOOST)
        self.assertGreater(max(lit[OUTER_FRAME[0]]), max(rest[OUTER_FRAME[0]]))
        self.assertEqual(lit[KEYS[0]], rest[KEYS[0]])
        self.assertEqual(lit[LOGOS[0]], rest[LOGOS[0]])

    def test_dim_zone_leaves_the_pulse_room_to_show(self):
        # Even a full-brightness base colour gets a visible pulse, because
        # the frame starts from DECOR_GAIN brightness, not from the top.
        lit = frame_for((255, 120, 40), level=1.0, boost_amount=PULSE_BOOST)
        rest = frame_for((255, 120, 40))
        self.assertGreaterEqual(max(lit[OUTER_FRAME[0]]) / max(rest[OUTER_FRAME[0]]), 1.5)

    def test_default_pulse_peaks_above_the_base_colour(self):
        # Regression: with the strips dimmed to DECOR_GAIN, a weak boost left
        # the pulse peak (0.8x base at boost 0.6) too dim to notice.
        peak = frame_for(self.BASE, level=1.0, boost_amount=PULSE_BOOST)[OUTER_FRAME[0]]
        self.assertGreater(max(peak), max(self.BASE))

if __name__ == "__main__":
    unittest.main()
