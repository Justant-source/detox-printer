#!/usr/bin/env python3
"""PLAN-01 E-2: 벤더 필터(`rastertoM08F`) 출력 캡처를 CUPS/벤더 필터 없이
순수 Python(Pillow + stdlib)만으로 바이트 단위로 재현한다.

두 매체를 지원한다:
- a4      : `captures/filter/t3.bin` (2480x3508px A4 소스, 좌상단 100x100 검정 사각형)
- w110h146: `captures/filter/w110h146/t3n.bin2` (사용자 실제 장착 용지, 110mm x 146mm,
            1300x1724px 소스, 좌상단 100x100 검정 사각형)

이 스크립트는 USB/CUPS/벤더 바이너리를 전혀 실행하지 않는다. 이미 캡처된
*.bin*(=필터 출력 결과)과 *_corner.png(=필터 입력 이미지)만 파일로 읽는다.

인자 없이 실행하면 두 매체를 모두 검증한다. `python3 06_generate.py a4` 또는
`python3 06_generate.py w110h146`처럼 인자를 주면 해당 매체만 검증한다.

--- A4: 스케일/오프셋을 어떻게 확정했는가 (추측 아님, t3.bin 실측으로 역산) ---

`docs/protocol.md`의 "A단계 PPD 계산값과의 교차 검증" 절에 따르면 cupsfilter의
imagetoraster가 실제로 사용한 ImagingBoundingBox는 폭 553pt(->2304dot, 8배수
정렬), 높이는 cupsHeight=3257로 보고되었다(`docs/protocol.md` "높이 패딩" 절).
즉 필터가 최종적으로 사용한 캔버스는 2304 x 3257 px이며, 우리 소스 PNG는
2480 x 3508 px 전체 페이지 이미지다.

그 캔버스에 원본 이미지를 정확히 어떻게 맞췄는지(스케일 방식·오프셋)는
소스 코드 지도(`docs/filter-source-map.md`)에 없어서(imagetoraster는
rastertoM08F가 아니라 cups-filters 쪽 코드), t3.bin의 실제 비트를 역산해서
검증했다:

- t3.bin의 비트맵에서 검정 픽셀은 정확히 (row=0..92, col=0..92)의 93x93
  정사각형뿐이다(전수조사, 다른 곳은 전부 0). 경계가 완전히 날카롭다
  (그레이/안티앨리어싱 픽셀이 전혀 없다) -> 필터가 쓴 축소 알고리즘은
  보간(bilinear 등)이 아니라 **최근접 이웃(nearest-neighbor) 포인트 샘플링**이다.
- 원본 사각형은 소스 이미지의 (0,0)~(99,99) 100x100px(01_make_testimages.py 참고).
  출력 캔버스 좌표 i가 소스 좌표 `floor(i * SRC/DST)`를 그대로 가리키는
  "좌상단 정렬, 오프셋 없음" 최근접 이웃 매핑으로 놓고 계산하면:
    i=92 -> floor(92*2480/2304)=floor(99.03)=99 (사각형 안쪽, 마지막 검정 열)
    i=93 -> floor(93*2480/2304)=floor(100.10)=100 (사각형 밖, 첫 흰 열)
  세로도 동일 공식(높이 스케일 3508/3257)으로 92->99, 93->100이 나와 정확히
  일치한다. 즉 오프셋은 0이고(이미지 (0,0)이 캔버스 (0,0)에 그대로 대응),
  가로/세로 스케일은 서로 독립적으로(비율 보존 없이) 캔버스 크기에 맞춰
  최근접 이웃으로 다운샘플링된다.
- Pillow의 `Image.resize(..., Image.NEAREST)`가 이 픽셀 좌표 매핑과 정확히
  같은 결과를 내는지 별도로 검증(대화 중 실측, 93x93 사각형 경계 완전 일치)
  했으므로 아래 코드는 Pillow 표준 resize를 그대로 사용한다.

--- A4: 높이 패딩 바이트 값을 어떻게 확정했는가 ---

`docs/filter-source-map.md` (e)절 소스(14611-14636)는 패딩 시
`memset(tempbuf, 0xFF, tmph*tmpw)`를 쓰는데, 이 시점의 버퍼는 **아직 1bpp로
패킹되기 전, 픽셀당 1바이트짜리 그레이스케일 버퍼**다(패킹은 훨씬 뒤
OutputLine()에서 일어난다). 그레이스케일 0xFF(255)=흰색이고, OutputLine의
`case M832`(13401-13429, `pixelColor <= 128`이면 비트 1=검정)에 따르면
255는 128보다 크므로 비트 0(흰색)이 된다. 즉 **패킹된 최종 바이트 레벨에서는
패딩이 0xFF가 아니라 0x00이어야 한다.**
이 해석을 t3.bin 실측으로 검증했다: 실제 이미지 데이터는 3257줄(0~3256)까지고,
그 뒤 3257~3483줄(227줄 = 3484-3257)의 패킹된 바이트는 t3.bin에서 전부 0x00임을
확인했다(전수조사, 예외 없음). 아래 코드는 이 실측대로 0x00으로 채운다.

--- w110h146(110mm): A4와 다른 점, 어떻게 확인했는가 ---

`docs/protocol.md`의 "110mm(w110h146) 용지 실측" 절 기준. t3n.bin2의 bCmdBMP를
직접 파싱해 실측했다(추측 아님):
- xL=0xa3(163), xH=0x00 -> WIDTH_BYTES=163 (=1304dot)
- yL=0xbd(189), yH=0x06 -> HEIGHT_LINES=1725
- t3n.bin2 총 15,199+... 바이트 중 헤더(15) + 163*1725=281,175 + 꼬리 9바이트
  = 281,199바이트로 실제 파일 크기와 정확히 일치(검증 완료).
- **꼬리가 A4와 다르다**: `1b 64 01`(bCmdAfter, M832After) + `1b 64 02`
  (작업 종료) + `1f 11 11`(findpaper) = 9바이트. A4/Letter는 PageSize 조건 때문에
  이 bCmdAfter가 안 붙지만(`docs/filter-source-map.md` EndPage 로직), w110h146은
  붙는다 — protocol.md에 [확인됨]으로 기록됨.
- **높이 패딩이 없다**: HEIGHT_LINES(1725) == 실제 사용 캔버스 높이(1725), 즉
  PAD_LINES=0. A4처럼 고정값(3484)으로 채우지 않고 이미지 높이 그대로 쓴다.
- 소스 PNG(t3n_corner.png)는 1300x1724px인데 실측 캔버스 높이는 1725로, PNG보다
  1픽셀 더 크다(ImageableArea `0 0 312 414`pt -> 414pt*300/72=1725.0 정확히,
  반면 PNG 제작 시 146mm*300dpi/25.4=1724.4->1724로 반올림해 1픽셀 오차 발생 —
  protocol.md의 "반올림 오차 ±1" 기록과 일치). 폭은 312pt*300/72=1300.0로 PNG
  폭(1300)과 정확히 일치해 폭 방향 리스케일은 실질적으로 없다(1:1).
- 이 1픽셀 높이 차이를 A4와 동일한 `Image.resize(..., Image.NEAREST)` 로직으로
  (1300,1724) -> (1300,1725) 업스케일하면(A4와 코드 경로 완전히 동일, 크기만
  다름), t3n.bin2와 바이트 단위로 정확히 일치함을 실측 확인했다(마지막 줄이
  바로 앞 줄과 완전히 동일하게 복제되는데, 이는 NEAREST 업스케일의 자연스러운
  결과이자 t3n.bin2 실측값과 일치).
- **폭 바이트 정렬 패딩**: CUPS_WIDTH(1300)가 WIDTH_BYTES*8(1304)보다 4dot
  작다(163*8-1300=4). A4는 우연히 WIDTH_BYTES*8==CUPS_WIDTH(2304)라 패딩이
  전혀 없었지만, 110mm은 한 줄당 끝에 4비트의 바이트-정렬 패딩이 생긴다.
  이 4비트는 실측상 전부 0(흰색)이었다 — MSB-first로 패킹된 각 줄의 정수를
  왼쪽으로 (WIDTH_BYTES*8 - CUPS_WIDTH)비트만큼 시프트해서 그 빈 하위비트가
  자동으로 0이 되게 하면 정확히 일치한다(아래 `render_bitmap`의 `bit_pad`).
"""
import pathlib
import sys
from dataclasses import dataclass

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 헤더 공통 부분 (docs/protocol.md "전체 구조" 표, 전부 [확인됨], A4/110mm 동일 구조)
HDR_MEDIA = bytes.fromhex("1f110b")        # 미디어 타입: 연속용지(zeMediaTracking=Continuous)
HDR_COMPRESSION_OFF = bytes.fromhex("1f113500")  # M832은 압축 목록에 없어 항상 Off
                                                  # (docs/filter-source-map.md (b)절)


