#!/usr/bin/env python3
"""H4(용지 감지 가능성 조사) — RFCOMM(SPP 채널 1)로 findpaper(1F 11 11) 조회 명령만
반복 전송해 응답이 고정값인지, 매번 재현되는지 확인한다.

이것은 **상태 조회**이지 래스터(인쇄) 명령이 아니다. CLAUDE.md 절대금지 5("용지가 장착되지
않은 상태에서는 래스터 명령을 보내지 않는다")는 GS v 0(1D 76 30) 같은 비트맵 명령에 적용되는
규칙이고, findpaper(1F 11 11)는 findings.md에 이미 여러 번 기록된 조회성 명령이다. 이 스크립트는
비트맵 명령을 만들지도, 전송하지도 않는다 — --confirm-paper-loaded 플래그가 없다.

목적: findings.md "V2 — RFCOMM… 전송 성공"에 기록된 11바이트 응답
(`1a 3e 00 00 1a 3b 04 19 00 05 00`)이 매번 동일한지, findpaper 단독 조회에서도 나오는지
확인한다. **주의**: 이 스크립트만으로는 "용지 있음/없음을 구분할 수 있는가"(H4의 진짜 질문)에
답할 수 없다 — 지금 프린터의 실제 용지 상태를 아무도 확인/조작하지 않았기 때문이다. 사람이
프린터 앞에서 용지를 뺐다 끼웠다 하며 같은 스크립트를 다시 돌려 응답을 비교해야 최종 판정이
나온다.

CLAUDE.md 절대금지 3: 보낸 바이트는 예외 없이 captures/sent/NNNN.bin으로 저장한다.
"""
import argparse
import pathlib
import socket
import sys
import time

# 2026-09-17 findings.md 실측값: SPP(JL_SPP, 0x1101), RFCOMM 채널 1.
MAC = "C5:0D:F7:B7:B2:A1"  # 기기 대장 1호기
RFCOMM_CHANNEL = 1
FINDPAPER = bytes([0x1F, 0x11, 0x11])  # 작업 종료 시 질의 명령. 비트맵 명령 아님

ROOT = pathlib.Path(__file__).resolve().parent.parent
SENT_DIR = ROOT / "captures" / "sent"


def parse_args():
    p = argparse.ArgumentParser(
        description="H4: findpaper(1F 11 11) 조회를 반복 전송해 응답 재현성을 확인한다."
    )
    p.add_argument("--mac", default=MAC)
    p.add_argument("--channel", type=int, default=RFCOMM_CHANNEL)
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--interval-s", type=float, default=1.0)
    p.add_argument("--connect-timeout-s", type=float, default=10.0)
    p.add_argument("--read-timeout-s", type=float, default=3.0)
    return p.parse_args()


def next_sent_path(sent_dir: pathlib.Path) -> pathlib.Path:
    sent_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        int(f.stem) for f in sent_dir.glob("*.bin") if f.stem.isdigit() and len(f.stem) == 4
    ]
    n = (max(existing) + 1) if existing else 1
    return sent_dir / f"{n:04d}.bin"


def main():
    args = parse_args()

    if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_RFCOMM"):
        print("[ERROR] 이 파이썬 빌드는 AF_BLUETOOTH/BTPROTO_RFCOMM을 지원하지 않는다.", file=sys.stderr)
        sys.exit(1)

    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(args.connect_timeout_s)
    try:
        sock.connect((args.mac, args.channel))
    except OSError as e:
        print(f"[ERROR] RFCOMM connect 실패 — 프린터가 꺼져 있거나 범위 밖일 수 있음: {e}", file=sys.stderr)
        sock.close()
        sys.exit(1)
    print(f"RFCOMM 연결 성공 ({args.mac} channel {args.channel})")

    responses = []
    try:
        for i in range(args.repeat):
            # 절대금지 3: 보낸 바이트는 예외 없이 저장한다. 매 반복 전송 직전에 남긴다.
            sent_path = next_sent_path(SENT_DIR)
            sent_path.write_bytes(FINDPAPER)

            try:
                sock.settimeout(args.connect_timeout_s)
                sock.send(FINDPAPER)
            except OSError as e:
                print(f"[ERROR] 전송 실패(반복 {i+1}/{args.repeat}): {e}", file=sys.stderr)
                break

            sock.settimeout(args.read_timeout_s)
            try:
                resp = sock.recv(64)
                resp_hex = resp.hex(" ") if resp else "(0바이트)"
            except OSError as e:
                resp = b""
                resp_hex = f"(무응답/타임아웃: {e})"

            print(f"[{i+1}/{args.repeat}] 보냄={FINDPAPER.hex(' ')} → 응답={resp_hex}")
            responses.append(resp)
            if i < args.repeat - 1:
                time.sleep(args.interval_s)
    finally:
        sock.close()

    print()
    unique = {r for r in responses}
    if len(unique) <= 1 and responses:
        print(f"결론(스크립트 판단, 최종 판정 아님): {len(responses)}회 모두 응답 동일 — 고정값일 가능성")
    elif len(unique) > 1:
        print(f"결론(스크립트 판단, 최종 판정 아님): 응답이 {len(unique)}가지로 달랐음 — 상태 반영 가능성, 원인 불명")
    else:
        print("응답을 하나도 받지 못함")


if __name__ == "__main__":
    main()
