#!/usr/bin/env python3
"""PLAN-01 C단계: 필터 오프라인 실행용 테스트 이미지 4종 생성.

A4 @300dpi = 2480 x 3508 dot (전체 페이지, cupsfilter가 PPD의
ImageableArea로 마진 처리를 하므로 여기서는 전체 페이지를 채운다).
"""
import pathlib
from PIL import Image, ImageDraw

DPI = 300
W = 2480  # A4 210mm @300dpi
H = 3508  # A4 297mm @300dpi
OUT = pathlib.Path(__file__).resolve().parent.parent / "captures" / "filter"
OUT.mkdir(parents=True, exist_ok=True)

def save(name, im):
    path = OUT / f"{name}.png"
    im.save(path, dpi=(DPI, DPI))
    print(f"wrote {path} {im.size}")

# t1_white: 전면 흰색 -> 헤더/푸터 순수 형태 확인
t1 = Image.new("RGB", (W, H), (255, 255, 255))
save("t1_white", t1)

# t2_black: 전면 검정 -> 압축 여부(t1과 크기 비교)
t2 = Image.new("RGB", (W, H), (0, 0, 0))
save("t2_black", t2)

# t3_corner: 좌상단 100x100만 검정 -> 좌표/오프셋 인코딩 확인
t3 = Image.new("RGB", (W, H), (255, 255, 255))
d3 = ImageDraw.Draw(t3)
d3.rectangle([0, 0, 99, 99], fill=(0, 0, 0))
save("t3_corner", t3)

# t4_line: 가로 1px 검은 줄 하나 -> 라인 단위 구조 확인
t4 = Image.new("RGB", (W, H), (255, 255, 255))
d4 = ImageDraw.Draw(t4)
d4.line([(0, H // 2), (W - 1, H // 2)], fill=(0, 0, 0), width=1)
save("t4_line", t4)