@dataclass(frozen=True)
class MediaConfig:
    name: str
    src_png: pathlib.Path
    target_bin: pathlib.Path
    out_bin: pathlib.Path
    src_expected_size: tuple  # (w, h)px, 소스 PNG가 이 크기가 아니면 즉시 에러
    width_bytes: int          # bCmdBMP xL/xH 실측값
    height_lines: int         # bCmdBMP yL/yH 실측값 (=최종 패킹된 총 줄 수)
    cups_width: int           # 필터가 실제로 리샘플링에 사용한 캔버스 폭(px)
    cups_height: int          # 필터가 실제로 리샘플링에 사용한 캔버스 높이(px, 패딩 전)
    footer: bytes              # 꼬리 바이트 (A4/Letter vs 그 외 PageSize가 다름)


MEDIA_CONFIGS = {
    "a4": MediaConfig(
        name="a4",
        src_png=ROOT / "captures" / "filter" / "t3_corner.png",
        target_bin=ROOT / "captures" / "filter" / "t3.bin",
        out_bin=ROOT / "captures" / "filter" / "t3_generated.bin",
        src_expected_size=(2480, 3508),
        width_bytes=288,   # C단계 실측(bCmdBMP xL/xH=0x20,0x01). 하드웨어 최대 폭이 아님
                           # (docs/protocol.md "A단계 교차 검증" 절)
        height_lines=3484,  # C단계 실측(bCmdBMP yL/yH=0x9c,0x0d).
                            # A4 295mm*300dpi/25.4=3484.25->3484
                            # (docs/filter-source-map.md (e)절 tmph 계산)
        cups_width=288 * 8,   # = 2304px, ImagingBoundingBox 553pt -> 2304dot(8배수 정렬)
        cups_height=3257,     # cupsfilter가 보고한 cupsHeight(패딩 전 실제 이미지 높이)
        footer=bytes.fromhex("1f1111"),  # findpaper만 (PageSize=A4라 bCmdAfter 없음)
    ),
    "w110h146": MediaConfig(
        name="w110h146",
        src_png=ROOT / "captures" / "filter" / "w110h146" / "t3n_corner.png",
        target_bin=ROOT / "captures" / "filter" / "w110h146" / "t3n.bin2",
        out_bin=ROOT / "captures" / "filter" / "w110h146" / "t3n_generated.bin",
        src_expected_size=(1300, 1724),
        width_bytes=163,     # C단계 실측(t3n.bin2 bCmdBMP xL/xH=0xa3,0x00)
        height_lines=1725,   # C단계 실측(t3n.bin2 bCmdBMP yL/yH=0xbd,0x06).
                             # 고정 패딩 없이 실제 사용 캔버스 높이 그대로
                             # (docs/protocol.md "110mm 실측" 절)
        cups_width=1300,     # ImageableArea 312pt*300/72=1300.0 (PNG 폭과 정확히 일치)
        cups_height=1725,    # ImageableArea 414pt*300/72=1725.0
                             # (PNG는 1724px로 1픽셀 오차 있음 -> resize로 흡수, docstring 참고)
        footer=bytes.fromhex("1b64011b64021f1111"),  # bCmdAfter(1b6401+1b6402) + findpaper
                                                      # PageSize!=A4/Letter라 bCmdAfter 발동
                                                      # (docs/protocol.md "110mm 실측" 절)
    ),
}


