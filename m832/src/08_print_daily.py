#!/usr/bin/env python3
"""PLAN-01 G단계: cron 자동 출력 PoC.

매일 messages/YYYY-MM-DD.txt 를 읽어 이미지로 렌더링하고, 래스터 전송 전에
findpaper(`1F 11 11`) 응답으로 용지 유무를 확인한 뒤에만 인쇄한다.

## crontab (Orange Pi / WSL 리눅스 쪽, PLAN-01 13절)

    0 7 * * * cd ~/Data/detox-printer/m832 && .venv/bin/python src/08_print_daily.py

## WSL 주의

WSL 인스턴스가 떠 있을 때만 위 cron이 동작한다. WSL이 꺼져 있으면 07시가 되어도
아무 일도 일어나지 않는다. Windows 작업 스케줄러에서 아래처럼 호출하는 편이 더
안전하다 (Orange Pi로 넘어가면 이 문제 자체가 없어진다):

    wsl.exe -d Ubuntu-24.04 -e bash -lc "cd ~/Data/detox-printer/m832 && .venv/bin/python src/08_print_daily.py"

## 중요 — 이 스크립트를 실행하기 전에

PLAN-01 13절(G단계) 명시 조건: "응답 형식이 E-1에서 확정되기 전에는 G단계를 시작하지
않는다." E-1(`src/05_replay.py`)은 아직 실제 프린터에 대해 실행되지 않았고, 따라서
`1F 11 11`(findpaper) 응답 중 어떤 바이트열이 "용지 있음"을 뜻하는지 **아직 모른다**.

그래서 이 스크립트는 정직하게 다음처럼 동작한다:
- 아래 `check_paper_present()`는 아직 아무 패턴도 "용지 있음"으로 인정하지 않는
  플레이스홀더다 (`EXPECTED_PAPER_PRESENT_PATTERNS`가 비어 있음).
- 즉 이 스크립트를 지금 당장 cron에 걸어도, findpaper 응답이 무엇이 오든
  "용지 없음"으로 간주하고 **절대 인쇄하지 않는다** (fail-safe).
- E-1을 실물 프린터로 돌려서 "용지 있음" 상태의 findpaper 응답 바이트를
  `docs/findings.md`에 [확인됨]으로 기록한 뒤, 그 값을
  `EXPECTED_PAPER_PRESENT_PATTERNS`에 채워 넣어야 실제로 인쇄가 시작된다.
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys
import traceback

from PIL import Image, ImageDraw, ImageFont

# --- 경로 ------------------------------------------------------------------

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent  # m832/
MESSAGES_DIR = PROJECT_ROOT / "messages"
LOGS_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOGS_DIR / "print.log"
CAPTURES_SENT_DIR = PROJECT_ROOT / "captures" / "sent"  # CLAUDE.md 금지 3: 보낸 바이트 전부 저장

DEFAULT_MESSAGE = "오늘도 좋은 하루 보내세요."
# 위 문구는 messages/YYYY-MM-DD.txt 가 없을 때 쓰는 대체 문구다.
# (구 PLAN.md 6단계 취지: 실패해도 매일 뭔가는 나와야 한다)

# --- USB 상수 (m832/docs/device-descriptor.md, 1단계 확인값) ---------------

VID, PID = 0x0483, 0x5740
EP_OUT = 0x02  # BULK OUT, wMaxPacketSize=64 (device-descriptor.md)
EP_IN = 0x81  # BULK IN, wMaxPacketSize=64 (device-descriptor.md)
USB_TIMEOUT_MS = 3000  # 임의값. E-1에서 실측 후 조정 필요 (CLAUDE.md 코드 규칙: 근거 주석)

FINDPAPER_CMD = bytes([0x1F, 0x11, 0x11])  # docs/protocol.md, docs/filter-source-map.md 11347-11363

# 래스터 헤더/푸터 (docs/protocol.md — C단계 필터 오프라인 실행으로 [확인됨]).
# 주의: 이건 "필터가 만든 바이트열"이 확인된 것이지, E-1(실제 USB 응답)이 확인된 것은
# 아니다. 아래 WIDTH_BYTES 등은 07_print_image.py(E-3)가 아직 없어서 여기서 최소
# 구현으로만 사용한다 — 07_print_image.py가 작성되면 이 블록은 그쪽 파이프라인을
# import해서 재사용하도록 정리해야 한다 (중복 로직 제거는 그때 한다).
MEDIA_TYPE_CMD = bytes([0x1F, 0x11, 0x0B])  # 연속용지
COMPRESSION_OFF_CMD = bytes([0x1F, 0x11, 0x35, 0x00])
WIDTH_BYTES = 288  # docs/findings.md·docs/protocol.md에서 [확인됨] (bCmdBMP xL/xH 실측, C단계)
WIDTH_DOTS = WIDTH_BYTES * 8  # 2304 dot


def log(message: str) -> None:
    """logs/print.log 에 타임스탬프를 붙여 한 줄 append한다. 실패를 조용히 넘기지 않는다."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {message}\n"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)
    # 사람이 터미널에서 돌릴 때도 보이도록 stderr에도 낸다.
    print(line, end="", file=sys.stderr)


