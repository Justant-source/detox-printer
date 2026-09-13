#!/usr/bin/env python3
"""PLAN-01 E-1: C단계 필터 캡처(captures/filter/t3.bin)를 pyusb로 실제 M832에 재생한다.

CLAUDE.md 금지 5: 용지가 장착되지 않은 상태에서는 래스터(인쇄) 명령을 보내지 않는다.
헤드가 상한다. 이 스크립트는 다음 두 안전장치를 모두 통과하기 전에는 USB 장치를
열지도, claim하지도, write하지도 않는다.

  1. --confirm-paper-loaded 플래그 없이 실행 → 안내 메시지만 찍고 즉시 종료.
  2. 플래그가 있어도, 전송할 바이트(크기/앞뒤 16바이트)를 보여준 뒤
     사람이 Enter를 눌러야만 실제 전송으로 넘어간다 (PLAN-01 E-1: "전송 전 용지 확인 Enter 대기").

CLAUDE.md 금지 3: 프린터에 보낸 바이트는 예외 없이 captures/sent/NNNN.bin으로 저장한다.
"""
import argparse
import pathlib
import sys

import usb.core
import usb.util

# 1단계 확인값 (m832/docs/device-descriptor.md): VID:PID 0483:5740,
# interface 0 = bInterfaceClass 0x07 (Printer), BULK OUT 0x02 / BULK IN 0x81,
# 두 엔드포인트 모두 wMaxPacketSize=64.
VID, PID = 0x0483, 0x5740
INTERFACE = 0
EP_OUT = 0x02
EP_IN = 0x81
MIN_CHUNK = 64  # wMaxPacketSize 하한. device-descriptor.md. 이 아래로는 더 못 줄인다.

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "captures" / "filter" / "t3.bin"
SENT_DIR = ROOT / "captures" / "sent"


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "PLAN-01 E-1: C단계 필터 캡처(t3.bin)를 pyusb 벌크 전송으로 실제 M832에 재생한다. "
            "--confirm-paper-loaded 없이는 어떤 USB 동작도 하지 않는다."
        )
    )
    p.add_argument(
        "--confirm-paper-loaded",
        action="store_true",
        help=(
            "용지가 실제로 프린터에 물려 있음을 육안으로 확인했다는 명시적 플래그. "
            "이 플래그가 없으면 USB 장치를 열지 않고 즉시 종료한다 (CLAUDE.md 금지 5)."
        ),
    )
    p.add_argument(
        "--input",
        type=pathlib.Path,
        default=DEFAULT_INPUT,
        help=f"재생할 캡처 파일 (기본값: {DEFAULT_INPUT})",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=4096,
        # PLAN-01 E-1: "청크는 4096바이트에서 시작해 wMaxPacketSize와 실측으로 조정한다"
        help="시작 청크 크기(바이트). write 실패/타임아웃 시 MIN_CHUNK까지 자동으로 절반씩 줄인다.",
    )
    p.add_argument(
        "--write-timeout-ms",
        type=int,
        default=5000,
        help="BULK OUT write 1회당 타임아웃(ms). 무한 대기 금지 (CLAUDE.md 코드 규칙).",
    )
    p.add_argument(
        "--read-timeout-ms",
        type=int,
        default=2000,
        help="전송 후 BULK IN 응답을 기다리는 타임아웃(ms).",
    )
    return p.parse_args()


def next_sent_path(sent_dir: pathlib.Path) -> pathlib.Path:
    """captures/sent/ 안에서 다음으로 쓸 수 있는 NNNN.bin 경로를 찾는다. 비어 있으면 0001부터."""
    sent_dir.mkdir(parents=True, exist_ok=True)
    existing = []
    for f in sent_dir.glob("*.bin"):
        if f.stem.isdigit() and len(f.stem) == 4:
            existing.append(int(f.stem))
    n = (max(existing) + 1) if existing else 1
    return sent_dir / f"{n:04d}.bin"


