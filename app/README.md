# MX Master 2S remapper — Options+ replacement (v0.1)

A small resident tool that replaces the parts of Logi Options+ actually used
on this machine: per-app custom keys on the thumb buttons, mode-shift button
and gesture button of one **MX Master 2S** (Unifying receiver). No Flow, no
cloud, no pointer-speed overwriting — Windows pointer speed is never touched.

## Files

| file | role |
|---|---|
| `hidpp.py` | HID++ client over `hidapi` (ping, features, battery, DPI, CID divert) |
| `app.py` | resident loop: foreground-app watch + diverted-button → keystroke |
| `config.json` | per-app key mappings |
| `verify.py` | read-only-ish self-check (ping / name / battery / DPI / divert round-trip with restore) |

## Running it (on the desktop)

The venv built during the HID investigation is reused:

```
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\app.py
```

Run it in your own logged-on session (it needs to see your foreground window
and send keys to your apps). Useful flags:

- `--dry-run` — log `would inject ...` instead of sending keys.
- `--seconds 20` — auto-exit after 20 s (smoke tests).
- `--config <path>` — alternate config file.

Verify the device link any time with:

```
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\verify.py
```

## How it works

- Transport: HID++ long reports over the Unifying receiver's vendor HID
  interface (usage page 0xFF00 / usage 2), via the `hidapi` package.
  (`pywinusb` cannot send on this setup — every request errors out.)
- On start, the tool sets the *diverted* flag (0x1B04 SetCidReporting) for
  CIDs `0x0053` (back), `0x0056` (forward), `0x00C3` (gesture), `0x00C4`
  (mode shift). Diverted presses arrive as HID++ notifications instead of
  performing their built-in action. **On exit the original flags are
  restored exactly**, so quitting hands control back to Options+ / defaults.
  (Device quirk, verified: the set command byte is *value + valid* —
  `0x03` diverts, `0x02` un-diverts, anything without the valid bit is a
  no-op, and the set reply is all zeros, so state is always confirmed by
  reading back. Other reporting bits, e.g. the gesture button's raw-XY
  bit, are never touched.)
- The foreground process is polled (~4×/s) with `GetForegroundWindow` +
  `QueryFullProcessImageNameW`; its exe basename selects the profile.
- Keystrokes are injected with `SendInput`. Gesture button: raw XY deltas
  stream in while it is held; on release the dominant direction wins, or a
  tap if total movement is small.

## Config format

```json
{
  "default": { "back": "alt+Left", "...": "..." },
  "apps": {
    "SLDWORKS.exe": { "back": "ctrl+z" }
  }
}
```

- Keys of `apps` are process exe basenames (case-sensitive as reported by
  Windows, e.g. `chrome.exe`). An app entry overrides `default` per action;
  an empty string or a missing action falls back to `default`.
- Actions: `back`, `forward`, `mode_shift`, `gesture_tap`, `gesture_up`,
  `gesture_down`, `gesture_left`, `gesture_right`.
- Values are `+`-joined key tokens, case-insensitive: modifiers `ctrl`,
  `alt`, `shift`, `win`; letters/digits; `tab`, `enter`, `esc`, `space`,
  `left/right/up/down`, `home`, `end`, `pageup`, `pagedown`, `f1`–`f12`;
  browser/media tokens `browser_back`, `browser_forward`, `volume_up`,
  `volume_down`, `volume_mute`, `play_pause`, `next_track`, `prev_track`.

## Seed mappings (placeholders — change freely)

| action | default |
|---|---|
| back | `alt+Left` |
| forward | `alt+Right` |
| mode_shift | `ctrl+tab` |
| gesture_tap | `ctrl+w` |
| gesture_up/down/left/right | `win+Up` / `win+Down` / `win+Left` / `win+Right` (window snap — visible, harmless placeholders) |

`config.json` also contains an app entry with an empty name: rename its key
to your CAD app's exe name and fill in that app's actions.

## Known limits (v0.1)

- One device only: the MX Master 2S on slot 1 of the Unifying receiver.
  Bluetooth connection is not handled.
- If Options+ is running at the same time, both receive the diverted events
  and Options+ may re-assert its own divert settings; expect to run one or
  the other. (Pointer speed is safe either way — this tool never writes it.)
- The main wheel, thumb wheel and clicks are not remapped (standard HID).
- Gesture classification is a simple dominant-axis threshold.