def save_sent_bytes(data: bytes) -> pathlib.Path:
    """CLAUDE.md 금지 3: 프린터에 보낸 바이트는 예외 없이 captures/sent/에 .bin으로 저장한다."""
    CAPTURES_SENT_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(CAPTURES_SENT_DIR.glob("[0-9][0-9][0-9][0-9].bin"))
    next_idx = 0
    for p in existing:
        try:
            next_idx = max(next_idx, int(p.stem) + 1)
        except ValueError:
            continue
    out_path = CAPTURES_SENT_DIR / f"{next_idx:04d}.bin"
    out_path.write_bytes(data)
    return out_path


# --- 메시지 로딩 -------------------------------------------------------------


def load_today_message() -> tuple[str, str]:
    """오늘 날짜의 messages/YYYY-MM-DD.txt 를 읽는다. 없으면 기본 문구로 대체한다.

    반환: (본문 텍스트, 출처 설명) — 출처 설명은 로그에 남기기 위함이다.
    """
    today = datetime.date.today().isoformat()
    message_path = MESSAGES_DIR / f"{today}.txt"
    if message_path.is_file():
        text = message_path.read_text(encoding="utf-8").strip()
        if text:
            return text, f"messages/{today}.txt"
        # 파일은 있는데 내용이 비어있는 경우도 "없는 것"과 동일하게 기본 문구로 대체한다.
        return DEFAULT_MESSAGE, f"messages/{today}.txt 가 비어있어 기본 문구로 대체"
    return DEFAULT_MESSAGE, f"messages/{today}.txt 없음 → 기본 문구로 대체"


# --- 이미지 렌더링 ------------------------------------------------------------
# NOTE: m832/src/07_print_image.py (E-3, 그레이스케일→디더링→1bpp 패킹 파이프라인)가
# 아직 작성되지 않았다 (2026-09-13 기준 src/ 에는 01~04만 존재). 그래서 여기서는
# Pillow ImageDraw만 쓰는 최소 자체 구현을 둔다. 07_print_image.py가 생기면 이
# render_text_to_image()/pack_image_1bpp() 두 함수는 지우고 그쪽 파이프라인 함수를
# import해서 재사용하도록 정리(reconcile)해야 한다 — 지금 당장 두 파일에 같은 로직을
# 만들어 두지 않기 위해서다.


def render_text_to_image(text: str, width_dots: int = WIDTH_DOTS) -> Image.Image:
    """텍스트를 흑백(1bit) Pillow 이미지로 렌더링한다. 최소 구현."""
    font = ImageFont.load_default()
    padding = 20
    # 줄바꿈은 이미 텍스트에 있는 개행 기준으로만 처리한다 (자동 word-wrap은 07_print_image.py 몫).
    lines = text.splitlines() or [""]

    # 임시 캔버스로 각 줄 높이를 측정한다.
    tmp = Image.new("L", (10, 10), color=255)
    tmp_draw = ImageDraw.Draw(tmp)
    line_height = 0
    for line in lines:
        bbox = tmp_draw.textbbox((0, 0), line, font=font)
        line_height = max(line_height, bbox[3] - bbox[1])
    line_height = max(line_height, 12) + 6  # 줄 간격 여유

    height_dots = padding * 2 + line_height * len(lines)
    image = Image.new("L", (width_dots, height_dots), color=255)  # 흰 배경
    draw = ImageDraw.Draw(image)
    y = padding
    for line in lines:
        draw.text((padding, y), line, fill=0, font=font)  # 검정 글씨
        y += line_height

    return image.convert("1")  # 1bit로 변환 (팔레트 디더링은 07_print_image.py 몫)


