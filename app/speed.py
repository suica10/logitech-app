"""Pointer speed control for the MX Master 2S app.

One virtual slider (1..40) mapped onto (Windows pointer speed 1..20) x
(mouse DPI 200..4000, via HID++ 0x2201):

- virtual 20 == the Windows GUI maximum (speed 20, multiplier 3.5) at the
  base DPI 2000.
- virtual 21..40 keep Windows at 20 and raise the DPI 2100..4000, so
  virtual 40 is exactly twice the Windows-maximum effective speed.
- virtual 1..19 keep the DPI at 2000 and lower the Windows speed.

Effective speed (counts per inch the cursor logic sees) is monotonic in
the virtual value: effective(v) = dpi(v) * WIN_MULT[win(v)].
"""

import ctypes
from ctypes import wintypes

SPI_GETMOUSESPEED = 0x0070
SPI_SETMOUSESPEED = 0x0071
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

BASE_DPI = 2000
MAX_DPI = 4000
WIN_MAX = 20
VIRTUAL_MAX = 40

# Windows pointer-speed value -> cursor multiplier (documented mapping).
WIN_MULT = {
    1: 0.03125, 2: 0.0625, 3: 0.125, 4: 0.25, 5: 1.0 / 3.0,
    6: 0.5, 7: 2.0 / 3.0, 8: 0.8, 9: 0.9, 10: 1.0,
    11: 1.1, 12: 1.25, 13: 1.5, 14: 1.75, 15: 2.0,
    16: 2.25, 17: 2.5, 18: 2.75, 19: 3.0, 20: 3.5,
}

_user32 = ctypes.WinDLL("user32", use_last_error=True)


def get_win_speed():
    """Current Windows pointer speed (1..20)."""
    v = wintypes.INT()
    if not _user32.SystemParametersInfoW(
            SPI_GETMOUSESPEED, 0, ctypes.byref(v), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return v.value


def set_win_speed(value):
    """Set Windows pointer speed (1..20), persisted to the user profile."""
    value = max(1, min(WIN_MAX, int(value)))
    if not _user32.SystemParametersInfoW(
            SPI_SETMOUSESPEED, 0, ctypes.c_void_p(value),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE):
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def virtual_to_pair(v):
    """Virtual slider value -> (windows_speed, dpi_x)."""
    v = max(1, min(VIRTUAL_MAX, int(round(v))))
    if v <= WIN_MAX:
        return v, BASE_DPI
    dpi = int(round(BASE_DPI * v / WIN_MAX / 50.0)) * 50
    return WIN_MAX, min(MAX_DPI, dpi)


def effective(v):
    """Effective counts/inch for a virtual value."""
    win, dpi = virtual_to_pair(v)
    return dpi * WIN_MULT[win]


def nearest_virtual(dpi_x, win_speed):
    """Virtual value whose effective speed is closest to a live state."""
    target = dpi_x * WIN_MULT.get(win_speed, 1.0)
    return min(range(1, VIRTUAL_MAX + 1),
               key=lambda v: abs(effective(v) - target))
