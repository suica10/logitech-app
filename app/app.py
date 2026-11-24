"""MX Master 2S per-app button remapper (Logi Options+ replacement, v0.1).

Resident loop:
- Connects to the mouse over HID++ (see hidpp.py) and diverts the thumb /
  gesture / mode-shift buttons (CIDs 0x53, 0x56, 0xC3, 0xC4).
- Watches the foreground window's process.
- On a diverted press, injects the keystroke configured for that app
  (config.json), falling back to the "default" profile.
- The gesture button (0xC3) accumulates raw XY deltas while held; on release
  the dominant direction (or a tap) selects the mapping.
- On exit, the original CID reporting flags are restored exactly.

Usage:
    python app.py [--config config.json] [--dry-run] [--seconds N]

--dry-run logs "would inject ..." instead of sending keys (smoke tests).
--seconds N auto-exits after N seconds (0 = run forever).
"""

import argparse
import ctypes
import json
import logging
import os
import struct
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import (  # noqa: E402
    CID_FLAG_DIVERTED,
    FEATURE_REPROG_CONTROLS_V4,
    HIDPPDevice,
)

# --------------------------------------------------------------------------
# Buttons (CIDs measured on the real device, 2026-11-24)
CID_BACK = 0x0053
CID_FORWARD = 0x0056
CID_GESTURE = 0x00C3
CID_MODE_SHIFT = 0x00C4

CID_ACTIONS = {
    CID_BACK: "back",
    CID_FORWARD: "forward",
    CID_MODE_SHIFT: "mode_shift",
}
DIVERT_CIDS = [CID_BACK, CID_FORWARD, CID_GESTURE, CID_MODE_SHIFT]

GESTURE_THRESHOLD = 60  # summed |delta| counts needed to call it a swipe