def pack_image_1bpp_msb_first(image: Image.Image, width_bytes: int) -> bytes:
    """PIL '1' 모드 이미지를 MSB-first 1bpp, 1=검정으로 패킹한다 (docs/protocol.md 비트 극성)."""
    width_dots = width_bytes * 8
    if image.width != width_dots:
        # 폭을 확정 WIDTH_DOTS에 맞춘다 (레터박스: 왼쪽 정렬, 나머지는 흰색).
        canvas = Image.new("1", (width_dots, image.height), color=1)  # '1' 모드: 1=흰색(반전 전)
        canvas.paste(image, (0, 0))
        image = canvas

    pixels = image.load()
    out = bytearray(width_bytes * image.height)
    for y in range(image.height):
        row_offset = y * width_bytes
        for byte_x in range(width_bytes):
            b = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                # PIL '1' 모드: 0=검정, 255(=1로 로드됨)=흰색. 프로토콜은 1=검정이므로 반전.
                is_black = pixels[x, y] == 0
                if is_black:
                    b |= 0x80 >> bit
            out[row_offset + byte_x] = b
    return bytes(out)


def build_raster_command(bitmap: bytes, width_bytes: int, height_lines: int) -> bytes:
    """docs/protocol.md 순서: 미디어타입 → 압축Off → bCmdBMP → 비트맵 → findpaper(푸터)."""
    x = width_bytes
    y = height_lines
    bcmd_bmp = bytes([0x1D, 0x76, 0x30, 0x00, x & 0xFF, (x >> 8) & 0xFF, y & 0xFF, (y >> 8) & 0xFF])
    return MEDIA_TYPE_CMD + COMPRESSION_OFF_CMD + bcmd_bmp + bitmap + FINDPAPER_CMD


# --- 용지 확인 (findpaper) ---------------------------------------------------

# TODO [미확정]: E-1(src/05_replay.py)을 실제 프린터로 실행해서 "용지 있음" 상태의
# findpaper(`1F 11 11`) 응답 바이트를 docs/findings.md에 [확인됨]으로 기록한 뒤,
# 그 정확한 바이트열(들)을 아래 리스트에 채워 넣어야 한다. 지금은 E-1이 하드웨어에
# 대해 실행된 적이 없으므로 이 값은 그냥 모른다 — 추측으로 아무 패턴이나 넣고 "아마
# 맞겠지"로 넘어가면 안 된다 (CLAUDE.md 금지 2: 확인 안 된 걸 확인된 것처럼 취급 금지).
# 비어 있는 한, check_paper_present()는 무엇이 오든 False를 반환한다 (fail-safe:
# 모르면 "용지 없음"으로 간주하고 인쇄하지 않는다).
EXPECTED_PAPER_PRESENT_PATTERNS: list[bytes] = []  # E-1 완료 후 여기를 채울 것


def check_paper_present(response_bytes: bytes | None) -> bool:
    """findpaper(`1F 11 11`) 응답이 "용지 있음"을 뜻하는지 판정한다.

    미확정 상태 (EXPECTED_PAPER_PRESENT_PATTERNS 비어있음) 에서는 무엇이 오든
    False를 반환한다 — 모르는 응답을 "아마 용지 있음"으로 넘겨짚지 않는다.
    """
    if not EXPECTED_PAPER_PRESENT_PATTERNS:
        return False
    if response_bytes is None:
        return False
    return response_bytes in EXPECTED_PAPER_PRESENT_PATTERNS


