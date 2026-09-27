"""Locate the current desktop wallpaper and pull a usable colour from it."""
import os
import time

from ledcolor import to_hsv
from watchers import DirectoryWatcher

# Windows re-transcodes whatever the current wallpaper is (slideshow included)
# into this single file, so its mtime is a reliable change signal.
WALLPAPER_PATH = os.path.join(
    os.environ["APPDATA"], "Microsoft", "Windows", "Themes", "TranscodedWallpaper"
)

SAMPLE_SIZE = (200, 125)   # plenty for colour statistics, cheap to process
PALETTE_SIZE = 16          # median-cut buckets to consider

# A folder notification can fire several times while Windows is still writing
# the file; decoding each time wastes work and may read a half-written image.
SETTLE_SECONDS = 0.3
SETTLE_TIMEOUT = 3.0


def token():
    """File mtime - changes whenever Windows re-transcodes a new wallpaper."""
    try:
        return os.path.getmtime(WALLPAPER_PATH)
    except OSError:
        return None


def watcher(on_change):
    """Fires on_change when anything in the Themes folder is written."""
    return DirectoryWatcher(os.path.dirname(WALLPAPER_PATH), on_change)


def color():
    """Wait for the file to stop changing, then pick its dominant colour."""
    deadline = time.monotonic() + SETTLE_TIMEOUT
    last = token()
    while time.monotonic() < deadline:
        time.sleep(SETTLE_SECONDS)
        current = token()
        if current == last:
            break
        last = current
    return dominant_color()


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
    from PIL import Image      # lazy: only the wallpaper source needs PIL

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
        _, s, v = to_hsv((r, g, b))
        sc = _score(count / total, s, v)
        if sc > best_score:
            best, best_score = (r, g, b), sc

    return best


if __name__ == "__main__":
    from ledcolor import hexcolor, normalize_for_leds
    from render import describe
    print(f"wallpaper: {WALLPAPER_PATH}")
    raw = dominant_color()
    print(f"dominant : {hexcolor(raw)}  ->  {describe(normalize_for_leds(raw))}")
