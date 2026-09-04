"""Locate the current desktop wallpaper and pull a usable accent colour from it."""
import colorsys
import os

from PIL import Image

# Windows re-transcodes whatever the current wallpaper is (slideshow included)
# into this single file, so its mtime is a reliable change signal.
WALLPAPER_PATH = os.path.join(
    os.environ["APPDATA"], "Microsoft", "Windows", "Themes", "TranscodedWallpaper"
)

SAMPLE_SIZE = (200, 125)   # plenty for colour statistics, cheap to process
PALETTE_SIZE = 16          # median-cut buckets to consider

# Keyboard LEDs wash out muted colours, so refuse to emit anything too grey/dark.
MIN_SATURATION = 0.45
MIN_VALUE = 0.55


def mtime():
    try:
        return os.path.getmtime(WALLPAPER_PATH)
    except OSError:
        return None


def _score(fraction, saturation, value):
    """Favour colours that are common AND vivid.

    Frequency alone picks the muddy background that dominates most photos;
    saturation alone picks a stray highlight. The product is what makes the
    result look deliberate rather than accidental.
    """
    if value < 0.15 or value > 0.97:      # near-black / blown-out white
        return 0.0
    return fraction * (0.20 + saturation) * (0.40 + value)


def dominant_color(path=WALLPAPER_PATH):
    """Return (r, g, b) - the most characteristic vivid colour in the wallpaper."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail(SAMPLE_SIZE, Image.Resampling.BILINEAR)
        quantized = im.quantize(colors=PALETTE_SIZE, method=Image.Quantize.MEDIANCUT)

        palette = quantized.getpalette()
        counts = quantized.getcolors()          # [(count, palette_index), ...]

    total = sum(c for c, _ in counts) or 1

    best, best_score = (128, 128, 128), -1.0
    for count, idx in counts:
        r, g, b = palette[idx * 3: idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        sc = _score(count / total, s, v)
        if sc > best_score:
            best, best_score = (r, g, b), sc

    return _make_vivid(best)


def _make_vivid(rgb):
    """Nudge the colour up to a floor of saturation/brightness for LED display."""
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    s = max(s, MIN_SATURATION)
    v = max(v, MIN_VALUE)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


if __name__ == "__main__":
    print(f"wallpaper: {WALLPAPER_PATH}")
    rgb = dominant_color()
    print(f"dominant : rgb{rgb}  #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