def query_findpaper_over_usb() -> bytes | None:
    """실제 USB로 findpaper(`1F 11 11`)를 보내고 BULK IN 응답을 읽는다.

    CLAUDE.md 코드 규칙: 예외를 삼키지 않는다 — 여기서는 그대로 올린다(raise).
    호출부(main)에서 잡아서 로그로 남긴다.
    """
    import usb.core
    import usb.util

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise RuntimeError(f"장치를 찾을 수 없음 (VID:PID {VID:04x}:{PID:04x})")

    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    usb.util.claim_interface(dev, 0)
    try:
        sent_path = save_sent_bytes(FINDPAPER_CMD)
        dev.write(EP_OUT, FINDPAPER_CMD, timeout=USB_TIMEOUT_MS)
        log(f"findpaper 질의 전송 완료 ({sent_path})")
        try:
            resp = dev.read(EP_IN, 64, timeout=USB_TIMEOUT_MS)
            return bytes(resp)
        except usb.core.USBError as e:
            # 타임아웃 등 무응답도 흔한 케이스 — 예외를 삼키지 않고 None으로 변환해 올린다.
            log(f"findpaper 응답 읽기 실패 (무응답으로 처리): {e}")
            return None
    finally:
        usb.util.release_interface(dev, 0)
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass


def send_raster_over_usb(command_bytes: bytes) -> None:
    """확정된 래스터 명령 전체를 BULK OUT으로 전송한다. 보낸 바이트는 저장한다."""
    import usb.core
    import usb.util

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise RuntimeError(f"장치를 찾을 수 없음 (VID:PID {VID:04x}:{PID:04x})")

    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    usb.util.claim_interface(dev, 0)
    try:
        sent_path = save_sent_bytes(command_bytes)
        log(f"래스터 전송 시작 ({len(command_bytes)} bytes, {sent_path})")
        # 청크 크기는 E-1/E-3에서 wMaxPacketSize·실측으로 확정 필요 (지금은 4096 임시값).
        chunk_size = 4096  # PLAN-01 E-1 절: "청크는 4096바이트에서 시작"
        for offset in range(0, len(command_bytes), chunk_size):
            dev.write(EP_OUT, command_bytes[offset:offset + chunk_size], timeout=USB_TIMEOUT_MS)
    finally:
        usb.util.release_interface(dev, 0)
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass


# --- 메인 --------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simulate-no-response",
        action="store_true",
        help=(
            "테스트 전용. 실제 USB 장치에 전혀 접근하지 않고, findpaper 질의가 "
            "무응답으로 온 것처럼 취급한다. 하드웨어를 건드리지 않고 "
            "'용지 미확인 → 인쇄 안 함 → 로그' 경로를 검증할 때 쓴다."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    text, message_source = load_today_message()

    try:
        image = render_text_to_image(text)
    except Exception:
        log(f"실패: 이미지 렌더링 중 예외 발생 (메시지 소스={message_source})\n{traceback.format_exc()}")
        return 1

    if args.simulate_no_response:
        response = None
        query_note = "시뮬레이션(--simulate-no-response): 실제 USB에 접근하지 않고 무응답으로 간주"
    else:
        try:
            response = query_findpaper_over_usb()
            query_note = f"findpaper 응답={response!r}" if response is not None else "findpaper 무응답"
        except Exception:
            response = None
            query_note = f"findpaper 질의 중 예외 발생 (무응답으로 처리)\n{traceback.format_exc()}"

    if response is None:
        log(
            "실패: 용지 확인 불가 → 인쇄하지 않음 "
            f"(메시지 소스={message_source}; {query_note})"
        )
        return 1

    paper_present = check_paper_present(response)
    if not paper_present:
        log(
            "실패: 용지 없음(또는 판정 기준 미확정) → 인쇄하지 않음 "
            f"(메시지 소스={message_source}; {query_note}; "
            f"check_paper_present 확정 패턴 개수={len(EXPECTED_PAPER_PRESENT_PATTERNS)})"
        )
        return 1

    # 여기부터는 EXPECTED_PAPER_PRESENT_PATTERNS가 채워지고 실제로 "용지 있음"이
    # 확인된 경우에만 도달한다. E-1이 완료되기 전까지는 이 경로에 도달하지 않는다.
    try:
        bitmap = pack_image_1bpp_msb_first(image, WIDTH_BYTES)
        command = build_raster_command(bitmap, WIDTH_BYTES, image.height)
        send_raster_over_usb(command)
    except Exception:
        log(f"실패: 인쇄 전송 중 예외 발생 (메시지 소스={message_source})\n{traceback.format_exc()}")
        return 1

    log(f"성공: 인쇄 완료 (메시지 소스={message_source}; {query_note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