# --------------------------------------------------------------------------
# Foreground window (ctypes only, no psutil)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground_exe():
    """Basename of the foreground window's process exe, or '' if unknown."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(handle)


# --------------------------------------------------------------------------
# Key injection via SendInput

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
INPUT_KEYBOARD = 1

VK = {
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D,
    # browser / media (extended keys)
    "browser_back": 0xA6, "browser_forward": 0xA7,
    "browser_refresh": 0xA8, "browser_home": 0xAC,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "next_track": 0xB0, "prev_track": 0xB1,
    "play_pause": 0xB3, "media_play_pause": 0xB3,
}
for _i in range(12):
    VK[f"f{_i + 1}"] = 0x70 + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)

EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x21, 0x22, 0x23, 0x24, 0x2D, 0x2E,
            0x5B, 0xA6, 0xA7, 0xA8, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB3}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _send_vk(vk, key_up):
    flags = KEYEVENTF_KEYUP if key_up else 0
    if vk in EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0,
                              dwExtraInfo=None)
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def inject_sequence(sequence):
    """Inject e.g. 'ctrl+shift+t', 'alt+Left', or a single token like
    'browser_back'. Tokens are case-insensitive."""
    tokens = [t.strip().lower() for t in sequence.split("+") if t.strip()]
    vks = []
    for tok in tokens:
        if tok not in VK:
            raise ValueError(f"unknown key token: {tok!r} in {sequence!r}")
        vks.append(VK[tok])
    for vk in vks:
        _send_vk(vk, key_up=False)
    for vk in reversed(vks):
        _send_vk(vk, key_up=True)


# --------------------------------------------------------------------------

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("default", {})
    cfg.setdefault("apps", {})
    return cfg


def lookup(cfg, exe, action):
    profile = cfg["apps"].get(exe) if exe else None
    if profile:
        seq = profile.get(action)
        if seq == "none":
            return None  # explicitly disabled in this app: no fallback
        if seq:
            return seq
    return cfg["default"].get(action) or None


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "config.json"))
    ap.add_argument("--dry-run", action="store_true",
                    help="log actions instead of injecting keys")
    ap.add_argument("--seconds", type=int, default=0,
                    help="auto-exit after N seconds (0 = forever)")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    log = logging.getLogger("mx2s")

    cfg = load_config(args.config)
    log.info("config loaded: %s (default=%d keys, apps=%s)",
             args.config, len(cfg["default"]), list(cfg["apps"].keys()))

    dev = HIDPPDevice(device_index=1)
    original_flags = {}
    try:
        proto = dev.ping()
        name = dev.device_name()
        level, status = dev.battery()
        log.info("connected: %s (HID++ %d.%d), battery %d%% status %d",
                 name, proto[0], proto[1], level, status)
        reprog_idx = dev.feature_index(FEATURE_REPROG_CONTROLS_V4)

        for cid in DIVERT_CIDS:
            flags = dev.get_cid_reporting(cid)
            original_flags[cid] = flags
            if not flags & CID_FLAG_DIVERTED:
                dev.set_diverted(cid, True)
            log.info("divert set: CID 0x%04x (flags 0x%02x -> diverted)",
                     cid, flags)

        deadline = time.time() + args.seconds if args.seconds else None
        current_exe = None
        last_fg_check = 0.0
        gesture = None  # [sum_dx, sum_dy] while the gesture button is held
        pressed = set()  # CIDs currently reported as pressed

        log.info("running (dry-run=%s)", args.dry_run)
        while True:
            now = time.time()
            if deadline and now >= deadline:
                log.info("time limit reached, exiting")
                break
            if now - last_fg_check > 0.25:
                last_fg_check = now
                exe = foreground_exe()
                if exe != current_exe:
                    current_exe = exe
                    log.info("foreground: %s", exe or "(unknown)")

            msg = dev.poll_notification(timeout=0.05)
            if msg is None or len(msg) < 6:
                continue
            if msg[0] != 0x11 or msg[1] != dev.device_index or msg[2] != reprog_idx:
                continue
            fn = msg[3] >> 4
            if fn == 0:
                # divertedButtonsEvent: payload = set of pressed CIDs as
                # big-endian uint16 pairs, zero-terminated (all-zero = all
                # released).
                now_pressed = set()
                for off in range(4, len(msg) - 1, 2):
                    cid = struct.unpack(">H", msg[off:off + 2])[0]
                    if cid == 0:
                        break
                    now_pressed.add(cid)
                for cid in sorted(now_pressed - pressed):
                    if cid == CID_GESTURE:
                        gesture = [0, 0]
                        log.info("gesture press (app=%s)", current_exe)
                    elif cid in CID_ACTIONS:
                        fire(cfg, current_exe, CID_ACTIONS[cid],
                             args.dry_run, log)
                    else:
                        log.info("diverted press: CID 0x%04x (app=%s)",
                                 cid, current_exe)
                if CID_GESTURE in pressed and CID_GESTURE not in now_pressed \
                        and gesture is not None:
                    dx, dy = gesture
                    gesture = None
                    fire(cfg, current_exe, classify_gesture(dx, dy),
                         args.dry_run, log)
                pressed = now_pressed
            elif fn == 1 and gesture is not None:
                # diverted XY event while the gesture button is held
                dx, dy = struct.unpack(">hh", msg[4:8])
                gesture[0] += dx
                gesture[1] += dy
    except KeyboardInterrupt:
        log.info("interrupted")
    finally:
        for cid, flags in original_flags.items():
            try:
                back = dev.set_diverted(cid, bool(flags & CID_FLAG_DIVERTED))
                if back != flags:
                    log.warning("divert restore CID 0x%04x: read back 0x%02x, "
                                "original was 0x%02x", cid, back, flags)
                log.info("divert restored: CID 0x%04x flags 0x%02x", cid, back)
            except Exception as e:  # noqa: BLE001
                log.error("failed to restore CID 0x%04x: %s", cid, e)
        dev.close()
        log.info("bye")


def classify_gesture(dx, dy):
    if abs(dx) + abs(dy) < GESTURE_THRESHOLD:
        return "gesture_tap"
    if abs(dx) >= abs(dy):
        return "gesture_right" if dx > 0 else "gesture_left"
    return "gesture_down" if dy > 0 else "gesture_up"


def fire(cfg, exe, action, dry_run, log):
    seq = lookup(cfg, exe, action)
    if not seq:
        log.info("action %s (app=%s): no mapping", action, exe)
        return
    if dry_run:
        log.info("action %s (app=%s): would inject %r", action, exe, seq)
        return
    try:
        inject_sequence(seq)
        log.info("action %s (app=%s): injected %r", action, exe, seq)
    except Exception as e:  # noqa: BLE001
        log.error("action %s (app=%s): inject %r failed: %s", action, exe, seq, e)


if __name__ == "__main__":
    main()
