"""Read the Windows accent colour.

With Settings > Personalization > Colors > "Automatically pick an accent
color from my background" enabled, Windows recomputes this from the
wallpaper, so it follows the slideshow on its own.

The accent lives in Explorer\\Accent\\AccentPalette: eight RGBA entries, light
to dark, where entry 3 is the accent itself - byte-for-byte what the official
WinRT API UISettings.GetColorValue(UIColorType.Accent) returns.

Do NOT use DWM\\AccentColor. It looks like the accent and often matches it,
but it is the title-bar colourization value: on this machine it stayed on a
stale #69250C, and Windows snapped it back there ~50ms after briefly writing
each new accent - so following it made the keyboard flip to the new colour
and straight back.
"""
import winreg

from watchers import RegistryWatcher

_ACCENT_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent"
_VALUE = "AccentPalette"
ACCENT_INDEX = 3


def decode_palette(palette, index=ACCENT_INDEX):
    """Return (r, g, b) for one entry of the 32-byte AccentPalette blob."""
    r, g, b = palette[index * 4: index * 4 + 3]
    return (r, g, b)


def token():
    """Raw palette bytes - cheap to read and change whenever the accent does."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ACCENT_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE)
            return bytes(value)
    except OSError:
        return None


def watcher(on_change):
    """Fires on_change the moment Windows writes a new accent palette."""
    return RegistryWatcher(winreg.HKEY_CURRENT_USER, _ACCENT_KEY, on_change)


def color():
    palette = token()
    if not palette or len(palette) < (ACCENT_INDEX + 1) * 4:
        raise RuntimeError("HKCU/" + _ACCENT_KEY + "/" + _VALUE + " not readable")
    return decode_palette(palette)


if __name__ == "__main__":
    from ledcolor import hexcolor, normalize_for_leds
    raw = color()
    print(f"accent: {hexcolor(raw)}  ->  led: {hexcolor(normalize_for_leds(raw))}")
