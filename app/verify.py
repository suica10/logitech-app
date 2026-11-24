"""On-device verification for the MX Master 2S HID++ client.

Checks (in order):
  1. ping + protocol version
  2. device name
  3. battery level
  4. DPI read
  5. Divert round-trip on CID 0x0053 (back): read flags, toggle the diverted
     bit, read back and confirm, write the ORIGINAL flags back, read back and
     confirm the device is exactly as found.

Prints PASS/FAIL lines; exit code 0 only if everything passes.
Run with the logi venv python on the desktop.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import CID_FLAG_DIVERTED, HIDPPDevice  # noqa: E402

CID_TEST = 0x0053  # back button

failures = []


def _dpi_list_summary(dev):
    lst = dev.get_dpi_list()
    if not lst:
        raise AssertionError("empty DPI list")
    steps = {b - a for a, b in zip(lst, lst[1:])}
    return f"count={len(lst)} min={lst[0]} max={lst[-1]} steps={sorted(steps)}"


def check(label, fn):
    try:
        value = fn()
        print(f"PASS {label}: {value}", flush=True)
        return value
    except Exception as e:  # noqa: BLE001
        print(f"FAIL {label}: {type(e).__name__}: {e}", flush=True)
        failures.append(label)
        return None


def main():
    dev = HIDPPDevice(device_index=1)
    try:
        check("ping", lambda: "HID++ %d.%d" % dev.ping())
        check("device_name", dev.device_name)
        check("battery", lambda: "level=%d%% status=%d" % dev.battery())
        check("dpi", lambda: "x=%d y=%d" % dev.get_dpi())
        check("dpi_list", lambda: _dpi_list_summary(dev))

        orig_flags = check("divert_read_original",
                            lambda: "flags=0x%02x" % dev.get_cid_reporting(CID_TEST))
        if orig_flags is not None:
            orig = dev.get_cid_reporting(CID_TEST)
            want_toggled = orig ^ CID_FLAG_DIVERTED

            def round_trip():
                back = dev.set_diverted(CID_TEST, not (orig & CID_FLAG_DIVERTED))
                if back != want_toggled:
                    raise AssertionError(
                        f"after toggle, read back 0x{back:02x}, want 0x{want_toggled:02x}")
                return f"flags 0x{orig:02x} -> 0x{back:02x} confirmed via GET"

            check("divert_toggle", round_trip)

            def restore():
                back = dev.set_diverted(CID_TEST, bool(orig & CID_FLAG_DIVERTED))
                if back != orig:
                    raise AssertionError(
                        f"restore failed: read 0x{back:02x}, want 0x{orig:02x}")
                return f"flags restored to 0x{orig:02x}"

            check("divert_restore", restore)
    finally:
        dev.close()

    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}", flush=True)
        return 1
    print("RESULT: ALL PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