def build_bcmd_bmp(width_bytes: int, height_lines: int) -> bytes:
    """1D 76 30 00 xL xH yL yH (docs/filter-source-map.md (c)절 14780-14788)."""
    x_lo = width_bytes % 256
    x_hi = width_bytes // 256
    y_lo = height_lines % 256
    y_hi = height_lines // 256
    return bytes([0x1D, 0x76, 0x30, 0x00, x_lo, x_hi, y_lo, y_hi])


def render_bitmap(cfg: MediaConfig) -> bytes:
    """소스 PNG -> 1bpp MSB-first 패킹된 비트맵(높이 패딩 포함)."""
    im = Image.open(cfg.src_png).convert("L")  # 그레이스케일 변환. 소스가 순흑/순백뿐이라
                                                # RGB->gray 공식 차이는 결과에 영향 없음
    if im.size != cfg.src_expected_size:
        raise ValueError(
            f"[{cfg.name}] 예상치 못한 소스 크기: {im.size} (기대: {cfg.src_expected_size})"
        )

    # 필터가 실제로 배치한 캔버스 크기(cups_width x cups_height)로 최근접 이웃
    # 리샘플링. A4는 다운스케일, w110h146은 높이 방향으로 1px 업스케일이지만
    # 코드 경로는 완전히 동일하다(Image.resize NEAREST에게 방향은 문제가 안 됨).
    # 스케일 근거는 파일 상단 docstring 참고 (각 매체의 *.bin* 실측으로 역산·검증됨).
    resized = im.resize((cfg.cups_width, cfg.cups_height), Image.NEAREST)
    raw = resized.tobytes()  # 1 byte/pixel, row-major, len == cups_width*cups_height

    # threshold: pixelColor <= 128 -> 검정(비트 1) (docs/filter-source-map.md (d)절, 13422행)
    # ASCII '1'(0x31)/'0'(0x30)로 매핑한 뒤 int(...,2)로 한 번에 packing (순수 Python 루프보다 빠름)
    THRESH_TO_BIT_ASCII = bytes(
        0x31 if v <= 128 else 0x30 for v in range(256)
    )

    # 한 줄의 실제 픽셀 수(cups_width)가 WIDTH_BYTES*8(바이트 정렬된 비트 수)보다
    # 작을 수 있다(w110h146: 1300 vs 1304). MSB-first 패킹이므로 그 차이만큼
    # 왼쪽으로 시프트해서 남는 하위 비트가 0(흰색)으로 채워지게 한다.
    # A4는 우연히 두 값이 같아(2304==2304) bit_pad=0, 즉 시프트가 no-op이다.
    bit_pad = cfg.width_bytes * 8 - cfg.cups_width
    assert bit_pad >= 0, f"[{cfg.name}] cups_width가 width_bytes*8보다 큼: {cfg}"

    rows = bytearray()
    for r in range(cfg.cups_height):
        row_pixels = raw[r * cfg.cups_width : (r + 1) * cfg.cups_width]
        bits_ascii = row_pixels.translate(THRESH_TO_BIT_ASCII)
        row_int = int(bits_ascii, 2)  # MSB-first (j=0이 최상위 비트, 13423행 128>>j와 동일)
        row_int <<= bit_pad
        rows += row_int.to_bytes(cfg.width_bytes, "big")

    # 높이 패딩: A4는 cups_height(3257) -> height_lines(3484)로 227줄 패딩이 붙지만,
    # w110h146은 cups_height==height_lines(1725==1725)라 pad_lines=0 (패딩 없음).
    # 패킹된 바이트 레벨에서 패딩 값은 0x00(흰색). 근거: 파일 상단 docstring
    # "A4: 높이 패딩 바이트 값을 어떻게 확정했는가" 참고.
    pad_lines = cfg.height_lines - cfg.cups_height
    assert pad_lines >= 0, f"[{cfg.name}] cups_height가 height_lines보다 큼: {cfg}"
    rows += bytes(cfg.width_bytes * pad_lines)

    assert len(rows) == cfg.width_bytes * cfg.height_lines, (
        f"[{cfg.name}] 비트맵 길이 불일치: {len(rows)} != {cfg.width_bytes * cfg.height_lines}"
    )
    return bytes(rows)


