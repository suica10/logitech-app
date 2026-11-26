"""MX Master 2S per-app button remapper (Logi Options+ replacement, v0.2).

Resident loop:
- Connects to the mouse over HID++ (see hidpp.py) and diverts the thumb /
  gesture / mode-shift buttons (CIDs 0x53, 0x56, 0xC3, 0xC4).
- Watches the foreground window's process.
- On a diverted press, injects the keystroke configured for that app
  (config.json), falling back to the "default" profile.
- The gesture button (0xC3) accumulates raw XY deltas while held; on release
  the dominant direction (or a tap) selects the mapping.
- On exit, the original CID reporting flags are restored exactly.

Pointer speed (v0.2):
- A single virtual slider (1..40) drives Windows pointer speed (1..20)
  and the mouse DPI together (see speed.py): 20 = Windows GUI maximum,
  40 = twice that. The setting lives in config.json ("pointer") and is
  re-applied at startup.
- Settings window: hidden; creating show_gui.flag next to this file (the
  desktop launcher does that) pops it up. Closing the window hides it;
  the resident app keeps running.

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
import threading
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import (  # noqa: E402
    CID_FLAG_DIVERTED,
    FEATURE_REPROG_CONTROLS_V4,
    HIDPPDevice,
)
import speed as pspeed  # noqa: E402

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
    cfg.setdefault("pointer", {})
    return cfg


def save_config(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def lookup(cfg, exe, action):
    profile = cfg["apps"].get(exe) if exe else None
    if profile:
        seq = profile.get(action)
        if seq == "none":
            return None  # explicitly disabled in this app: no fallback
        if seq:
            return seq
    return cfg["default"].get(action) or None


# --------------------------------------------------------------------------
# Pointer speed: apply / adopt, state file for headless verification

def write_state(here, **kw):
    path = os.path.join(here, "state.json")
    try:
        state = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        state.update(kw)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def apply_pointer(dev, cfg, config_path, here, log, virtual=None):
    """Apply a virtual speed (or the saved one) to Windows + the mouse.

    Returns the virtual value in effect. Raises on device/OS errors;
    callers decide whether that is fatal.
    """
    if virtual is None:
        virtual = int(cfg["pointer"]["virtual"])
    win, dpi = pspeed.virtual_to_pair(virtual)
    pspeed.set_win_speed(win)
    got_x, got_y = dev.set_dpi(dpi, dpi)
    cfg["pointer"] = {"virtual": virtual, "win_speed": win, "dpi_x": dpi}
    save_config(config_path, cfg)
    write_state(here, connected=True, virtual=virtual, win_speed=win,
                dpi_x=got_x, dpi_y=got_y)
    log.info("pointer: virtual %d -> win %d, dpi %d (read back %d/%d)",
             virtual, win, dpi, got_x, got_y)
    return virtual


def adopt_pointer(dev, cfg, config_path, here, log):
    """First run: take the live state as the slider position, change
    nothing, and persist it so later startups re-apply it."""
    dpi_x, dpi_y = dev.get_dpi()
    win = pspeed.get_win_speed()
    virtual = pspeed.nearest_virtual(dpi_x, win)
    cfg["pointer"] = {"virtual": virtual, "win_speed": win, "dpi_x": dpi_x}
    save_config(config_path, cfg)
    write_state(here, connected=True, virtual=virtual, win_speed=win,
                dpi_x=dpi_x, dpi_y=dpi_y)
    log.info("pointer: adopted live state win %d dpi %d -> virtual %d",
             win, dpi_x, virtual)
    return virtual


# --------------------------------------------------------------------------
# Settings window (Tk). Hidden until show_gui.flag appears.

class SettingsWindow:
    def __init__(self, root, dev, cfg, config_path, here, log, virtual):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.dev = dev
        self.cfg = cfg
        self.config_path = config_path
        self.here = here
        self.log = log
        self.flag_path = os.path.join(here, "show_gui.flag")

        root.title("MX Master 2S 設定")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", root.withdraw)

        frame = tk.Frame(root, padx=16, pady=12)
        frame.pack()

        tk.Label(frame, text="カーソル速度").pack(anchor="w")
        self.var = tk.IntVar(value=virtual)
        self.scale = tk.Scale(
            frame, from_=1, to=pspeed.VIRTUAL_MAX, orient="horizontal",
            variable=self.var, showvalue=False, length=440,
            command=self._on_slide)
        self.scale.pack()
        self.scale.bind("<ButtonRelease-1>", self._on_release)

        marks = tk.Frame(frame)
        marks.pack(fill="x")
        tk.Label(marks, text="遅い").pack(side="left")
        tk.Label(marks, text="2倍").pack(side="right")
        tk.Label(marks, text="Windows最大").pack(side="right", padx=(0, 118))

        self.readout = tk.Label(frame, text="")
        self.readout.pack(anchor="w", pady=(8, 0))
        self._update_readout(virtual)

        root.withdraw()
        root.after(400, self._poll_flag)

    def _pair_text(self, v):
        win, dpi = pspeed.virtual_to_pair(v)
        return (f"{v / pspeed.WIN_MAX:.2f} 倍　"
                f"（DPI {dpi} × Windows速度 {win}、実効 {pspeed.effective(v):,.0f}）")

    def _update_readout(self, v):
        self.readout.config(text=self._pair_text(int(v)))

    def _on_slide(self, value):
        self._update_readout(int(float(value)))

    def _on_release(self, _event):
        v = int(self.var.get())
        try:
            apply_pointer(self.dev, self.cfg, self.config_path,
                          self.here, self.log, virtual=v)
        except Exception as e:  # noqa: BLE001
            self.log.error("pointer apply failed: %s", e)
        self._update_readout(v)

    def _poll_flag(self):
        if os.path.exists(self.flag_path):
            try:
                os.remove(self.flag_path)
            except OSError:
                pass
            # Refresh the slider from the persisted setting.
            v = int(self.cfg.get("pointer", {}).get("virtual", self.var.get()))
            self.var.set(v)
            self._update_readout(v)
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            write_state(self.here, gui_shown_at=time.time())
        self.root.after(400, self._poll_flag)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "config.json"))
    ap.add_argument("--dry-run", action="store_true",
                    help="log actions instead of injecting keys")
    ap.add_argument("--seconds", type=int, default=0,
                    help="auto-exit after N seconds (0 = forever)")
    ap.add_argument("--no-gui", action="store_true",
                    help="run headless (no settings window)")
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

    # Startup retry: at logon the receiver/mouse may not be ready yet
    # (USB still enumerating, mouse asleep). Retry the whole connect +
    # divert setup for up to ~3 minutes instead of dying instantly.
    dev = None
    original_flags = {}
    reprog_idx = None
    for attempt in range(36):
        try:
            dev = HIDPPDevice(device_index=1)
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
            break
        except Exception as e:  # noqa: BLE001
            log.warning("connect attempt %d failed: %s", attempt + 1, e)
            if dev is not None:
                for cid, flags in original_flags.items():
                    try:
                        dev.set_diverted(cid, bool(flags & CID_FLAG_DIVERTED))
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
            dev = None
            original_flags = {}
            time.sleep(5)
    if dev is None:
        log.error("could not connect to the mouse after retries; exiting")
        return

    # Pointer speed: re-apply the saved setting; on first run adopt the
    # live state without changing anything.
    virtual = None
    try:
        if cfg["pointer"].get("virtual"):
            virtual = apply_pointer(dev, cfg, args.config, here, log)
        else:
            virtual = adopt_pointer(dev, cfg, args.config, here, log)
    except Exception as e:  # noqa: BLE001
        log.warning("pointer setup failed (continuing): %s", e)

    stop_gui = threading.Event()

    def resident_loop():
        try:
            run_loop(dev, original_flags, cfg, args, log)
        finally:
            stop_gui.set()

    thread = threading.Thread(target=resident_loop, daemon=True)
    thread.start()

    if args.no_gui:
        thread.join()
        return

    try:
        import tkinter as tk
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
        root = tk.Tk()
    except Exception as e:  # noqa: BLE001
        log.warning("GUI unavailable (%s); running headless", e)
        thread.join()
        return

    if virtual is None:
        virtual = pspeed.nearest_virtual(*_live_pair(dev))
    SettingsWindow(root, dev, cfg, args.config, here, log, virtual)

    def watch_exit():
        if stop_gui.is_set():
            root.destroy()
            return
        root.after(300, watch_exit)

    root.after(300, watch_exit)
    root.mainloop()
    log.info("bye")


def _live_pair(dev):
    try:
        dpi_x, _ = dev.get_dpi()
        return dpi_x, pspeed.get_win_speed()
    except Exception:  # noqa: BLE001
        return pspeed.BASE_DPI, 10


def run_loop(dev, original_flags, cfg, args, log):
    reprog_idx = dev.feature_index(FEATURE_REPROG_CONTROLS_V4)
    try:
        deadline = time.time() + args.seconds if args.seconds else None
        current_exe = None
        last_fg_check = 0.0
        last_divert_check = 0.0
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

            # Watchdog: the mouse's divert state is volatile and resets
            # when the mouse sleeps / power-cycles / switches channel.
            # Re-check every 10 s and re-apply, otherwise the remapping
            # silently dies while this loop keeps running.
            if now - last_divert_check > 10.0:
                last_divert_check = now
                try:
                    for cid in DIVERT_CIDS:
                        if not dev.get_cid_reporting(cid) & CID_FLAG_DIVERTED:
                            dev.set_diverted(cid, True)
                            log.info("watchdog: re-applied divert for "
                                     "CID 0x%04x", cid)
                except Exception as e:  # noqa: BLE001
                    log.warning("watchdog divert check failed: %s", e)

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
        log.info("loop done")


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
