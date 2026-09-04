"""
Thermaltake Level 20 RGB (264A:3017) direct lighting control over USB HID.

Protocol derived from the community SignalRGB plugin
(github.com/devilnaked/ttlevel20signalrgb, MIT), reverse engineered from USB
HID captures. Transport verified against this device: interface 1,
usage page 0xFF00, 65-byte output reports, no feature reports.
"""
import time

import hid

from leds import ALL_INDEXES, REPORT_INDEXES, reports_touching

VID, PID = 0x264A, 0x3017

# Handshake that hands control from the keyboard's onboard effects to the host.
# Without this, colour writes are accepted and silently ignored.
SOFTWARE_MODE_SEQUENCE = [
    ([0x41, 0x03], 0),
    ([0x43, 0x00, 0x00, 0x00, 0x01], 0),
    ([0x51, 0x00], 0),
    ([0x50, 0x00], 0),
    ([0x12, 0x22], 30),
    ([0x52, 0x92], 30),
    ([0x52, 0x10], 0),
    ([0x40, 0x61], 0),
]


class Level20:
    def __init__(self):
        path = self._find_endpoint()
        if path is None:
            raise RuntimeError(f"No vendor interface for {VID:04X}:{PID:04X}")
        self.dev = hid.device()
        self.dev.open_path(path)
        self.dev.set_nonblocking(True)
        # Shadow copy of every LED, so a partial update can rebuild the
        # untouched LEDs that share a report with the ones being changed.
        self.state = {i: (0, 0, 0) for i in ALL_INDEXES}

    @staticmethod
    def _find_endpoint():
        for d in hid.enumerate(VID, PID):
            if d["interface_number"] == 1 and d["usage_page"] == 0xFF00:
                return d["path"]
        return None

    # -- transport ---------------------------------------------------------

    def _send_payload(self, payload):
        report = bytes([0x00]) + bytes(payload)      # leading report ID
        written = self.dev.write(report)
        time.sleep(0.002)
        self.dev.read(65)                            # drain the device ack
        return written

    def _send_command(self, cmd_bytes):
        payload = bytearray(64)
        payload[: len(cmd_bytes)] = bytes(cmd_bytes)
        return self._send_payload(payload)

    def enter_software_mode(self):
        for cmd, pause_ms in SOFTWARE_MODE_SEQUENCE:
            self._send_command(cmd)
            if pause_ms:
                time.sleep(pause_ms / 1000)

    # -- colour ------------------------------------------------------------

    def _send_report(self, report_no):
        payload = bytearray(64)
        payload[0] = 0xC0
        payload[1] = 0x01
        payload[2] = 0x06 if report_no == 10 else 0x0F
        payload[3] = 0xF7
        for entry, index in enumerate(REPORT_INDEXES[report_no]):
            r, g, b = self.state[index]
            off = 4 + entry * 4
            payload[off]     = index
            payload[off + 1] = r & 0xFF
            payload[off + 2] = g & 0xFF
            payload[off + 3] = b & 0xFF
        return self._send_payload(payload)

    def set_leds(self, colors_by_index, flush=True):
        """Update specific LEDs. Only reports containing them are resent."""
        self.state.update(colors_by_index)
        if not flush:
            return []
        return [self._send_report(n) for n in reports_touching(colors_by_index)]

    def set_solid(self, r, g, b):
        """Paint every LED the same colour."""
        self.state.update({i: (r, g, b) for i in ALL_INDEXES})
        return [self._send_report(n) for n in range(len(REPORT_INDEXES))]

    def close(self):
        self.dev.close()


if __name__ == "__main__":
    kb = Level20()
    try:
        print("Entering software mode ...")
        kb.enter_software_mode()
        for name, rgb in [("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
                          ("BLUE", (0, 0, 255)), ("AMBER", (255, 200, 120))]:
            res = kb.set_solid(*rgb)
            print(f"  {name:<6} rgb{rgb} -> {len(res)} reports, all 65B: {all(n == 65 for n in res)}")
            time.sleep(2)
        print("Done.")
    finally:
        kb.close()