def run_one(cfg: MediaConfig) -> bool:
    """하나의 매체 설정을 검증한다. PASS면 True, FAIL이면 False를 반환한다."""
    if not cfg.src_png.exists():
        print(f"[{cfg.name}] FAIL: 소스 이미지 없음: {cfg.src_png}")
        return False
    if not cfg.target_bin.exists():
        print(f"[{cfg.name}] FAIL: 대조 대상 없음: {cfg.target_bin}")
        return False

    bitmap = render_bitmap(cfg)
    bcmd_bmp = build_bcmd_bmp(cfg.width_bytes, cfg.height_lines)

    generated = HDR_MEDIA + HDR_COMPRESSION_OFF + bcmd_bmp + bitmap + cfg.footer

    cfg.out_bin.write_bytes(generated)
    target = cfg.target_bin.read_bytes()

    if generated == target:
        print(
            f"[{cfg.name}] PASS: {cfg.out_bin.name} ({len(generated)} bytes) "
            f"== {cfg.target_bin.name} (byte-for-byte identical)"
        )
        return True

    # 실패 시: 실패를 숨기지 않는다 (CLAUDE.md 규칙 4)
    print(f"[{cfg.name}] FAIL: 불일치 (생성 {len(generated)} bytes, 대상 {len(target)} bytes)")
    n = min(len(generated), len(target))
    first_diff = None
    diff_count = 0
    for i in range(n):
        if generated[i] != target[i]:
            diff_count += 1
            if first_diff is None:
                first_diff = i
    diff_count += abs(len(generated) - len(target))
    if first_diff is not None:
        print(
            f"  [{cfg.name}] 첫 차이 오프셋: {first_diff} "
            f"(생성=0x{generated[first_diff]:02x}, 대상=0x{target[first_diff]:02x})"
        )
    print(f"  [{cfg.name}] 총 차이 바이트 수: {diff_count} / {max(len(generated), len(target))}")
    return False


def main() -> int:
    if len(sys.argv) > 1:
        names = sys.argv[1:]
        for n in names:
            if n not in MEDIA_CONFIGS:
                print(f"FAIL: 알 수 없는 매체 '{n}' (선택 가능: {', '.join(MEDIA_CONFIGS)})")
                return 1
    else:
        names = list(MEDIA_CONFIGS)  # 인자 없으면 전부 검증

    ok = True
    for n in names:
        ok = run_one(MEDIA_CONFIGS[n]) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
