# tt-keyboard-sync

Drives the **Thermaltake Level 20 RGB** (`KB-LVT-SSBRUS-01`) backlight from the
Windows accent colour (or the desktop wallpaper). Talks to the keyboard directly over USB HID — no
Thermaltake, Razer, or SignalRGB software involved at runtime.

## Usage

```
python sync.py --reactive          # accent sync + keypress pulse
python sync.py                     # accent sync only
python sync.py --source wallpaper  # follow the wallpaper instead
python sync.py --once              # apply current colour and exit
python sync.py --reactive --boost 0.9 --decay 0.20
python sync.py --fade 2.5          # slower colour transitions (0 = snap)
python accent.py                   # print accent colour and its LED version
python wallpaper.py                # same, for the wallpaper pick
python -m unittest test_color -v   # colour-logic tests
python tt_level20.py               # hardware self-test: red/green/blue/amber
python reactive.py                 # visualise the pulse envelope in the terminal
```

Requires `pip install hidapi pillow pynput`.

Runs automatically at login via a Startup shortcut:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\TT Keyboard Sync.lnk`
(launches `pythonw` so there is no console window; output goes to `sync.log`).
Delete that shortcut to disable autostart. Only one instance can run at a time -
the process holds loopback port 49731 as a lock.

## How it works

| File | Role |
|---|---|
| `tt_level20.py` | USB HID driver for `264A:3017` |
| `leds.py`       | LED index groups (keys, logos, centre strip, outer frame) |
| `accent.py`     | Reads the Windows accent colour from the registry |
| `wallpaper.py`  | Finds current wallpaper, extracts a dominant colour |
| `ledcolor.py`   | Adapts any source colour for LED display; fades |
| `render.py`     | Base colour -> per-LED frame, with per-zone gains |
| `reactive.py`   | Keypress listener + hue-preserving pulse |
| `watchers.py`   | Win32 change notifications (registry key / folder) |
| `sync.py`       | Ties it together; waits for events, renders pulse |

### Colour sources

`--source accent` (default) reads entry 3 of
`HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent\AccentPalette`
(eight RGBA shades, light to dark). Entry 3 is byte-for-byte what Windows' own
`UISettings.GetColorValue(UIColorType.Accent)` returns. With *Automatically pick
an accent color from my background* enabled, Windows recomputes it whenever the
wallpaper slideshow rotates.

Don't use `DWM\AccentColor` for this. It looks like the accent and often
matches it, but it's the title-bar colourization value. On this machine it
stayed on a stale colour and snapped back to it ~50ms after each accent
change, so an earlier version briefly showed the new colour and then reverted.

`--source wallpaper` uses this project's own pick: median-cut the wallpaper into
16 buckets, score each on `frequency x saturation x brightness`.

### Event-driven updates

Nothing is polled in normal operation. `RegNotifyChangeKeyValue` on the Accent
key (the same mechanism Chrome uses to follow the accent) and
`FindFirstChangeNotification` on the Themes folder wake the loop the moment
Windows writes a change - measured at ~40ms from the registry write to the
keyboard repainting.

A notification only means *something* under that key/folder changed, so each
source also has a cheap change token (palette bytes / file mtime); the keyboard
is repainted only when the token actually differs. The wallpaper source also
waits for the file to stop changing before decoding it, so a burst of writes
while Windows transcodes produces one repaint, not several.

The main loop blocks on a single event set by the colour watcher and by the
keypress listener, so at rest it uses no CPU at all, and a keypress starts the
pulse immediately. `--interval` is only a safety re-check (default 60s) in case
a notification is ever missed, e.g. across sleep/resume; if notifications
can't be registered at all it falls back to polling every 2s.

### LED adaptation

Every source colour passes through `normalize_for_leds()` before reaching the
keyboard: saturation and brightness are floored at 45% and 55%, because dark or
muted colours look muddy on LEDs. Hue is never changed. So the keyboard
deliberately does *not* show the exact source value — e.g. `#69250C` is
normalized to `#8C3110` before the per-zone gains below.

The same drive level also looks very different across the board. Key LEDs sit
under opaque keycaps, so only light escaping through the legends and gaps
reaches the eye; the logo and light strips are bare diffusers and look bright
and washed out. `render.frame_for()` therefore applies per-zone gains, chosen by
eye on the real keyboard: **keys x1.5** (capped at full drive) and **logo +
strips x0.5**. Keeping the decorative zone dim is also what gives the keypress
pulse — which only runs on the outer frame — room to brighten visibly.

### Colour transitions

A new colour fades in over `--fade` seconds (default 1.0) instead of snapping.
The path matters: consecutive accents are often near-opposite hues (rust ->
teal), and a straight crossfade in RGB - or even perceptual OKLab - passes
through a dull grey midway (saturation ~0.2, muddy on LEDs). Blending in OKLCh
rotates hue along the short arc instead, so the colour stays vivid and passes
briefly through an in-between hue. Smoothstep easing starts and ends gently.

