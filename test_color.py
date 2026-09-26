"""Tests for the pure colour logic: registry decode, LED normalization, pulse boost.

    python -m unittest test_color -v
"""
import unittest

from accent import decode_palette
from ledcolor import MAX_VALUE, MIN_SATURATION, MIN_VALUE, normalize_for_leds
from ledcolor import to_hsv as hsv
from reactive import boost


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

    def test_bright_colour_is_capped_for_pulse_headroom(self):
        raw = (255, 120, 40)                          # V = 1.0
        out = normalize_for_leds(raw)
        self.assertAlmostEqual(hsv(out)[2], MAX_VALUE, delta=0.01)
        self.assertSameHue(raw, out)

    def test_muted_colour_gets_saturation_floor(self):
        out = normalize_for_leds((150, 140, 130))     # nearly grey
        self.assertGreaterEqual(hsv(out)[1], MIN_SATURATION - 0.01)

    def test_colour_already_in_range_is_unchanged(self):
        raw = (180, 60, 30)                           # S 0.83, V 0.71
        self.assertEqual(normalize_for_leds(raw), raw)


class HuePreservingBoost(unittest.TestCase):
    def test_no_pulse_returns_base(self):
        self.assertEqual(boost((140, 49, 16), 0.0, 0.6), (140, 49, 16))

    def test_boost_scales_all_channels_when_there_is_headroom(self):
        self.assertEqual(boost((100, 50, 20), 1.0, 0.5), (150, 75, 30))

    def test_boost_stops_at_255_without_shifting_hue(self):
        base = (200, 100, 50)
        out = boost(base, 1.0, 0.6)                   # 1.6x would clip red
        self.assertEqual(max(out), 255)
        self.assertAlmostEqual(hsv(out)[0], hsv(base)[0], delta=0.01)

    def test_black_does_not_divide_by_zero(self):
        self.assertEqual(boost((0, 0, 0), 1.0, 0.6), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
