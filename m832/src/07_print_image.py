#!/usr/bin/env python3
"""07_print_image.py — E-3: 임의 이미지 출력 (PLAN-01 .temp/PLAN-01.md 11절 E-3, 구 PLAN.md 4단계 이식)

목표(CLAUDE.md): 순수 파이썬 + pyusb + Pillow만 사용. CUPS/벤더 드라이버 비의존.

파이프라인:
    이미지 로드 → 그레이스케일 → 확정 폭(WIDTH_BYTES)으로 리사이즈
    → Floyd-Steinberg 디더링(Pillow convert("1") 기본값)으로 1bit화
    → MSB-first 패킹(1=검정, docs/protocol.md 확인값)
    → 1f 11 0b + 1f 11 35 00 + 1d 76 30 00 <xL xH yL yH> + 비트맵 + 꼬리
      (꼬리는 매체별로 다르다 — 아래 "꼬리 바이트" 절과 --page-size-is-a4-or-letter 참고)

기본은 --dry-run(파일로만 저장, USB 미접촉)이다. 실물 전송은 --send를 명시해야 하며,
전송 전 반드시 "용지 확인" 인터랙티브 프롬프트를 통과해야 한다(CLAUDE.md 절대 금지 5).
보낸 바이트는 예외 없이 captures/sent/NNNN.bin에 저장한다(CLAUDE.md 절대 금지 3).

폭(WIDTH_BYTES)에 대한 중요한 주의:
    docs/protocol.md의 163byte(1300~1304dot, "110mm(w110h146) 용지 실측" 절)는 사용자가
    실제로 장착한 110mm 용지에 대해 cupsfilter가 벤더 필터에 먹였을 때 나온 bCmdBMP 값이지,
    프린터가 실제로 지원하는 최대/정확 폭이 아니다. WIDTH_BYTES는 PPD PageSize에 종속된
    값이며(CLAUDE.md), 이전에 A4로 테스트했을 때는 288byte(2304dot)이었다 — 매체가 바뀌면
    반드시 재확인해야 하는 값이지 하드웨어 고정 상수가 아니다. 진짜 하드웨어 폭 한계는
    D단계(CUPS 실물 인쇄) 또는 F-2(헤드 폭 실측, PLAN-01 12절)에서 확정된다. 그 전까지 이
    스크립트는 163을 "현재 장착된 용지에 대해 문서화된 값"으로 쓰고, --width-bytes로
    override 가능하게 열어둔다.

꼬리 바이트(footer)에 대한 중요한 주의:
    docs/filter-source-map.md (c)/(e)에 따르면 M832 벤더 필터는 연속용지(PAPER_CONTINUES)
    이고 `cupsPageSizeName`이 "A4"도 "Letter"도 아닐 때만 EndPage에서 `1B 64 01`(페이지별
    M832After 트리거)을 내보내고, job 전체가 끝나면 `1B 64 02`(job-end)를 한 번 더 내보낸다.
    A4/Letter일 때는 이 6바이트가 전혀 나가지 않고 `1F 11 11`(findpaper) 3바이트만 붙는다.
    사용자가 지금 실제로 장착한 110mm(w110h146) 용지는 A4도 Letter도 아니므로 --send 대상
    기본값은 "A4/Letter 아님"(9바이트 꼬리)이어야 한다. 이 스크립트는 향후 다른 매체에도
    쓰일 수 있으므로 이 분기를 하드코딩하지 않고 --page-size-is-a4-or-letter 플래그로 뽑아
    낸다(기본값 False = 현재 장착된 용지 기준).

높이(HEIGHT_LINES)에 대한 중요한 주의:
    docs/protocol.md가 관찰한 3484줄 패딩은 "A4 연속용지 전체 페이지를 끝까지 채우는" 벤더
    필터(rastertoM08F)의 로직이 만든 값이다(A4=295mm를 300dpi로 환산해 0xFF로 패딩). 이 스크립트는
    임의 크기 이미지 한 장을 그 이미지 실제 높이만큼만 인쇄하는 것이 목적이고, PLAN-01 E-3
    문단도 "확정 폭으로 리사이즈 → 디더링 → 패킹 → 전송"이라고만 적혀 있을 뿐 높이 패딩을
    요구하지 않는다. 따라서 여기서는 bCmdBMP의 yL/yH에 이미지의 실제 높이(dot)를 그대로 넣고,
    3484 같은 상수를 복사하지 않는다. 다만 이것이 "패딩이 전혀 필요 없다"는 것까지 확인된 사실은
    아니다 — 프린터가 최소 높이나 8배수 정렬을 요구할 가능성은 실물 전송(E-1/D단계)에서만
    확인 가능하며, 이 스크립트는 --dry-run으로만 검증되었다.

비트 극성에 대한 확인 사항:
    Pillow의 Image.convert("1").tobytes()는 자체적으로 1=흰색(255)/0=검정(0), MSB-first로
    패킹한다(이 스크립트 작성 중 .venv 안에서 실측 확인: 8픽셀 중 첫 픽셀만 검정으로 만들면
    tobytes()[0] == 0b01111111 — MSB가 0으로 나옴). docs/protocol.md가 확인한 프로토콜은
    반대(1=검정)이므로, 기본(--invert 미지정)에서는 Pillow 출력을 XOR 0xFF로 뒤집어 내보낸다.
    실물 인쇄에서 정반대로 나오면 --invert로 이 반전을 끈다(=Pillow 기본값을 그대로 내보냄).
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# 확정 상수 — docs/device-descriptor.md (1단계, 04_probe.py로 확인됨)
# ---------------------------------------------------------------------------
VID = 0x0483
PID = 0x5740
EP_OUT = 0x02  # BULK OUT, wMaxPacketSize=64
EP_IN = 0x81  # BULK IN — 이 스크립트에서는 미사용(findpaper 응답 읽기는 05_replay.py 영역)
USB_INTERFACE = 0

# libusb는 벌크 파이프를 알아서 wMaxPacketSize(64) 단위 패킷으로 쪼개므로, 파이썬 쪽 write
# 청크를 64byte로 맞출 필요는 없다. PLAN-01 E-1이 제시한 시작값(4096)을 그대로 따르고,
# 실측(끊김/STALL 여부)에 따라 조정한다. 이 스크립트에서는 --send를 실행하지 않으므로 미검증.
USB_CHUNK_SIZE = 4096
USB_WRITE_TIMEOUT_MS = 5000  # 모든 USB write에 명시 타임아웃 (CLAUDE.md 코드 규칙)

# ---------------------------------------------------------------------------
# 폭 상수 — docs/protocol.md "110mm(w110h146) 용지 실측" 절(C단계 확인값). 하드웨어
# 고정 상수가 아니라 PPD PageSize에 종속된 값이며(CLAUDE.md "확정된 사실" 참고), 매체를
# 바꾸면 반드시 재확인해야 한다.
# ---------------------------------------------------------------------------
WIDTH_BYTES = 163  # docs/protocol.md 110mm(w110h146) 실측값: 163byte(1300~1304dot).
# 사용자가 현재 실제 장착한 용지(110mm 폭)에 맞춘 기본값이다. A4는 288byte(2304dot)였다
# (같은 문서 상단 "전체 구조" 절, bCmdBMP xL=0x20 xH=0x01 -> 32+256=288) — 매체마다
# 다르므로 A4용 288을 그대로 재사용하면 안 된다. 다른 매체로 바꿀 때는 --width-bytes로
# override.
WIDTH_DOTS = WIDTH_BYTES * 8  # 1304

REPO_ROOT = Path(__file__).resolve().parent.parent  # m832/
CAPTURES_SENT_DIR = REPO_ROOT / "captures" / "sent"
CAPTURES_FILTER_DIR = REPO_ROOT / "captures" / "filter"

# ---------------------------------------------------------------------------
# 프로토콜 바이트 — docs/protocol.md [확인됨]
# ---------------------------------------------------------------------------
HDR_MEDIA_CONTINUOUS = bytes([0x1F, 0x11, 0x0B])  # 연속용지 (zeMediaTracking=Continuous)
HDR_COMPRESSION_OFF = bytes([0x1F, 0x11, 0x35, 0x00])  # M832은 압축 대상 기종이 아님(else 분기)
CMD_BMP_PREFIX = bytes([0x1D, 0x76, 0x30, 0x00])  # bCmdBMP, 뒤에 xL xH yL yH가 붙는다
FOOTER_FINDPAPER = bytes([0x1F, 0x11, 0x11])  # findpaper, 작업 종료 시 질의 (모든 매체 공통)
# bCmdAfter — docs/filter-source-map.md (c) 14912-14939. 연속용지 + PageSize가 A4/Letter가
# 아닐 때만 나간다(현재 실제 장착된 110mm 용지가 이 경우). A4/Letter에서는 전혀 나가지 않는다.
CMD_AFTER_PAGE = bytes([0x1B, 0x64, 0x01])  # 페이지별 트리거 (M832After=1)
CMD_AFTER_JOBEND = bytes([0x1B, 0x64, 0x02])  # job 전체 종료 시 한 번 더

# Pillow mode "1" 기본 패킹(1=흰색)을 프로토콜 극성(1=검정)으로 뒤집기 위한 룩업테이블
_INVERT_TABLE = bytes(x ^ 0xFF for x in range(256))


def load_and_prepare_image(path: Path, width_dots: int) -> Image.Image:
    """이미지 로드 → 그레이스케일 → 폭 리사이즈(가로세로 비율 유지). mode "L" 반환."""
    img = Image.open(path)
    img_l = img.convert("L")
    orig_w, orig_h = img_l.size
    if orig_w <= 0 or orig_h <= 0:
        raise ValueError(f"이미지 크기가 이상함: {img_l.size}")
    height_dots = max(1, round(orig_h * width_dots / orig_w))
    img_resized = img_l.resize((width_dots, height_dots), resample=Image.LANCZOS)
    return img_resized


def make_test_pattern(name: str, width_dots: int) -> Image.Image:
    """PLAN-01 E-3 검증 순서(체커보드→대각선→원)용 테스트 패턴을 메모리에서 생성한다.
    파일을 거치지 않아 방향/좌우반전 문제를 이미지 자체 문제와 분리해서 확인할 수 있다.
    세로 길이는 가로의 절반으로 고정한다(용지를 과도하게 소모하지 않기 위한 임의 선택)."""
    height_dots = max(1, width_dots // 2)
    img = Image.new("L", (width_dots, height_dots), color=255)  # 흰 배경
    draw = ImageDraw.Draw(img)

    if name == "checkerboard":
        square = 64
        for y in range(0, height_dots, square):
            for x in range(0, width_dots, square):
                if ((x // square) + (y // square)) % 2 == 0:
                    draw.rectangle(
                        [x, y, min(x + square, width_dots) - 1, min(y + square, height_dots) - 1],
                        fill=0,
                    )
    elif name == "diagonal":
        # 좌상단→우하단 대각선. 인쇄 후 대각선이 반대쪽(우상단→좌하단)으로 나오면
        # 좌우 또는 상하 반전이 있다는 뜻이다.
        thickness = max(4, width_dots // 200)
        draw.line([(0, 0), (width_dots - 1, height_dots - 1)], fill=0, width=thickness)
    elif name == "circle":
        # 정원이 타원으로 찌그러져 나오면 가로/세로 dot 밀도가 300x300dpi 정사각형이 아니라는 뜻.
        margin = min(width_dots, height_dots) // 10
        cx, cy = width_dots // 2, height_dots // 2
        r = min(width_dots, height_dots) // 2 - margin
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=max(4, r // 20))
    else:
        raise ValueError(f"알 수 없는 테스트 패턴: {name}")

    return img


def apply_h_offset(img_l: Image.Image, offset_dots: int) -> Image.Image:
    """콘텐츠를 캔버스 안에서 좌우로 이동한다. 전송 폭(width_dots)은 바뀌지 않는다 —
    벤더 소스(rastertoM08F.cxx)의 AdjustHoriaontal PPD 옵션과 동일한 방식:
    `hOffset`을 mm->dot로 환산해 픽셀 열 인덱스에 더하는 것(`int nj = j + hOffset`)을
    Pillow의 캔버스 paste로 재현한다. 양수(offset_dots>0)는 콘텐츠를 오른쪽으로 밀어
    왼쪽에 흰 여백을 만들고(오른쪽 끝은 그만큼 잘림), 음수는 반대다. 0이면 원본 그대로.
    실측(2mm 좌측 여백/우측 여백 없음, m832/docs/findings.md)을 보정하기 위해 추가됨."""
    if offset_dots == 0:
        return img_l
    width, height = img_l.size
    shifted = Image.new("L", (width, height), color=255)  # 255=흰색(패딩 없음과 동일한 배경)
    shifted.paste(img_l, (offset_dots, 0))
    return shifted


def dither_to_1bit(img_l: Image.Image) -> Image.Image:
    """Floyd-Steinberg 디더링으로 1bit 변환. Pillow convert("1")의 기본 dither가
    Floyd-Steinberg이므로 별도 파라미터 없이 그대로 사용한다."""
    return img_l.convert("1")


def pack_bitmap(img_1: Image.Image, invert: bool) -> bytes:
    """MSB-first 1bpp로 패킹. 기본(invert=False)은 1=검정(docs/protocol.md 확인값)."""
    width_dots, height_lines = img_1.size
    if width_dots % 8 != 0:
        raise ValueError(f"폭이 8의 배수가 아님: {width_dots}dot (WIDTH_BYTES 정렬 확인 필요)")

    packed = img_1.tobytes()  # Pillow 기본: MSB-first, 1=흰색/0=검정
    expected_len = (width_dots // 8) * height_lines
    if len(packed) != expected_len:
        raise ValueError(
            f"패킹 결과 길이 불일치: got {len(packed)}, expected {expected_len} "
            f"({width_dots}dot x {height_lines}line)"
        )

    if not invert:
        # 기본 경로: docs/protocol.md 확인값(1=검정)에 맞추기 위해 Pillow 기본 극성을 뒤집는다.
        packed = packed.translate(_INVERT_TABLE)
    # invert=True: Pillow 기본 극성(1=흰색)을 그대로 내보낸다 — 실물에서 반대로 나올 때의 토글.
    return packed


def build_command(
    width_bytes: int,
    height_lines: int,
    bitmap: bytes,
    page_size_is_a4_or_letter: bool,
) -> bytes:
    """docs/protocol.md 확인 구조: 헤더 + bCmdBMP + 비트맵 + 꼬리.

    꼬리(footer)는 매체에 따라 다르다(docs/filter-source-map.md (c)/(e)):
      - PageSize가 A4/Letter가 아님(연속용지, 현재 실제 장착된 110mm 용지 포함):
        1B 64 01(페이지별) + 1B 64 02(job-end) + 1F 11 11(findpaper) = 9byte
      - PageSize가 A4 또는 Letter: 1F 11 11(findpaper)만 = 3byte
    """
    if len(bitmap) != width_bytes * height_lines:
        raise ValueError(
            f"비트맵 길이 불일치: {len(bitmap)} != {width_bytes}*{height_lines}"
        )
    if not (0 <= width_bytes <= 0xFFFF) or not (0 <= height_lines <= 0xFFFF):
        raise ValueError(f"width_bytes/height_lines가 16bit 범위를 벗어남: {width_bytes}, {height_lines}")

    xL, xH = width_bytes & 0xFF, (width_bytes >> 8) & 0xFF
    yL, yH = height_lines & 0xFF, (height_lines >> 8) & 0xFF

    if page_size_is_a4_or_letter:
        tail = FOOTER_FINDPAPER
    else:
        tail = CMD_AFTER_PAGE + CMD_AFTER_JOBEND + FOOTER_FINDPAPER

    return (
        HDR_MEDIA_CONTINUOUS
        + HDR_COMPRESSION_OFF
        + CMD_BMP_PREFIX
        + bytes([xL, xH, yL, yH])
        + bitmap
        + tail
    )


def next_sent_number() -> str:
    """05_replay.py와 같은 규칙(captures/sent/NNNN.bin, 4자리 zero-pad)을 따른다.
    이 작성 시점에 05_replay.py가 아직 없어 확인된 선례는 없고, CLAUDE.md 예시
    (captures/sent/0007.bin)의 4자리 zero-pad 형식만 참고했다."""
    CAPTURES_SENT_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(CAPTURES_SENT_DIR.glob("[0-9][0-9][0-9][0-9].bin"))
    if not existing:
        return "0001"
    last = int(existing[-1].stem)
    return f"{last + 1:04d}"


def do_dry_run(stream: bytes, base_name: str) -> Path:
    CAPTURES_FILTER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CAPTURES_FILTER_DIR / f"dryrun_{base_name}.bin"
    out_path.write_bytes(stream)
    return out_path


def do_send(
    stream: bytes, width_bytes: int, height_lines: int, page_size_is_a4_or_letter: bool
) -> None:
    """CLAUDE.md 절대 금지 5: 용지 미확인 상태에서 래스터를 보내지 않는다.
    절대 금지 3: 보낸 바이트는 예외 없이 captures/sent/NNNN.bin에 저장한다.
    예외를 삼키지 않는다 — USB 오류는 그대로 위로 전파시킨다."""
    tail_len = 3 if page_size_is_a4_or_letter else 9
    print("=== 실물 인쇄 확인 ===", file=sys.stderr)
    print(
        f"보낼 바이트: {len(stream)} (width_bytes={width_bytes}, height_lines={height_lines}, "
        f"헤더 15byte + 비트맵 {width_bytes * height_lines}byte + 꼬리 {tail_len}byte"
        f"{'(A4/Letter)' if page_size_is_a4_or_letter else '(연속용지, 非A4/Letter — 1B 64 01+02 포함)'})",
        file=sys.stderr,
    )
    try:
        input("용지가 프린터에 장착되어 있는지 육안으로 확인했습니까? Enter=계속, Ctrl+C=중단: ")
    except KeyboardInterrupt:
        print("\n중단됨 — 아무것도 전송하지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    number = next_sent_number()
    sent_path = CAPTURES_SENT_DIR / f"{number}.bin"
    # 전송 시도 전에 먼저 디스크에 저장한다("전 또는 도중" 저장 — 전송이 중간에 실패해도
    # 무엇을 보내려 했는지는 남는다).
    sent_path.write_bytes(stream)
    print(f"[send] 전송 바이트를 저장함: {sent_path}", file=sys.stderr)

    import usb.core
    import usb.util

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise RuntimeError(
            f"장치를 찾을 수 없음 (VID={VID:#06x} PID={PID:#06x}). "
            "usbipd attach 상태·lsusb를 확인할 것."
        )

    if dev.is_kernel_driver_active(USB_INTERFACE):
        dev.detach_kernel_driver(USB_INTERFACE)

    dev.set_configuration()
    cfg = dev.get_active_configuration()
    intf = cfg[(USB_INTERFACE, 0)]
    usb.util.claim_interface(dev, USB_INTERFACE)

    try:
        total_written = 0
        for offset in range(0, len(stream), USB_CHUNK_SIZE):
            chunk = stream[offset : offset + USB_CHUNK_SIZE]
            written = dev.write(EP_OUT, chunk, timeout=USB_WRITE_TIMEOUT_MS)
            if written != len(chunk):
                raise IOError(
                    f"부분 전송 발생: offset={offset} written={written} expected={len(chunk)}"
                )
            total_written += written
        print(f"[send] 전송 완료: {total_written} bytes", file=sys.stderr)
    finally:
        usb.util.release_interface(dev, USB_INTERFACE)
        usb.util.dispose_resources(dev)


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="M832 이미지 출력 (pyusb 직접 재현, CUPS/벤더 드라이버 비의존). "
        "기본은 --dry-run이며 USB에 접촉하지 않는다."
    )
    src_group = p.add_mutually_exclusive_group(required=True)
    src_group.add_argument("image", nargs="?", default=None, help="인쇄할 이미지 파일 경로")
    src_group.add_argument(
        "--test-pattern",
        choices=["checkerboard", "diagonal", "circle"],
        default=None,
        help="파일 대신 메모리에서 생성한 테스트 패턴 사용 (PLAN-01 E-3 검증 순서: "
        "체커보드→대각선→원, 방향/좌우반전 확인용)",
    )
    p.add_argument(
        "--send",
        action="store_true",
        help="실제로 USB로 전송한다. 지정하지 않으면 dry-run(파일 저장만).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="기본 동작(USB 미접촉, captures/filter/dryrun_*.bin 저장)을 명시적으로 지정한다. "
        "--send와 함께 쓸 수 없다 — 아무 것도 지정하지 않아도 동작은 동일하다.",
    )
    p.add_argument(
        "--invert",
        action="store_true",
        help="비트 극성을 반전한다 (기본은 1=검정, docs/protocol.md C단계 확인값). "
        "실물 인쇄 결과가 반대(반전된 이미지)로 나오면 이 옵션을 사용.",
    )
    p.add_argument(
        "--width-bytes",
        type=int,
        default=None,
        help=f"폭(byte/line) override. 기본값 {WIDTH_BYTES}byte({WIDTH_DOTS}dot)는 현재 실제 "
        "장착된 110mm(w110h146) 용지의 C단계 cupsfilter 경유 산출값이며(docs/protocol.md), "
        "하드웨어 한계 확정값이 아니다 — 매체를 바꾸거나 F-2 실측 후 조정할 때 사용.",
    )
    p.add_argument(
        "--h-offset-mm",
        type=float,
        default=2.0,
        help="콘텐츠를 좌우로 이동해 물리적 정렬 오차를 보정한다(mm, 300dpi 기준 dot로 환산). "
        "양수=오른쪽 이동, 음수=왼쪽 이동. 기본값 2.0은 실물 인쇄 실측으로 확정된 보정값 "
        "(m832/docs/findings.md 'E-3 — 수평 정렬 보정' 참고): 보정 전 좌측 여백 ~2mm/우측 0mm였던 것이 "
        "+2mm 적용 후 좌우 대칭 ~1mm/~1mm로 개선됨(완전히 0이 되지 않는 건 현재 폭 설정 자체가 실제 "
        "인쇄 가능 폭보다 ~2mm 넓게 잡혀 있기 때문 — 같은 문서 참고). 다른 매체·다른 개체 프린터에서는 "
        "재보정 필요할 수 있으므로 0으로 override 가능하게 남겨둔다.",
    )
    p.add_argument(
        "--page-size-is-a4-or-letter",
        action="store_true",
        default=False,
        help="꼬리 바이트를 A4/Letter 방식(1F 11 11만, 3byte)으로 낸다. 기본값 False는 "
        "현재 실제 장착된 110mm(w110h146) 용지 기준이며, docs/filter-source-map.md (c)/(e)에 "
        "따라 연속용지+비-A4/Letter일 때 EndPage가 1B 64 01(페이지별)+1B 64 02(job-end)를 "
        "1F 11 11 앞에 추가로 내보내므로 꼬리가 9byte가 된다. A4/Letter 용지로 바꿔 테스트할 "
        "때만 이 플래그를 켠다.",
    )
    return p


def main() -> None:
    args = build_argparser().parse_args()

    if args.send and args.dry_run:
        print("--send와 --dry-run을 동시에 지정할 수 없습니다.", file=sys.stderr)
        sys.exit(2)

    width_bytes = args.width_bytes if args.width_bytes is not None else WIDTH_BYTES
    if width_bytes <= 0:
        raise ValueError(f"width_bytes는 양수여야 함: {width_bytes}")
    width_dots = width_bytes * 8

    if args.test_pattern:
        img_l = make_test_pattern(args.test_pattern, width_dots)
        base_name = args.test_pattern
    else:
        path = Path(args.image)
        if not path.exists():
            print(f"이미지 파일을 찾을 수 없음: {path}", file=sys.stderr)
            sys.exit(2)
        img_l = load_and_prepare_image(path, width_dots)
        base_name = path.stem

    if args.h_offset_mm != 0.0:
        offset_dots = round(args.h_offset_mm / 25.4 * 300)  # 300dpi 확정 사실
        img_l = apply_h_offset(img_l, offset_dots)
        print(f"수평 보정 적용: {args.h_offset_mm}mm -> {offset_dots}dot", file=sys.stderr)

    img_1 = dither_to_1bit(img_l)
    height_lines = img_1.size[1]
    bitmap = pack_bitmap(img_1, invert=args.invert)
    stream = build_command(
        width_bytes, height_lines, bitmap, args.page_size_is_a4_or_letter
    )

    est_mm = height_lines / 300.0 * 25.4  # 300dpi 가정(확정 사실: docs 하드웨어 사양)
    print(
        f"이미지 준비 완료: {width_dots}x{height_lines}dot "
        f"({width_bytes}byte/line, 총 {len(stream)}byte, 예상 인쇄 길이 약 {est_mm:.1f}mm)",
        file=sys.stderr,
    )

    if args.send:
        do_send(stream, width_bytes, height_lines, args.page_size_is_a4_or_letter)
    else:
        out_path = do_dry_run(stream, base_name)
        print(f"[dry-run] {len(stream)} bytes -> {out_path}", file=sys.stderr)
        print("(USB에 접촉하지 않았습니다. 실물 전송은 --send를 명시하세요.)", file=sys.stderr)


if __name__ == "__main__":
    main()