If another change arrives mid-fade, the next fade starts from whatever is on
the LEDs at that moment, so it redirects without a jump. Each frame repaints
the whole keyboard in one pass with the keypress pulse layered on, and frames
are paced to a budget rather than a fixed sleep: a full repaint is ~37ms of USB
time, so fades run at ~26fps, about the hardware ceiling.

### Reactive pulse

`--reactive` brightens the 34 outer-frame LEDs on each keypress and decays back
over roughly 250ms. The boost is hue-preserving: the multiplier is capped at
`255 / max(channel)` so all channels rise and stop together, rather than the
brightest channel saturating while the others keep climbing and shift the hue. The two logo LEDs (`0xB1`, `0xB2`) are deliberately excluded
so branding stays steady. Held keys pulse once: Windows auto-repeat is
suppressed by firing only on the up->down transition.

The key listener notes only *that* a key was pressed. Key identity is used
solely as an in-memory dedupe token for auto-repeat, is never logged or
persisted, and is discarded on release.

The wallpaper is read from `%APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper`.
Windows re-transcodes into this one file whenever the wallpaper changes, so its
mtime is a reliable change signal — which matters here because this desktop uses
a wallpaper **slideshow**, not a fixed image.

Colour choice deliberately avoids a plain average, which on most photos yields a
muddy grey-brown. Instead the image is median-cut into 16 buckets and each is
scored on `frequency x saturation x brightness`, then floored to a minimum
saturation/value so it reads well on LEDs.

## Device protocol

- Interface **1**, usage page **0xFF00**, **65-byte output reports** (1 report-ID
  byte + 64-byte payload). The device exposes **no feature reports**.
- `enter_software_mode()` sends `0x41 0x03 ... 0x40 0x61`. Without this the
  keyboard stays on onboard effects and silently ignores colour writes.
- Colour frames are 11 reports of 15 LEDs, each LED an explicit `(index, R, G, B)`
  quad:

```
payload[0:4] = C0 01 0F F7        # 0x06 instead of 0x0F on the last report
payload[4 + n*4 : +4] = index, r, g, b
```

Protocol credit: reverse engineered from USB HID captures by the community
SignalRGB plugin [devilnaked/ttlevel20signalrgb](https://github.com/devilnaked/ttlevel20signalrgb) (MIT).

## Things that do NOT work (investigated, ruled out)

- **TT iTAKE Engine** — its Level 20 modules hardcode PIDs `0x1018`/`0x1024`
  (`cmp ecx, 0x1018` in `LEVEL20_x64.dll`). This keyboard is `0x3017`. It can
  never enumerate it, regardless of reinstalling.
- **OpenRGB** — ships one Thermaltake keyboard driver, Poseidon Z RGB `0x3006`,
  using 264-byte *feature* reports. Wrong PID and wrong transport.
- **Razer Chroma / Synapse** — TT RGB PLUS is a Chroma *Broadcast subscriber*
  (`RzChromaSync.cpp`), not an SDK target. Broadcast never goes live under
  Synapse 4, so TT hides its Razer toggle. Not fixable from outside the vendors.

## Fans / case lighting - investigated, not possible

The case fans and AIO cannot be driven from software on this machine. This is a
conclusive negative, not an untested guess:

- **USB**: no RGB controller of any kind besides the keyboard.
- **SMBus**: opened successfully with PawnIO + admin (i801 `8086:A323` and
  NCT6791 both registered, and DIMM presence detection worked, proving the bus
  was readable) - yet nothing answered at the ASRock Polychrome or ENE
  addresses. The only RGB device OpenRGB found system-wide was a DualSense pad.

The ASRock Z390M Pro4 most likely drives its RGB headers straight from the
NCT6791 Super I/O with no addressable controller, so the colour is fixed in BIOS
or by an in-case hardware controller. Change it in the ASRock BIOS RGB page.

## Rollback tooling

`snapshot.ps1` / `diff-snapshot.ps1` capture and compare system state
(programs, services, drivers, tasks, autoruns, directories, registry) so vendor
software installed during investigation can be removed cleanly. Snapshots are
written to `baseline/<label>/`, which is git-ignored - it is an inventory of the
machine it ran on (programs, services, listening ports, registry), so it stays
local. `diff-snapshot.ps1 -From before -To after` lists everything added.

`make-restore-point.ps1` (needs admin) enables System Restore and takes a
checkpoint.

`cleanup-vendor-software.ps1` (needs admin) uninstalls TT iTAKE Engine,
Thermaltake Tool and PawnIO - none of which the keyboard sync depends on.

`detect-rgb.ps1` (needs admin) re-runs an OpenRGB SMBus scan, if you ever want
to revisit case lighting. It requires OpenRGB and PawnIO to be reinstalled.
