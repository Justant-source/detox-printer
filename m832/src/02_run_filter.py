#!/usr/bin/env python3
"""PLAN-01 C단계: PNG -> CUPS raster -> 벤더 필터(rastertoM08F) 오프라인 실행.

DEVICE_URI에 "bluetooth:"를 넣어야 필터가 용지/커버 상태를 무한 대기하지
않는다 (m832/.temp/PLAN-01.md B단계, m832/docs/filter-source-map.md 참고).
필터는 절대 sudo로 실행하지 않는다.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "captures" / "filter"
DRIVER = ROOT / ".temp" / "driver" / "extracted" / "QY_Printer-2.1.0.3"
PPD = DRIVER / "ppds" / "M832.ppd"
FILTER = DRIVER / "x86_64" / "rastertoM08F"

NAMES = ["t1_white", "t2_black", "t3_corner", "t4_line"]


def run_one(name, timeout_s=30):
    short = name.split("_")[0]
    png = D / f"{name}.png"
    ras = D / f"{short}.ras"
    binf = D / f"{short}.bin"
    errf = D / f"{short}.stderr.log"
    cflog = D / f"{short}.cupsfilter.log"

    with open(cflog, "wb") as errfh, open(ras, "wb") as rasfh:
        subprocess.run(
            ["cupsfilter", "-m", "application/vnd.cups-raster", "-p", str(PPD), str(png)],
            stdout=rasfh, stderr=errfh, check=True,
        )

    env = {"PPD": str(PPD), "DEVICE_URI": "bluetooth://offline", "PATH": "/usr/bin:/bin"}
    with open(ras, "rb") as inf, open(binf, "wb") as outf, open(errf, "wb") as errfh:
        proc = subprocess.run(
            ["timeout", str(timeout_s), str(FILTER), "1", "tester", "test", "1", ""],
            stdin=inf, stdout=subprocess.PIPE, stderr=errfh, env=env,
        )
        outf.write(proc.stdout[:104857600])
    print(f"{short}: exit={proc.returncode} size={binf.stat().st_size}")
    return proc.returncode


def main():
    codes = {n: run_one(n) for n in NAMES}
    failed = [n for n, c in codes.items() if c != 0]
    if failed:
        print(f"실패(비정상 종료): {failed} — 재시도 권장, 3회 넘게 실패하면 F단계", file=sys.stderr)


if __name__ == "__main__":
    main()
