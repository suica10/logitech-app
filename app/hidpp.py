"""HID++ client for the MX Master 2S over a Unifying receiver (Windows, hidapi).

Transport notes (verified on the real hardware, 2026-11-24):
- Use the `hidapi` package (interrupt WriteFile). pywinusb's send path is broken
  on this setup: every request comes back with a fake instant error.
- HID++ interface: VID 0x046D, usage page 0xFF00, usage 2 (long reports 0x11,
  exactly 20 bytes total including the report id).
- The mouse is device index 1 on the receiver, HID++ protocol 4.5.

Request/reply matching follows the probe scripts: replies carry the request's
software id (swid) in the low nibble of byte 3; errors arrive as byte2 == 0x8F
with the original function|swid byte at byte 4 and the error code at byte 5.
Anything else received is an unsolicited notification and is queued for the
application (see poll_notification()).
"""

import queue
import struct
import threading
import time

import hid

VID_LOGITECH = 0x046D
USAGE_PAGE_HIDPP = 0xFF00
USAGE_HIDPP_LONG = 2  # long reports (0x11)
USAGE_HIDPP_SHORT = 1  # short reports (0x10)

REPORT_LONG = 0x11
MSG_LEN = 20  # long report total length, report id included

# Feature IDs
FEATURE_ROOT = 0x0000
FEATURE_FEATURE_SET = 0x0001
FEATURE_DEVICE_NAME = 0x0005
FEATURE_BATTERY = 0x1000
FEATURE_REPROG_CONTROLS_V4 = 0x1B04
FEATURE_ADJUSTABLE_DPI = 0x2201

# REPROG_CONTROLS_V4 (0x1B04) function indices
RC_FN_GET_COUNT = 0
RC_FN_GET_CID_INFO = 1
RC_FN_GET_CID_REPORTING = 2
RC_FN_SET_CID_REPORTING = 3

# CID reporting (0x1B04). GET returns a flags byte: bit0 = diverted,
# bit4 = raw XY reporting (seen on the gesture CID, flags 0x11).
# SET semantics VERIFIED EMPIRICALLY on this device (2026-11-24): the byte
# written is NOT the flags byte. bit0 is the desired diverted value and
# bit1 is a "valid/change" bit for it: writing 0x03 diverts, writing 0x02
# un-diverts, writing 0x00/0x01 (valid bit clear) changes nothing, and
# other flag bits are left untouched. The set reply payload is all zeros;
# always confirm via GET.
CID_FLAG_DIVERTED = 0x01
CID_SET_VALID = 0x02

HIDPP_ERROR_NAMES = {
    0x01: "ERR_UNKNOWN",
    0x02: "ERR_INVALID_ARGUMENT",
    0x03: "ERR_OUT_OF_RANGE",
    0x04: "ERR_HW_ERROR",
    0x05: "ERR_INTERNAL",
    0x06: "ERR_INVALID_FEATURE_INDEX",
    0x07: "ERR_INVALID_FUNCTION_ID",
    0x08: "ERR_BUSY",
    0x09: "ERR_UNSUPPORTED",
}


class HIDPPError(Exception):
    def __init__(self, code, context=""):
        self.code = code
        name = HIDPP_ERROR_NAMES.get(code, "ERR_?")
        super().__init__(f"HID++ error {code} ({name}) {context}".strip())


class HIDPPTimeout(Exception):
    pass


def _u16be(b, off):
    return (b[off] << 8) | b[off + 1]


