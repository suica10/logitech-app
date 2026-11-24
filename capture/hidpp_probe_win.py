# HID++ probe via pywinusb — MX Master 2S on Unifying receiver (desktop, Python 3.12)
# Enumerates VID_046D HID collections, opens each, tries HID++ long-report traffic,
# prints every reply verbatim (hex) so the feature table can be read from raw bytes.
import sys, time
from pywinusb import hid

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

def main():
    devices = hid.HidDeviceFilter(vendor_id=VID).get_devices()
    print(f"found {len(devices)} HID collections for VID_046D")
    for i, d in enumerate(devices):
        print(f"[{i}] path={d.device_path}")
        print(f"     vendor={d.vendor_name} product={d.product_name} pid=0x{d.product_id:04x}")

    replies_log = []

    for i, d in enumerate(devices):
        # We only try collections whose path hints mi_02 (vendor) - but try all briefly is noisy;
        # instead: open each, look at output reports; HID++ lives where report 0x11 exists.
        try:
            d.open()
        except Exception as e:
            print(f"[{i}] open failed: {e}")
            continue
        try:
            out_reports = d.find_output_reports()
            in_reports = d.find_input_reports()
            out_ids = sorted({r.report_id for r in out_reports})
            in_ids = sorted({r.report_id for r in in_reports})
            print(f"[{i}] opened. out_report_ids={out_ids} in_report_ids={in_ids}")
            if 0x11 not in out_ids and 0x10 not in out_ids:
                d.close()
                continue

            got = []
            def handler(data):
                got.append(bytes(data))
            d.set_raw_data_handler(handler)
            time.sleep(0.2)

            def send_long(payload19):
                # HID++ long report = 20 bytes total INCLUDING report id 0x11:
                # [0x11, dev, feature, fn|swid, params x16]
                for r in out_reports:
                    if r.report_id == 0x11:
                        raw = [0x11] + list(payload19)
                        assert len(raw) == 20, len(raw)
                        r.set_raw_data(raw)
                        r.send()
                        return True
                return False

            def long_msg(dev, feature, function, swid, params):
                b = bytearray(19)
                b[0] = dev
                b[1] = feature
                b[2] = (function << 4) | swid
                for j, p in enumerate(params):
                    b[3 + j] = p
                return bytes(b)

            # 1) ping-ish: root feature(0) function 1, random payload, for receiver(0xFF) and slots 1..6
            for dev in (0xFF, 1, 2, 3, 4, 5, 6):
                got.clear()
                if not send_long(long_msg(dev, 0x00, 0x01, 0x0A, [0x5A, 0xA5, 0x3C])):
                    print(f"[{i}] no 0x11 output report")
                    break
                time.sleep(0.6)
                for g in got:
                    print(f"[{i}] dev={dev:#04x} ping -> {hexs(g)}")
                    replies_log.append(g)
            # 2) root getFeature for a few known features on slots that answered is decided later;
            #    here: try slot 1..6 getFeature(0x0005 device name) and (0x0001), (0x2201), (0x1B04)
            for dev in (1, 2, 3, 4, 5, 6):
                for feat in (0x0005, 0x0001, 0x2201, 0x1B04, 0x2205, 0x2111):
                    got.clear()
                    send_long(long_msg(dev, 0x00, 0x00, 0x0A, [feat >> 8, feat & 0xFF, 0x00]))
                    time.sleep(0.35)
                    for g in got:
                        print(f"[{i}] dev={dev} getFeature(0x{feat:04x}) -> {hexs(g)}")
        except Exception as e:
            print(f"[{i}] probe error: {e}")
        finally:
            try:
                d.close()
            except Exception:
                pass
    print("probe done")

if __name__ == "__main__":
    main()
