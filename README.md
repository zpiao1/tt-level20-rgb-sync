# tt-keyboard-sync

Drives the **Thermaltake Level 20 RGB** (`KB-LVT-SSBRUS-01`) backlight from the
current desktop wallpaper. Talks to the keyboard directly over USB HID — no
Thermaltake, Razer, or SignalRGB software involved at runtime.

## Usage

```
python sync.py --reactive          # wallpaper sync + keypress pulse
python sync.py                     # wallpaper sync only
python sync.py --once              # apply current colour and exit
python sync.py --reactive --boost 0.9 --decay 0.20
python wallpaper.py                # print the colour that would be used
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
| `wallpaper.py`  | Finds current wallpaper, extracts an accent colour |
| `reactive.py`   | Keypress listener + pulse envelope |
| `sync.py`       | Ties it together; watches wallpaper, renders pulse |

### Reactive pulse

`--reactive` brightens the 34 outer-frame LEDs on each keypress and decays back
over roughly 250ms. The two logo LEDs (`0xB1`, `0xB2`) are deliberately excluded
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