class HIDPPDevice:
    """One HID++ device (the mouse) behind the Unifying receiver."""

    def __init__(self, device_index=1, vid=VID_LOGITECH):
        self.device_index = device_index
        self._path = None
        for d in hid.enumerate(vid, 0):
            if d["usage_page"] == USAGE_PAGE_HIDPP and d["usage"] == USAGE_HIDPP_LONG:
                self._path = d["path"]
                break
        if self._path is None:
            raise RuntimeError("HID++ long interface (usage page 0xFF00, usage 2) not found")

        self._dev = hid.device()
        self._dev.open_path(self._path)
        self._dev.set_nonblocking(False)

        self._inbox = queue.Queue()       # everything received
        self._notifications = queue.Queue()  # unsolicited messages only
        self._stop = False
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()

        self._request_lock = threading.Lock()
        self._swid = 0x08
        self._feature_index_cache = {FEATURE_ROOT: 0}

    # ------------------------------------------------------------------ I/O

    def _reader_loop(self):
        while not self._stop:
            try:
                data = self._dev.read(64, 200)
            except Exception:
                return
            if data:
                self._inbox.put(bytes(data))

    def close(self):
        self._stop = True
        try:
            self._dev.close()
        except Exception:
            pass

    def request(self, feature_index, function, params=b"", timeout=2.0):
        """Send a request, return the reply payload (bytes from offset 4).

        Raises HIDPPError on a device error reply, HIDPPTimeout on no reply.
        Non-matching messages received meanwhile are kept as notifications.
        """
        with self._request_lock:
            swid = self._swid
            self._swid = 0x08 + ((self._swid - 0x08 + 1) % 8)

            msg = bytearray(MSG_LEN)
            msg[0] = REPORT_LONG
            msg[1] = self.device_index
            msg[2] = feature_index
            msg[3] = (function << 4) | swid
            msg[4:4 + len(params)] = params
            self._dev.write(bytes(msg))

            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    r = self._inbox.get(timeout=max(0.05, deadline - time.time()))
                except queue.Empty:
                    break
                if len(r) < 5:
                    self._notifications.put(r)
                    continue
                # Error reply: byte2 == 0x8F, byte4 = original fn|swid, byte5 = code
                if r[2] == 0x8F and (r[4] & 0x0F) == swid:
                    raise HIDPPError(r[5], f"(feature idx {feature_index}, fn {function})")
                if (
                    r[0] == REPORT_LONG
                    and r[1] == self.device_index
                    and r[2] == feature_index
                    and (r[3] & 0x0F) == swid
                    and (r[3] >> 4) == function
                ):
                    return bytes(r[4:])
                self._notifications.put(r)
            raise HIDPPTimeout(
                f"no reply: feature idx {feature_index}, fn {function}"
            )

    def poll_notification(self, timeout=0.0):
        """Return one unsolicited message (raw bytes) or None."""
        try:
            return self._notifications.get(timeout=timeout)
        except queue.Empty:
            return None

    # ------------------------------------------------------------- features

    def ping(self):
        """Return (protocol_major, protocol_minor)."""
        payload = self.request(0, 1, bytes([0x5A, 0xA5, 0x3C]))
        return payload[0], payload[1]

    def feature_index(self, feature_id):
        """Resolve a feature ID to its index via Root GetFeature (cached)."""
        if feature_id in self._feature_index_cache:
            return self._feature_index_cache[feature_id]
        params = bytes([feature_id >> 8, feature_id & 0xFF, 0x00])
        payload = self.request(0, 0, params)
        idx = payload[0]
        if idx == 0 and feature_id != FEATURE_ROOT:
            raise HIDPPError(0x09, f"feature 0x{feature_id:04x} not present")
        self._feature_index_cache[feature_id] = idx
        return idx

    def enumerate_features(self):
        """Full {feature_id: index} map via FeatureSet (like probe6)."""
        fs_idx = self.feature_index(FEATURE_FEATURE_SET)
        count = self.request(fs_idx, 0)[0]
        table = {}
        for i in range(count):
            payload = self.request(fs_idx, 1, bytes([i]))
            fid = _u16be(payload, 0)
            table[fid] = i
            self._feature_index_cache[fid] = i
        return table

    def device_name(self):
        idx = self.feature_index(FEATURE_DEVICE_NAME)
        total = self.request(idx, 0)[0]
        name = ""
        offset = 0
        while offset < total:
            chunk = self.request(idx, 1, bytes([offset]))
            take = chunk[: total - offset]
            if not take:
                break
            name += take.decode("utf-8", "replace")
            offset += len(take)
        return name

    # -------------------------------------------------------------- battery

    def battery(self):
        """Return (level_percent, status_code).

        Raw reply on this device: [level, 50, status, ...] -- byte0 is the
        charge level in percent, byte2 the status (0 = discharging,
        1 = charging, 2 = nearly full, 3 = full, 4 = slow recharge).
        The middle byte (50) is not a valid status code; it is reported
        verbatim in probe7.log and left uninterpreted here.
        """
        idx = self.feature_index(FEATURE_BATTERY)
        payload = self.request(idx, 0)
        return payload[0], payload[2]

    # ------------------------------------------------------------------ DPI

    def get_dpi(self, sensor=0):
        """Current (dpi_x, dpi_y) via 0x2201 fn2 getSensorDPI.

        Reply layout verified on this device: [sensor echo, dpiX(2 BE),
        dpiY(2 BE), ...]. Current values: X=2650, Y=1000.
        """
        idx = self.feature_index(FEATURE_ADJUSTABLE_DPI)
        payload = self.request(idx, 2, bytes([sensor]))
        return _u16be(payload, 1), _u16be(payload, 3)

    def set_dpi(self, dpi_x, dpi_y=None, sensor=0):
        """Set DPI via 0x2201 fn3 setSensorDPI ([sensor, X(2 BE), Y(2 BE)]).

        Verified on this device: X is applied (800/1000/2650 round-trips
        confirmed). Y was NOT changed by any set in testing -- it read back
        1000 regardless of the value sent, so on this unit Y appears to be
        fixed/ignored. Returns the (x, y) read back after the set.
        """
        if dpi_y is None:
            dpi_y = dpi_x
        idx = self.feature_index(FEATURE_ADJUSTABLE_DPI)
        params = bytes([sensor]) + struct.pack(">HH", dpi_x, dpi_y)
        self.request(idx, 3, params)
        return self.get_dpi(sensor)

    def get_dpi_list(self, sensor=0):
        """Supported DPIs via 0x2201 fn1 getSensorDPIList.

        Reply layout verified on this device: a leading sensor-echo byte,
        then uint16 BE entries. A plain entry is a supported DPI; an entry
        with the 0xE000 bits set encodes (step) for a range that starts at
        the previous plain entry and ends at the following entry.
        This device: 200, (0xE000|50), 4000 -> 200..4000 step 50.
        """
        idx = self.feature_index(FEATURE_ADJUSTABLE_DPI)
        payload = self.request(idx, 1, bytes([sensor]))
        body = payload[1:]  # skip sensor echo
        words = [struct.unpack(">H", body[i:i + 2])[0]
                 for i in range(0, len(body) - 1, 2)]
        out = []
        i = 0
        while i < len(words):
            w = words[i]
            if w == 0:
                break
            if w & 0xE000 and out and i + 1 < len(words):
                step = w & 0x1FFF
                end = words[i + 1]
                start = out[-1]
                if step:
                    out.extend(range(start + step, end + 1, step))
                i += 2
            else:
                out.append(w)
                i += 1
        return out

    # ------------------------------------------------------- reprog / divert

    def get_cid_reporting(self, cid):
        """0x1B04 fn2: return the reporting flags byte for a CID."""
        idx = self.feature_index(FEATURE_REPROG_CONTROLS_V4)
        payload = self.request(idx, RC_FN_GET_CID_REPORTING,
                               struct.pack(">H", cid))
        got_cid = _u16be(payload, 0)
        if got_cid != cid:
            raise HIDPPError(0x02, f"getCidReporting echo cid 0x{got_cid:04x} != 0x{cid:04x}")
        return payload[2]

    def set_cid_reporting_raw(self, cid, byte):
        """0x1B04 fn3 with a raw command byte (see CID_SET_VALID notes).
        The device replies with an all-zero payload; confirm via GET."""
        idx = self.feature_index(FEATURE_REPROG_CONTROLS_V4)
        self.request(idx, RC_FN_SET_CID_REPORTING,
                     struct.pack(">HB", cid, byte))

    def set_diverted(self, cid, diverted):
        """Set or clear the diverted flag of a CID, leaving all other
        reporting bits untouched. Returns the flags byte read back."""
        cmd = CID_SET_VALID | (CID_FLAG_DIVERTED if diverted else 0)
        self.set_cid_reporting_raw(cid, cmd)
        return self.get_cid_reporting(cid)

    def get_control_count(self):
        idx = self.feature_index(FEATURE_REPROG_CONTROLS_V4)
        return self.request(idx, RC_FN_GET_COUNT)[0]
