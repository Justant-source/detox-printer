#!/usr/bin/env python3
"""PLAN-02 V2: 검증된 인쇄 바이트(captures/sent/0002.bin, USB로 인쇄 확인됨)를
L2CAP(HCRP, PSM 4107)로 M832에 재생해 BT 경로로도 같은 바이트가 그대로 먹히는지
확인한다.

이 실험 이전까지 M832의 BT 프로토콜은 [추정]이었다(Haru-Paper init_plan.md는
"같은 계열은 Classic SPP(RFCOMM)"라고 적어뒀음). 2026-09-17 SDP 조회로
M832는 SPP가 아니라 HCRP(L2CAP PSM 4107)를 광고한다는 게 [확인됨]으로
바뀌었다(findings.md 참고). HCRP가 세션 핸드셰이크 없이 원시 바이트를 그대로
받는지는 아직 모른다 — 그게 이 스크립트가 답하려는 것이다.

CLAUDE.md 금지 5: 용지가 장착되지 않은 상태에서는 래스터(인쇄) 명령을 보내지 않는다.
이 스크립트는 --confirm-paper-loaded 플래그 없이는 소켓을 열지도 않는다.

05_replay.py(USB)와 다른 점: 이 스크립트는 Claude Code 세션이 SSH를 통해
비대화식으로 실행한다(TTY 없음) — 05_replay.py의 "전송 직전 Enter 대기" 2차
안전장치는 non-TTY에서 input()이 즉시 EOFError가 되므로 여기서는 성립하지 않는다.
대신 사람의 확인은 이 스크립트를 실행하기 *전에* 대화로 받았다(용지 장착을
육안으로 확인했다는 명시적 답변, 2026-09-17) — --confirm-paper-loaded 플래그가
그 확인을 대신 표현하고, 이 사실을 findings.md에도 함께 기록한다.

CLAUDE.md 금지 3: 프린터에 보낸 바이트는 예외 없이 captures/sent/NNNN.bin으로 저장한다.
"""
import argparse
import pathlib
import socket
import sys

# 2026-09-17 SDP 조회 실측값(findings.md): "HCR Print"(0x1126), L2CAP, PSM 4107.
MAC = "C5:0D:F7:B7:B2:A1"  # 작업지시서 v1.2 기기 대장 1호기와 일치(findings.md에서 대조 확인)
PSM = 4107
# L2CAP Basic 모드 최소 MTU(스펙상 절대 하한). 이 아래로는 더 못 줄인다.
MIN_CHUNK = 48

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "captures" / "sent" / "0002.bin"
SENT_DIR = ROOT / "captures" / "sent"


def parse_args():
    p = argparse.ArgumentParser(
        description="V2: 검증된 인쇄 바이트를 L2CAP(HCRP PSM 4107)로 M832에 재생한다."
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
    p.add_argument("--psm", type=int, default=PSM)
    p.add_argument(
        "--chunk-size",
        type=int,
        default=672,
        # 고전 L2CAP Basic 모드 기본 MTU. 실측으로 조정(연결 후 협상된 MTU는 미확인).
        help="시작 청크 크기(바이트). send 실패 시 MIN_CHUNK까지 절반씩 줄여 재시도.",
    )
    p.add_argument("--connect-timeout-s", type=float, default=10.0)
    p.add_argument("--write-timeout-s", type=float, default=15.0)
    return p.parse_args()


def next_sent_path(sent_dir: pathlib.Path) -> pathlib.Path:
    """captures/sent/ 안에서 다음으로 쓸 수 있는 NNNN.bin 경로. 05_replay.py와 동일 로직."""
    sent_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        int(f.stem) for f in sent_dir.glob("*.bin") if f.stem.isdigit() and len(f.stem) == 4
    ]
    n = (max(existing) + 1) if existing else 1
    return sent_dir / f"{n:04d}.bin"


def send_chunked(sock: socket.socket, data: bytes, chunk_size: int) -> int:
    """SOCK_SEQPACKET L2CAP 소켓으로 data를 청크(SDU) 단위 전송한다.

    send()가 실패하면(OSError, EMSGSIZE 포함) 같은 offset에서 청크 크기를 절반으로
    줄여 재시도한다. MIN_CHUNK에서도 실패하면 예외를 그대로 올린다
    (CLAUDE.md 코드 규칙: 예외를 삼키지 않는다).
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
        if n != len(chunk):
            print(f"[WARN] 부분 전송: 요청 {len(chunk)}바이트 중 {n}바이트만 전송됨", file=sys.stderr)
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
    print(f"대상: {args.mac} PSM {args.psm} (L2CAP, HCRP — 2026-09-17 SDP 조회 확인)")
    print()

    if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_L2CAP"):
        print("[ERROR] 이 파이썬 빌드는 AF_BLUETOOTH/BTPROTO_L2CAP을 지원하지 않는다.", file=sys.stderr)
        sys.exit(1)

    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    sock.settimeout(args.connect_timeout_s)
    try:
        sock.connect((args.mac, args.psm))
    except OSError as e:
        print(f"[ERROR] L2CAP connect 실패: {e}", file=sys.stderr)
        sock.close()
        sys.exit(1)
    print("L2CAP 연결 성공")

    try:
        # CLAUDE.md 금지 3: 보낸 바이트는 예외 없이 저장한다.
        # 전송 시도 직전에, 보내려는 정확한 바이트를 먼저 디스크에 남긴다
        # (전송이 중간에 실패해도 "무엇을 보내려 했는지"는 재현 가능해야 한다).
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

        # 응답 시도. 무응답/타임아웃은 스크립트 실패로 취급하지 않되,
        # CLAUDE.md 금지 4에 따라 무반응이면 무반응이라고 명확히 남긴다.
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
