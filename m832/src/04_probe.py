#!/usr/bin/env python3
"""PLAN-01 1단계: 장치 지문 뜨기. 아무것도 쓰지 않는다 — 읽기 전용.

VID:PID 0483:5740 (usbipd list / lsusb 확인값, m832/docs/findings.md 참고)의
디스크립터를 전부 읽어 m832/docs/device-descriptor.md에 저장한다.
"""
import pathlib
import sys

import usb.core
import usb.util

VID, PID = 0x0483, 0x5740
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "device-descriptor.md"


def main():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print(f"장치를 찾을 수 없음 (VID:PID {VID:04x}:{PID:04x})", file=sys.stderr)
        sys.exit(1)

    lines = ["# M832 장치 디스크립터 (1단계, 읽기 전용)", ""]

    def emit(s=""):
        lines.append(s)
        print(s)

    emit(f"idVendor: 0x{dev.idVendor:04x}")
    emit(f"idProduct: 0x{dev.idProduct:04x}")
    try:
        emit(f"iManufacturer: {usb.util.get_string(dev, dev.iManufacturer)!r}")
    except Exception as e:
        emit(f"iManufacturer: 읽기 실패 ({e})")
    try:
        emit(f"iProduct: {usb.util.get_string(dev, dev.iProduct)!r}")
    except Exception as e:
        emit(f"iProduct: 읽기 실패 ({e})")
    try:
        emit(f"iSerialNumber: {usb.util.get_string(dev, dev.iSerialNumber)!r}")
    except Exception as e:
        emit(f"iSerialNumber: 읽기 실패 ({e})")

    emit(f"\n컨피그레이션 개수: {dev.bNumConfigurations}")

    for cfg in dev:
        emit(f"\n## Configuration {cfg.bConfigurationValue}")
        for intf in cfg:
            emit(
                f"### Interface {intf.bInterfaceNumber} (alt {intf.bAlternateSetting}): "
                f"bInterfaceClass=0x{intf.bInterfaceClass:02x} "
                f"({'Printer' if intf.bInterfaceClass == 7 else ('Vendor' if intf.bInterfaceClass == 255 else '기타')}), "
                f"bInterfaceSubClass=0x{intf.bInterfaceSubClass:02x}, "
                f"bInterfaceProtocol=0x{intf.bInterfaceProtocol:02x}"
            )
            try:
                active = dev.is_kernel_driver_active(intf.bInterfaceNumber)
                emit(f"  is_kernel_driver_active: {active}")
            except Exception as e:
                emit(f"  is_kernel_driver_active: 확인 실패 ({e})")
            for ep in intf:
                dir_ = "IN" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
                ttype = usb.util.endpoint_type(ep.bmAttributes)
                ttype_name = {
                    usb.util.ENDPOINT_TYPE_CTRL: "CONTROL",
                    usb.util.ENDPOINT_TYPE_ISO: "ISOCHRONOUS",
                    usb.util.ENDPOINT_TYPE_BULK: "BULK",
                    usb.util.ENDPOINT_TYPE_INTR: "INTERRUPT",
                }.get(ttype, str(ttype))
                emit(
                    f"  - Endpoint 0x{ep.bEndpointAddress:02x} ({dir_}, {ttype_name}), "
                    f"wMaxPacketSize={ep.wMaxPacketSize}"
                )

    OUT.write_text("\n".join(lines) + "\n")
    print(f"\n저장 완료: {OUT}")


if __name__ == "__main__":
    main()
