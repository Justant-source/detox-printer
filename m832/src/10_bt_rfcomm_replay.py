#!/usr/bin/env python3
"""PLAN-02 V2 (2차): 검증된 인쇄 바이트(captures/sent/0002.bin, USB로 인쇄 확인됨)를
RFCOMM(SPP, 채널 1)로 M832에 재생한다.

09_bt_l2cap_replay.py(HCRP, L2CAP PSM 4107)는 페어링 전 EPERM으로 거부됐다. 페어링 후
SDP 재조회에서 SPP(0x1101) 서비스가 RFCOMM 채널 1로 확인됐다(findings.md, 2026-09-17).
SPP는 RFCOMM 기반 단순 시리얼 파이프라 USB bulk-out과 의미상 가장 가깝다 — 이 스크립트가
그 가설을 확인한다.

CLAUDE.md 금지 5: 용지가 장착되지 않은 상태에서는 래스터(인쇄) 명령을 보내지 않는다.
--confirm-paper-loaded 없이는 소켓을 열지 않는다.

09번 스크립트와 동일한 이유로 비대화식 실행(TTY 없음, SSH를 통한 자동화 컨텍스트) —
사람의 용지 확인은 스크립트 실행 전에 대화로 받았다(2026-09-17). --confirm-paper-loaded가
그 확인을 대신 표현한다.

CLAUDE.md 금지 3: 프린터에 보낸 바이트는 예외 없이 captures/sent/NNNN.bin으로 저장한다.
"""
import argparse
import pathlib
import socket
import sys

# 2026-09-17 페어링 후 sdptool search SP 실측값(findings.md): "JL_SPP", RFCOMM 채널 1.
MAC = "C5:0D:F7:B7:B2:A1"  # 작업지시서 v1.2 기기 대장 1호기와 일치
RFCOMM_CHANNEL = 1
MIN_CHUNK = 64  # RFCOMM은 논리적으로 스트림이라 USB와 같은 하한을 그대로 씀(05_replay.py MIN_CHUNK와 동일 근거)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "captures" / "sent" / "0002.bin"
SENT_DIR = ROOT / "captures" / "sent"


def parse_args():
    p = argparse.ArgumentParser(
        description="V2: 검증된 인쇄 바이트를 RFCOMM(SPP 채널 1)로 M832에 재생한다."
    )
    p.add_argument(
        "--confirm-paper-loaded",
        action="store_true",
        help=(
            "용지가 실제로 프린터에 물려 있음을 육안으로 확인했다는 명시적 플래그. "
            "이 플래그가 없으면 소켓을 열지 않고 즉시 종료한다 (CLAUDE.md 금지 5)."
        ),
    )
    p.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    p.add_argument("--mac", default=MAC)
    p.add_argument("--channel", type=int, default=RFCOMM_CHANNEL)
    p.add_argument("--chunk-size", type=int, default=4096)  # 05_replay.py(USB)와 동일 시작값
    p.add_argument("--connect-timeout-s", type=float, default=10.0)
    p.add_argument("--write-timeout-s", type=float, default=20.0)
    return p.parse_args()


def next_sent_path(sent_dir: pathlib.Path) -> pathlib.Path:
    sent_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        int(f.stem) for f in sent_dir.glob("*.bin") if f.stem.isdigit() and len(f.stem) == 4
    ]
    n = (max(existing) + 1) if existing else 1
    return sent_dir / f"{n:04d}.bin"


def send_chunked(sock: socket.socket, data: bytes, chunk_size: int) -> int:
    """RFCOMM(SOCK_STREAM)은 진짜 스트림이라 05_replay.py의 send_chunked와 사실상 동일하다.
    send() 실패 시 청크를 절반으로 줄여 같은 offset에서 재시도, MIN_CHUNK에서도 실패하면 예외를 올린다.
    """
    offset = 0
    total = len(data)
    current = chunk_size
    sent_total = 0
    while offset < total:
        chunk = data[offset : offset + current]
        try:
            n = sock.send(chunk)
        except OSError as e:
            if current > MIN_CHUNK:
                new_current = max(MIN_CHUNK, current // 2)
                print(
                    f"[WARN] send 실패 (offset={offset}, chunk={current}bytes): {e} "
                    f"-> 청크 크기를 {new_current}바이트로 줄이고 같은 offset에서 재시도",
                    file=sys.stderr,
                )
                current = new_current
                continue
            print(
                f"[ERROR] send 실패, 최소 청크({MIN_CHUNK}바이트)에서도 실패: {e}",
                file=sys.stderr,
            )
            raise
        offset += n
        sent_total += n
        print(f"  전송 진행: {offset}/{total} bytes", end="\r", file=sys.stderr)
    print(file=sys.stderr)
    return sent_total


def main():
    args = parse_args()

    if not args.confirm_paper_loaded:
        print(
            "거부: --confirm-paper-loaded 플래그 없이는 실행하지 않는다.\n"
            "\n"
            "CLAUDE.md 절대 금지 5: 용지가 장착되지 않은 상태에서는 래스터(인쇄) 명령을\n"
            "보내지 않는다. 헤드가 상한다.\n"
            "\n"
            "프린터에 실제로 용지가 물려 있는지 육안으로 직접 확인한 뒤,\n"
            "다시 --confirm-paper-loaded 플래그를 주고 실행할 것.\n"
            "(이 메시지만 출력했고, 소켓은 열지 않았다.)",
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

    print(f"입력 파일: {args.input}")
    print(f"전송할 바이트 수: {len(data)}")
    print(f"앞 16바이트: {data[:16].hex(' ')}")
    print(f"뒤 16바이트: {data[-16:].hex(' ') if len(data) >= 16 else data.hex(' ')}")
    print(f"대상: {args.mac} RFCOMM channel {args.channel} (SPP — 2026-09-17 SDP search 확인)")
    print()

    if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_RFCOMM"):
        print("[ERROR] 이 파이썬 빌드는 AF_BLUETOOTH/BTPROTO_RFCOMM을 지원하지 않는다.", file=sys.stderr)
        sys.exit(1)

    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(args.connect_timeout_s)
    try:
        sock.connect((args.mac, args.channel))
    except OSError as e:
        print(f"[ERROR] RFCOMM connect 실패: {e}", file=sys.stderr)
        sock.close()
        sys.exit(1)
    print("RFCOMM 연결 성공")

    try:
        # CLAUDE.md 금지 3: 보낸 바이트는 예외 없이 저장한다. 전송 시도 직전에 남긴다.
        sent_path = next_sent_path(SENT_DIR)
        sent_path.write_bytes(data)
        print(f"전송 바이트 저장 완료: {sent_path} ({len(data)} bytes)")

        sock.settimeout(args.write_timeout_s)
        try:
            sent_total = send_chunked(sock, data, args.chunk_size)
            print(f"전송 완료: {sent_total}/{len(data)} bytes")
        except OSError as e:
            print(f"[ERROR] 전송 실패: {e}", file=sys.stderr)
            sys.exit(1)

        sock.settimeout(3.0)
        try:
            resp = sock.recv(64)
            if resp:
                print(f"응답 수신: {len(resp)} bytes: {resp.hex(' ')}")
            else:
                print("응답 0바이트 — 상대가 연결을 닫았을 수 있음")
        except OSError as e:
            print(f"무응답 (timeout 또는 오류, 실패로 취급하지 않음): {e}")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
