"""Tests for the Win32 change-notification watchers.

Uses a scratch registry key and a scratch folder, so the real accent colour
and wallpaper are never touched.

    python -m unittest test_watchers -v
"""
import os
import shutil
import tempfile
import threading
import time
import unittest
import winreg

from watchers import DirectoryWatcher, RegistryWatcher

SCRATCH_KEY = r"Software\tt-keyboard-sync-test"
FIRE_TIMEOUT = 2.0      # generous; real latency is expected in milliseconds


class RegistryWatcherTest(unittest.TestCase):
    def setUp(self):
        self.key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, SCRATCH_KEY)
        winreg.SetValueEx(self.key, "AccentColor", 0, winreg.REG_DWORD, 1)
        self.fired = threading.Event()
        self.watcher = RegistryWatcher(winreg.HKEY_CURRENT_USER, SCRATCH_KEY,
                                       self.fired.set)
        self.watcher.start()

    def tearDown(self):
        self.watcher.stop()
        winreg.CloseKey(self.key)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCRATCH_KEY)

    def test_fires_promptly_when_a_value_is_written(self):
        t0 = time.perf_counter()
        winreg.SetValueEx(self.key, "AccentColor", 0, winreg.REG_DWORD, 2)
        self.assertTrue(self.fired.wait(FIRE_TIMEOUT))
        self.assertLess(time.perf_counter() - t0, 0.1)

    def test_keeps_firing_after_the_first_change(self):
        for value in (2, 3, 4):
            self.fired.clear()
            winreg.SetValueEx(self.key, "AccentColor", 0, winreg.REG_DWORD, value)
            self.assertTrue(self.fired.wait(FIRE_TIMEOUT), f"missed write {value}")

    def test_stop_returns_promptly(self):
        t0 = time.perf_counter()
        self.watcher.stop()
        self.assertLess(time.perf_counter() - t0, 1.0)
        self.assertFalse(self.watcher.is_alive())


class DirectoryWatcherTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="tt-sync-test-")
        self.file = os.path.join(self.dir, "TranscodedWallpaper")
        open(self.file, "wb").close()
        self.fired = threading.Event()
        self.watcher = DirectoryWatcher(self.dir, self.fired.set)
        self.watcher.start()

    def tearDown(self):
        self.watcher.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_fires_when_a_file_in_the_folder_is_rewritten(self):
        with open(self.file, "wb") as fh:
            fh.write(b"new wallpaper")
        self.assertTrue(self.fired.wait(FIRE_TIMEOUT))

    def test_stop_returns_promptly(self):
        self.watcher.stop()
        self.assertFalse(self.watcher.is_alive())


if __name__ == "__main__":
    unittest.main()