def send_chunked(dev: "usb.core.Device", data: bytes, chunk_size: int, timeout_ms: int) -> int:
    """BULK OUT(EP_OUT)으로 data를 청크 단위 전송한다.

    write가 실패하면(USBError, 타임아웃 포함) 같은 offset에서 청크 크기를 절반으로
    줄여 재시도한다. MIN_CHUNK에서도 실패하면 예외를 그대로 올린다(CLAUDE.md 코드 규칙:
    예외를 삼키지 않는다).
    """
    offset = 0
    total = len(data)
    current = chunk_size
    sent_total = 0
    while offset < total:
        chunk = data[offset : offset + current]
        try:
            written = dev.write(EP_OUT, chunk, timeout=timeout_ms)
        except usb.core.USBError as e:
            if current > MIN_CHUNK:
                new_current = max(MIN_CHUNK, current // 2)
                print(
                    f"[WARN] write 실패 (offset={offset}, chunk={current}bytes): {e} "
                    f"-> 청크 크기를 {new_current}바이트로 줄이고 같은 offset에서 재시도",
                    file=sys.stderr,
                )
                current = new_current
                continue
            print(
                f"[ERROR] write 실패, 최소 청크({MIN_CHUNK}바이트)에서도 실패: {e}",
                file=sys.stderr,
            )
            raise
        if written != len(chunk):
            print(
                f"[WARN] 부분 전송: 요청 {len(chunk)}바이트 중 {written}바이트만 전송됨",
                file=sys.stderr,
            )
        offset += written
        sent_total += written
        print(f"  전송 진행: {offset}/{total} bytes", end="\r", file=sys.stderr)
    print(file=sys.stderr)
    return sent_total


def main():
    args = parse_args()

    # --- 안전장치 1: 플래그 없으면 USB 근처도 안 간다 ---
    if not args.confirm_paper_loaded:
        print(
            "거부: --confirm-paper-loaded 플래그 없이는 실행하지 않는다.\n"
            "\n"
            "CLAUDE.md 절대 금지 5: 용지가 장착되지 않은 상태에서는 래스터(인쇄) 명령을\n"
            "보내지 않는다. 헤드가 상한다.\n"
            "\n"
            "프린터에 실제로 용지가 물려 있고 급지구에 정상적으로 걸려 있는지 육안으로\n"
            "직접 확인한 뒤, 다시 --confirm-paper-loaded 플래그를 주고 실행할 것.\n"
            "(이 메시지만 출력했고, USB 장치는 열지 않았다.)",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.input.exists():
        print(f"[ERROR] 입력 파일이 없음: {args.input}", file=sys.stderr)
        sys.exit(1)
    data = args.input.read_bytes()
    if len(data) == 0:
        print(f"[ERROR] 입력 파일이 비어 있음: {args.input}", file=sys.stderr)
        sys.exit(1)

    head_hex = data[:16].hex(" ")
    tail_hex = data[-16:].hex(" ") if len(data) >= 16 else data.hex(" ")

    # --- 안전장치 2: 전송 내용을 보여주고 사람이 Enter를 눌러야 진행 ---
    print(f"입력 파일: {args.input}")
    print(f"전송할 바이트 수: {len(data)}")
    print(f"앞 16바이트: {head_hex}")
    print(f"뒤 16바이트: {tail_hex}")
    print()
    print("*** 지금 프린터에 용지가 실제로 장착돼 있는지 다시 한번 육안으로 확인하라. ***")
    try:
        input("확인했으면 Enter를 눌러 전송을 계속한다 (Ctrl+C로 중단): ")
    except (EOFError, KeyboardInterrupt):
        print("\n중단됨. 아무것도 전송하지 않았다. USB 장치는 열지 않았다.", file=sys.stderr)
        sys.exit(1)

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print(f"[ERROR] 장치를 찾을 수 없음 (VID:PID {VID:04x}:{PID:04x})", file=sys.stderr)
        sys.exit(1)

    kernel_driver_was_active = False
    interface_claimed = False

    try:
        try:
            kernel_driver_was_active = dev.is_kernel_driver_active(INTERFACE)
        except (usb.core.USBError, NotImplementedError) as e:
            print(f"[ERROR] is_kernel_driver_active 확인 실패: {e}", file=sys.stderr)
            sys.exit(1)

        if kernel_driver_was_active:
            try:
                dev.detach_kernel_driver(INTERFACE)
                print(f"커널 드라이버 detach 완료 (interface {INTERFACE})")
            except usb.core.USBError as e:
                print(f"[ERROR] detach_kernel_driver 실패: {e}", file=sys.stderr)
                sys.exit(1)

        try:
            dev.set_configuration()
        except usb.core.USBError as e:
            print(f"[ERROR] set_configuration 실패: {e}", file=sys.stderr)
            sys.exit(1)

        try:
            usb.util.claim_interface(dev, INTERFACE)
            interface_claimed = True
            print(f"interface {INTERFACE} claim 완료")
        except usb.core.USBError as e:
            print(f"[ERROR] claim_interface 실패: {e}", file=sys.stderr)
            sys.exit(1)

        # CLAUDE.md 금지 3: 보낸 바이트는 예외 없이 저장한다.
        # 실제 전송을 시도하기 직전에, 전송하려는 정확한 바이트를 먼저 디스크에 남긴다
        # (이후 write가 중간에 실패해도 "무엇을 보내려 했는지"는 재현 가능해야 한다).
        sent_path = next_sent_path(SENT_DIR)
        sent_path.write_bytes(data)
        print(f"전송 바이트 저장 완료: {sent_path} ({len(data)} bytes)")

        try:
            sent_total = send_chunked(dev, data, args.chunk_size, args.write_timeout_ms)
            print(f"전송 완료: {sent_total}/{len(data)} bytes")
        except usb.core.USBError as e:
            print(f"[ERROR] 전송 실패: {e}", file=sys.stderr)
            sys.exit(1)

        # BULK IN 응답 시도. 무응답/타임아웃은 스크립트 실패로 취급하지 않되,
        # CLAUDE.md 금지 4에 따라 무반응이면 무반응이라고 명확히 남긴다.
        try:
            resp = dev.read(EP_IN, 64, timeout=args.read_timeout_ms)
            resp_bytes = bytes(resp)
            print(f"BULK IN 응답 수신: {len(resp_bytes)} bytes: {resp_bytes.hex(' ')}")
        except usb.core.USBError as e:
            print(f"BULK IN 무응답 (timeout 또는 오류, 실패로 취급하지 않음): {e}")

    finally:
        if interface_claimed:
            try:
                usb.util.release_interface(dev, INTERFACE)
                print(f"interface {INTERFACE} release 완료")
            except usb.core.USBError as e:
                print(f"[WARN] release_interface 실패: {e}", file=sys.stderr)
        if kernel_driver_was_active:
            try:
                dev.attach_kernel_driver(INTERFACE)
                print(f"커널 드라이버 재부착 완료 (interface {INTERFACE})")
            except usb.core.USBError as e:
                print(f"[WARN] attach_kernel_driver 실패: {e}", file=sys.stderr)
        usb.util.dispose_resources(dev)


if __name__ == "__main__":
    main()
