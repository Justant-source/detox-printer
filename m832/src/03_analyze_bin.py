#!/usr/bin/env python3
"""PLAN-01 C단계: 필터 출력 바이트 분석.

t1_white/t2_black/t3_corner/t4_line 4종의 rastertoM08F 출력(.bin)을 비교해
헤더/데이터/푸터 경계, 압축 여부, bCmdBMP 폭·높이 필드를 특정한다.
"""
import pathlib

D = pathlib.Path(__file__).resolve().parent.parent / "captures" / "filter"


def load(name):
    return (D / f"{name}.bin").read_bytes()


def find_all(data, pat):
    out = []
    i = data.find(pat)
    while i != -1:
        out.append(i)
        i = data.find(pat, i + 1)
    return out


def main():
    t1, t2, t3, t4 = load("t1"), load("t2"), load("t3"), load("t4")

    print("=== 크기 ===")
    for n, d in [("t1_white", t1), ("t2_black", t2), ("t3_corner", t3), ("t4_line", t4)]:
        print(f"{n}: {len(d)} bytes")

    print("\n=== 헤더 (첫 64바이트, xxd 스타일) ===")
    for n, d in [("t1", t1)]:
        for off in range(0, 64, 16):
            chunk = d[off:off + 16]
            hexs = " ".join(f"{b:02x}" for b in chunk)
            print(f"{n} {off:04x}: {hexs}")

    print("\n=== bCmdBMP(1D 76 30) 위치 ===")
    marker = bytes.fromhex("1d7630")
    for n, d in [("t1", t1), ("t2", t2), ("t3", t3), ("t4", t4)]:
        offs = find_all(d, marker)
        print(f"{n}: {len(offs)}개 위치 -> {offs[:5]}")
        for off in offs[:2]:
            block_hdr = d[off:off + 8]
            xl, xh, yl, yh = block_hdr[4], block_hdr[5], block_hdr[6], block_hdr[7]
            width_bytes = xl + xh * 256
            height_lines = yl + yh * 256
            print(f"  off={off} hdr={block_hdr.hex()} xL={xl} xH={xh} yL={yl} yH={yh}"
                  f" -> WIDTH_BYTES={width_bytes} HEIGHT_LINES={height_lines}")

    print("\n=== 1F 11 xx 명령 시퀀스 (헤더 영역, 첫 등장 위치까지) ===")
    first_bmp = t1.find(marker)
    head = t1[:first_bmp]
    i = 0
    while i < len(head) - 2:
        if head[i] == 0x1F and head[i + 1] == 0x11:
            length_guess = 4 if i + 3 < len(head) else 3
            print(f"  off={i}: {head[i:i+length_guess].hex()}")
            i += length_guess
        else:
            i += 1
    print(f"(bCmdBMP 이전 헤더 전체 길이: {first_bmp} bytes)")

    print("\n=== 페이지 데이터 이후 꼬리(tail) 바이트 (마지막 32바이트) ===")
    for n, d in [("t1", t1), ("t2", t2), ("t3", t3), ("t4", t4)]:
        print(f"{n} tail: {d[-32:].hex()}")

    print("\n=== t1 vs t2 (압축 여부: 크기 동일하면 비압축) ===")
    print(f"len(t1)==len(t2): {len(t1) == len(t2)}")
    diffs = sum(1 for a, b in zip(t1, t2) if a != b)
    print(f"다른 바이트 수: {diffs} / {len(t1)}")
    first_diff = next((i for i, (a, b) in enumerate(zip(t1, t2)) if a != b), None)
    print(f"첫 차이 위치: {first_diff}")

    print("\n=== t1(전면 흰색) vs t3(좌상단 100x100 검정): 검정 비트 위치로 극성 확인 ===")
    diffs13 = [i for i, (a, b) in enumerate(zip(t1, t3)) if a != b]
    print(f"다른 바이트 수: {len(diffs13)}, 첫 차이: {diffs13[0] if diffs13 else None}, 마지막 차이: {diffs13[-1] if diffs13 else None}")
    if diffs13:
        off = diffs13[0]
        print(f"  t1[{off}]=0x{t1[off]:02x}  t3[{off}]=0x{t3[off]:02x}")

    print("\n=== t1 vs t4 (가로 1px 줄: 라인 경계 확인) ===")
    diffs14 = [i for i, (a, b) in enumerate(zip(t1, t4)) if a != b]
    print(f"다른 바이트 수: {len(diffs14)}, 첫 차이: {diffs14[0] if diffs14 else None}, 마지막 차이: {diffs14[-1] if diffs14 else None}")


if __name__ == "__main__":
    main()
