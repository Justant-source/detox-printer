# 실험 기록

> 형식: 실험 하나당 3줄. 보낸 것 / 관찰 / 결론.
> 성공 여부와 무관하게 전부 남긴다. 실패 기록이 이 프로젝트의 자산이다.

## 확정 상수 (실측으로 확인된 것만)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| VID:PID | 0483:5740 [확인됨] | 1단계 |
| BULK OUT 엔드포인트 | 0x02, wMaxPacketSize=64 [확인됨] | 1단계 |
| wMaxPacketSize | 64 (IN/OUT 동일) [확인됨] | 1단계 |
| 인터페이스 클래스 | 7 (Printer), SubClass 0x01, Protocol 0x02(양방향) [확인됨] | 1단계 |
| 초기화 시퀀스 | `1f 11 0b`(연속용지) + `1f 11 35 00`(압축off) [확인됨·필터출력] | B-2 소스 + C단계 |
| **WIDTH_BYTES** | **PageSize에 종속(고정 하드웨어값 아님)**. A4=288, **110mm(w110h146)=163 [확인됨·bCmdBMP 실측, 사용자 실장착 용지에 적용]**. protocol.md 참고 | A단계 PPD 계산 + C단계 bCmdBMP |
| 검정 비트값 (1 or 0) | 1=검정, MSB-first, 반전 없음 [확인됨·소스+필터출력, A4·110mm 둘 다 동일 확인] | B-2 소스 + C단계 |
| 블록당 최대 라인 수 | 페이지당 1블록. A4/Letter는 고정 295mm/11in로 높이 패딩, 그 외 PageSize(110mm 포함)는 패딩 없이 실제 이미지 높이 그대로 [확인됨·소스+C단계] | B-2 소스 + E-1 |
| 해상도 | 300dpi [확인됨·PPD] | A단계 |
| A4 ImageableArea | "14.17 30 580.83 812" pt (PPD 선언값. 실제 사용폭은 cupsfilter 배치에 따라 다름) [확인됨·PPD] | A단계 |
| 벤더 필터·cupsModelNumber | rastertoM08F / 77832 [확인됨·PPD] | A단계 |
| 필터 입력 색공간/비트 | cupsColorSpace 1(RGB) / cupsBitsPerColor 8 [확인됨·PPD+필터출력] | A단계 |
| 압축 여부 | Off 확정 (`1F 11 35 00`, t1/t2 크기 동일) [확인됨·필터출력] | C단계 |
| 헤더 시퀀스 | `1f 11 0b` → `1f 11 35 00` → `1d 76 30 00 xL xH yL yH`(7바이트+8바이트=15바이트) [확인됨·필터출력] | C단계 |
| 푸터 시퀀스 | `1f 11 11`(findpaper, 응답 대기 없음, 3바이트) [확인됨·필터출력] | C단계 |
| 필터 오프라인 실행 가능 여부 | 가능 (`DEVICE_URI=bluetooth:...`로 waitFree 우회) [확인됨] | C단계 |
| PageSize 옵션 (M832.ppd) | A4/Letter/w110h146(110mm×146mm)/w80h106/w53h70 5종 [확인됨·PPD] | A단계 |
| bCmdAfter(`1B 64 01/02`) 발동 조건 | 연속용지 && PageSize가 A4/Letter가 **아닐 때만** — 110mm에서 실측 확인(꼬리 `1b 64 01 1b 64 02 1f 11 11`) [확인됨·소스+필터출력] | B-2 소스 + C단계(110mm) |

> A단계 PPD 행 중 WIDTH_BYTES는 C단계에서 교차검증되어 288byte로 정정됨(불일치 원인은 protocol.md 참고).
> 해상도·ImageableArea·cupsModelNumber 등 나머지 PPD 행은 C단계에서 별도로 재검증되지 않았으며
> 여전히 PPD 문서 선언값(실측 아님)임에 유의.

---

## [2026-09-13] A단계 — 드라이버 패키지 해부

- 보낸 것: 없음 (패키지 추출·PPD 열람만)
- 관찰: `.temp/driver/QY_Printer_Driver_Linux.zip` sha256 `6fc307f5792519d1ab75b4e433c29796b80becc795b020a5723a9d64fd07e9d5` 확인. M832.ppd 존재(`*cupsFilter: application/vnd.cups-raster 0 rastertoM08F`, `*cupsModelNumber: 77832`, `*DefaultResolution: 300dpi`, `Resolution` 줄에 `cupsBitsPerColor 8/cupsRowCount 8/cupsColorSpace 1`). A4 `*ImageableArea "14.17 30 580.83 812"` → (580.83-14.17)/72*300 = 2361.08 dot → ceil(/8) = 296byte. M832D.ppd와의 차이는 이름·번역줄 외에 `LineEnhance`·`PrintMode` 옵션 2개뿐(M832엔 둘 다 없음)
- 결론: [미검증·PPD계산] WIDTH_BYTES 잠정 296byte(기존 CLAUDE.md 가정 310byte와 다름). aarch64용 rastertoM08F 바이너리도 존재 확인(sha256 `431b6e73e66d61c300e350c15bb045adac839bacdfd675524ca13ad2a0e24fea`) → E단계가 필수인 이유는 아키텍처 이식성이 아니라 CLAUDE.md 목표(CUPS/드라이버 비의존)임. B단계로 진행

---

## [2026-09-13] B-1 — 벤더 바이너리·설치스크립트 검증

- 보낸 것: 없음 (file/readelf/ldd/strings 정적 검사만, 바이너리 미실행)
- 관찰: x86_64/rastertoM08F는 PIE ELF, interpreter `/lib64/ld-linux-x86-64.so.2`. `readelf -d` NEEDED에 `libOpenCL.so.1` 없음(사전열람 시 strings 기반 추정은 오탐, 실제 동적 링크 의존성 아님). `ldd`에서 `libcupsimage.so.2 => not found`만 유일한 미해결 — Ubuntu 24.04는 `libcupsimage2t64` 패키지로 해결 예정(C단계). strings에 네트워크 호출 흔적 없음(`socket:`은 OpenCV 심볼명 옆의 DEVICE_URI 문자열 비교 상수, `http(s)://`는 전부 OpenCV 라이브러리 자체의 github issue 안내 문자열). aarch64 바이너리도 동일 인터프리터 계열, ld-linux-aarch64.so.1
- 결론: [확인됨] 실행 가능 판단 — install/qyInstall 미실행 원칙 유지, C단계에서 libcupsimage2t64만 설치하면 로드 가능할 것으로 판단(ocl-icd-libopencl1은 실제로는 불필요해 보이나 설치해도 무해하므로 계획대로 진행)

---

## [2026-09-13] B-2 — 필터 소스 지도 (docs/filter-source-map.md)

- 보낸 것: 없음 (rastertoM08F.cxx 15,015줄 정적 분석만)
- 관찰: `skipAsk` 참조 6곳 중 M832 실사용 게이트는 12725 하나뿐(`waitFree()`+용지/커버 폴링 루프를 감쌈). `DEVICE_URI`에 `bluetooth:` 포함 시 `skipAsk=1`(14033-14036)이 되어 이 블록 전체를 건너뜀 — M832 경로에서 대기를 유발하는 다른 호출은 없음(작업 종료부의 GetPaperStatus는 Q302 전용). 압축 On 대상 목록(S821/M04S/P832Pro/Q302&&isQ302/S822)에 M832 없음 → 항상 Off. bCmdBMP 이후 트레일러는 연속용지+비A4/Letter일 때만 `1B 64 01/02`가 붙고 A4/Letter는 생략, 마지막엔 무조건 응답 대기 없이 `1F 11 11` 1회. 비트 극성은 OutputLine case M832(gray<=128→1, MSB-first, 반전 없음; TSPL 케이스만 `~`로 반전)
- 결론: [확인됨·소스] `DEVICE_URI=bluetooth://offline` 오프라인 실행 트릭이 M832 경로의 유일한 블로킹 지점(waitFree)을 정확히 우회함. C단계 실측과 100% 일치(아래 C단계 참고)

---

## [2026-09-13] C단계 — 필터 오프라인 실행 (t1~t4)

- 보낸 것: 없음 (`cupsfilter -p M832.ppd`로 변환한 A4 PNG 4종을 `rastertoM08F`에 `DEVICE_URI=bluetooth://offline`로 입력, captures/filter/t{1..4}.ras)
- 관찰: t1(백색)·t2(흑색)·t4(가로선)는 즉시 종료(exit 0), 모두 1,003,410byte 동일 크기. **t3(모서리 사각형)만 최초 실행에서 30초 타임아웃(exit 124, 999,424byte)됐으나 즉시 재시도 시 1.2초 만에 정상 종료, stderr 로그 tail 완전 동일** — 원인 불명의 1회성 비결정적 지연으로 재현 안 됨. 헤더 `1f 11 0b` `1f 11 35 00` `1d 76 30 00 20 01 9c 0d`(xL=32,xH=1→288byte, yL=156,yH=13→3484줄) → 비트맵 1,003,392byte → 푸터 `1f 11 11`. t1 vs t2 완전 동일 크기(비압축 확정), t1 vs t3 첫 차이가 오프셋15(비트맵 시작)에서 `0x00`→`0xff`(1=검정 확정)
- 결론: [확인됨] WIDTH_BYTES=288(A단계 PPD 추정 296과 불일치, 원인은 cupsfilter의 이미지 배치 스케일링 — docs/protocol.md 참고), HEIGHT_LINES=3484(연속용지 A4 높이 패딩, B-2 소스 예측과 정확히 일치), 압축 Off, 1=검정. 필터 오프라인 실행 가능 확정. 통과 조건 충족 → 1단계(실제 USB 필요)로 진행하려면 0-b(usbipd, Windows 관리자 PowerShell) 필요 — 여기서 중단하고 사용자 확인 대기

---

## [2026-09-13] 0-b — USB 패스스루·lsusb 확인

- 보낸 것: 없음 (읽기만)
- 관찰: Windows `usbipd list` → BUSID 4-4, VID:PID `0483:5740`, DEVICE명 "M832". `usbipd bind/attach --wsl` 후 WSL `lsusb`: `Bus 001 Device 002: ID 0483:5740 STMicroelectronics Virtual COM Port`
- 결론: [확인됨] VID:PID = 0483:5740. reference의 M02(0493:b002, MAG Technology, Printer class 복합장치)와 벤더·장치유형이 다름 — "Virtual COM Port"라는 lsusb 설명은 CDC-ACM 인터페이스만 보이는 경우의 전형적 문자열이나, bInterfaceClass가 실제로 7(Printer)인지 255(Vendor)인지는 1단계에서 확정 필요. M02와 같다고 가정하지 말 것(CLAUDE.md 금지 2)

---

## [2026-09-13] 1단계 — 장치 지문 뜨기

- 보낸 것: 없음 (디스크립터 읽기만, `src/04_probe.py`, sudo로 재실행해 문자열/커널드라이버 필드 보완)
- 관찰: `iManufacturer: 'Jieli Technology'`, `iProduct: 'USB Composite Device'`, `iSerialNumber: '1234567890ABCDEF'`(고정값으로 보임). 컨피그레이션 1개, 인터페이스 1개뿐(Interface 0, bInterfaceClass=0x07 Printer, bInterfaceSubClass=0x01, bInterfaceProtocol=0x02 양방향) — CDC-ACM 등 추가 인터페이스 없음(M02와 달리 진짜 단일 Printer-class 장치로 보임). 엔드포인트: BULK OUT 0x02, BULK IN 0x81, 둘 다 wMaxPacketSize=64. `is_kernel_driver_active`=False. 전체 출력은 `docs/device-descriptor.md`
- 결론: [확인됨] 클래스 7(Printer) → CUPS usb 백엔드로 D단계 인식 가능성 높음. wMaxPacketSize=64는 USB Full-Speed 벌크 표준값. lsusb의 "Virtual COM Port" 문자열은 실제 기능과 무관한 칩 벤더(Jieli) SDK의 범용 디스크립터 이름으로 보임 — bInterfaceClass 7이 실제 근거. D단계로 진행하되, 래스터 전송은 용지 장착 확인 후에만(CLAUDE.md 금지 5)

---

## [2026-09-13] 용지 확인 — A4 아닌 110mm 폭 장착 (D단계 진입 전 재검증)

- 보낸 것: 없음 (오프라인 필터 재실행만, 실제 프린터 무관)
- 관찰: 사용자가 실제 장착한 용지는 A4가 아니라 **110mm 폭**. `M832.ppd`를 다시 확인하니 `A4/Letter/w110h146(110mm×146mm)/w80h106/w53h70` 5개 PageSize 옵션이 있었음(A단계에서 A4만 보고 넘어간 게 누락이었음). `-o PageSize=w110h146`로 재변환·필터 실행 결과: WIDTH_BYTES=163byte(1300~1304dot), HEIGHT_LINES은 A4처럼 고정 패딩되지 않고 실제 이미지 높이 그대로(1724~1725). 압축 Off·1=검정 동일. 꼬리에 `1b 64 01`+`1b 64 02`가 추가로 붙음(A4/Letter에서는 안 붙던 bCmdAfter — PageSize가 A4/Letter가 아니면 발동한다는 B-2 소스 예측과 정확히 일치)
- 방법론 실수 기록: A4용 2480×3508 소스 이미지를 그대로 w110h146에 통과시켰더니 cupsfilter의 리스케일 과정에서 t3(모서리 사각형)가 통째로 잘려 t1/t3/t4 `.ras`가 완전히 동일해지는 문제 발생(md5 동일로 확인). 1300×1724px로 해당 매체 전용 이미지를 새로 만들어 재실행 후 정상적으로 차이 확인됨. 매체 크기를 바꿀 때는 그 매체 실제 치수에 맞는 이미지를 새로 만들어야 함(다른 매체용 이미지 재사용 금지)
- 결론: [확인됨] **이번 인쇄에 적용할 WIDTH_BYTES는 288이 아니라 163**. `src/06_generate.py`·`src/07_print_image.py`는 A4(288) 기준으로 작성돼 있어 그대로 쓰면 안 됨 — 110mm 폭(163byte)에 맞춰 파라미터를 바꾸거나 재검증 후 D/E단계 진행 필요

---

## [2026-09-13] D단계 — CUPS 실제 인쇄 (실물 확인) ★첫 실물 인쇄 성공★

- 보낸 것: `lp -d M832 -o PageSize=w110h146 captures/filter/w110h146/t3n_corner.png` (CUPS 큐 → PPD → `rastertoM08F` 필터 → usb 백엔드 → 실제 프린터. 이번엔 `DEVICE_URI=bluetooth://offline` 우회 없이 진짜 `usb:///M832?...` URI라서 `skipAsk=0` 경로, 즉 실제 용지/커버 상태 폴링 루프가 그대로 실행됨)
- 관찰: `lp` 즉시 accepted(job M832-1), 약 15~20초간 "now printing" 상태 유지 후 에러 없이 idle로 복귀. `/var/log/cups/error_log`에 이 작업 관련 에러 없음, `access_log`에 Create-Job/Send-Document 모두 successful-ok. **사용자가 육안으로 확인: 110mm 용지 모서리에 작은 검정 사각형이 실제로 인쇄됨**
- 결론: **[확인됨·실물]** WIDTH_BYTES=163, 비트 극성 1=검정, 헤더(`1f 11 0b`+`1f 11 35 00`+bCmdBMP)와 꼬리(`1b 64 01`+`1b 64 02`+`1f 11 11`) 전부 실제 하드웨어에서 정상 동작 확인. CLAUDE.md 금지 2("실제로 프린터에 보내서 눈으로 확인한 것만 확인됨")의 기준을 이번에 처음 충족함. D단계 통과 조건 완료. `skipAsk=0`(실제 용지/커버 폴링) 경로도 15~20초 내 정상 종료돼 무한 대기 문제 없음이 실측으로 확인됨(B-2에서 우려했던 지점)

---

## [2026-09-13] E-2 재검증 — 110mm 매체 추가

- 보낸 것: 없음 (순수 파이썬 재현, 프린터 무관)
- 관찰: `src/06_generate.py`를 A4/w110h146 두 매체 모두 지원하도록 일반화. w110h146: 소스 PNG(1300×1724)를 실제 캔버스(1300×1725, ImageableArea pt→dot 변환의 반올림 오차)로 1px 리사이즈, 폭 방향 비트 패딩(1304-1300=4bit, 0으로 확인) 필요. 두 경우 모두 `t3.bin`/`t3n.bin2`와 바이트 단위 완전 일치(PASS)
- 결론: [확인됨] 순수 파이썬 재현이 A4·110mm 두 매체 모두에서 벤더 필터 출력과 100% 동일 — 벤더 드라이버·CUPS 없이 동일 바이트를 만들 수 있음이 이번에 완전히 증명됨(CLAUDE.md 목표 핵심 달성). D단계 실물 인쇄 성공과 결합하면, 이 바이트를 E-1로 직접 전송해도 같은 결과가 나올 것이라는 근거가 강해짐

---

## [2026-09-13] E-1 — pyusb 직접 재현 (실물 확인) ★CUPS/벤더 드라이버 없이 첫 실물 인쇄 성공★

- 보낸 것: `captures/filter/w110h146/t3n.bin2`(D단계와 완전히 동일한 281,199바이트, 모서리 사각형)를 `src/05_replay.py --confirm-paper-loaded`로 pyusb 벌크 전송(4096바이트 청크, EP_OUT 0x02). 전송 직전 `sudo systemctl stop cups`로 usb 백엔드와의 충돌 방지. 보낸 바이트는 `captures/sent/0001.bin`에 저장(CLAUDE.md 금지 3 최초 충족)
- 관찰: `detach_kernel_driver`(원래 비활성이었음) → `set_configuration` → `claim_interface` → 청크 전송 281,199/281,199바이트 성공(재시도·청크축소 없이 한 번에) → `release_interface` 정상. BULK IN 응답은 타임아웃(무응답, 실패로 취급 안 함). **사용자가 육안으로 확인: D단계와 동일한 위치(모퉁이)에 동일한 검정 사각형이 인쇄됨**
- 결론: **[확인됨·실물]** PLAN-01 E-1 통과 조건("D와 같은 출력이 나오면 프로토콜은 확보된 것") 충족. **CUPS·벤더 드라이버·벤더 필터 전혀 없이, 순수 파이썬(pyusb)만으로 M832에 실제 인쇄 성공** — 이 프로젝트의 핵심 목표가 처음으로 실물 검증됨. wMaxPacketSize(64)보다 훨씬 큰 4096바이트 청크로도 문제없이 전송됨(청크 축소 로직 발동 안 함). BULK IN 무응답은 D단계에서도 관찰 안 해봤던 부분이라 [미검증] — G단계의 findpaper 응답 파싱(`08_print_daily.py`의 TODO)에 참고: 최소한 이 전송 흐름(청크 후 응답 대기)에서는 응답이 없어도 인쇄 자체는 정상 진행됨

---

## [2026-09-13] usbipd 연결 끊김 — 재현 가능한 운영 이슈 (하드웨어 결함 아님)

- 보낸 것: 없음
- 관찰: E-1 성공 후 CUPS를 재시작하고 얼마 지나지 않아 `lsusb`에서 M832가 사라짐. Windows `usbipd list` 확인 결과 BUSID 4-4 상태가 "Shared"로 내려가 있었음(= bind는 유지, WSL attach만 끊김). `usbipd attach --wsl --busid 4-4` 재실행으로 즉시 복구(재연결 시 디바이스 번호가 001→003으로 바뀜, 정상적인 재열거)
- 결론: [확인됨] usbipd-wsl 연결은 특히 USB 장치를 반복적으로 열고 닫을 때(CUPS↔pyusb 전환 등) 간헐적으로 끊길 수 있음. 하드웨어·프로토콜 문제 아님. G단계(3일 무인 cron)에서 이 문제가 재현되면 인쇄가 조용히 실패할 수 있으므로, `08_print_daily.py`는 USB 장치를 못 찾을 때 "usbipd 재연결 필요"를 명확히 로그에 남겨야 함(현재 TODO로 반영 필요)

---

## [2026-09-13] usbipd 연결 끊김 — 재발 및 패턴 추정 (사용자 관찰)

- 보낸 것: 없음
- 관찰: 같은 문제가 한 번 더 재현됨. 두 번의 발생 시점을 비교하면 공통점이 있다 — **① E-1(`05_replay.py`) 성공 후 `usb.util.dispose_resources()`로 장치를 놓아준 직후** (그 다음 CUPS를 재시작하려던 시점에 이미 끊겨 있었음), **② E-3(`07_print_image.py`) 정상 종료로 `release_interface`+`dispose_resources`가 실행된 직후**(다음 인쇄 시도에서 장치를 못 찾음). 두 경우 모두 "pyusb로 장치를 claim했다가 정상적으로 release한 직후" 패턴과 일치한다. 사용자 관찰: "디바이스를 열었다가 다시 닫으면 꺼지는 것 같다"
- 결론: **[미검증·패턴추정]** usbipd-wsl(또는 이 특정 프린터의 USB 컨트롤러)가 인터페이스 release/장치 리셋 시점에 USB 재열거(re-enumeration)를 일으켜, Windows 쪽 usbipd가 이를 "연결 해제"로 감지하고 WSL attach 상태를 "Shared"(미부착)로 되돌리는 것으로 추정됨(재부착 시 디바이스 번호가 매번 바뀜 — 001→003→004 — 이는 실제 재열거가 일어나고 있다는 근거). 아직 정확한 트리거(release_interface 자체인지, dispose_resources인지, 아니면 단순히 몇 초 이상 idle이면 그런지)는 미확인. **운영상 결론**: pyusb 스크립트 실행 후 연속으로 또 실행해야 한다면 매번 `lsusb`로 재확인하고 필요시 Windows에서 `usbipd attach --wsl --busid 4-4` 재실행. G단계(무인 운영)에서는 이 패턴이 치명적일 수 있음 — `08_print_daily.py`에 재시도 로직(장치 못 찾으면 수 초 대기 후 재시도, 그래도 안 되면 "usbipd 재연결 필요"로 로그) 추가를 권장

---

## [2026-09-13] usbipd 연결 끊김 — 근본 원인 규명: WSL2 NAT 유휴 타임아웃

- 보낸 것: 없음 (`dmesg -T` 로그 분석)
- 관찰: `dmesg -T`에서 매 disconnect마다 동일한 패턴 확인:
  ```
  vhci_hcd: connection closed
  vhci_hcd: stop threads
  vhci_hcd: release socket
  vhci_hcd: disconnect device
  usb 1-1: USB disconnect, device number N
  ```
  attach부터 disconnect까지 걸린 시간이 72초, 22초로 **일정하지 않음** — 고정 타임아웃이 아니라 유휴 시간에 비례하는 네트워크 계층 타임아웃 패턴과 일치. 최초 attach 로그에 `Detected networking mode 'nat'`가 찍혀 있었음(이전 세션 기록) — usbipd는 Windows→WSL 간 USB 트래픽을 TCP로 터널링하는데, WSL2의 기본 NAT 네트워킹은 유휴 TCP 연결을 일정 시간 후 끊는 것으로 알려져 있음(WSL2/usbipd-win 커뮤니티에 널리 보고된 문제). `C:\Users\Justant\.wslconfig` 확인 결과 기존 설정 없음(기본값 = NAT), WSL 버전 2.6.3.0은 `networkingMode=mirrored`(NAT를 아예 안 씀) 지원
- 결론: **[미검증·조치완료, 재부팅 후 재확인 필요]** `.wslconfig`에 `[wsl2]\nnetworkingMode=mirrored`를 추가함. `wsl --shutdown` 후 재시작하면 이 네트워킹 계층 자체가 바뀌어 usbipd TCP 터널의 NAT 유휴 타임아웃이 사라질 것으로 기대됨. 이것이 근본 원인이 맞다면 G단계(3일 무인 cron) 안정성에 결정적으로 중요함. **재시작 후 실제로 연결이 안 끊기는지 반드시 실측 재확인할 것** — 아직 [확인됨]이 아니라 가설+조치 단계

---

## [2026-09-13] E-3 — 대각선·원 패턴 실물 인쇄 (실물 확인)

- 보낸 것: `07_print_image.py --send --test-pattern diagonal`(`0005.bin`), `--test-pattern circle`(`0006.bin`). 둘 다 기본 `--h-offset-mm 2.0` 적용
- 관찰: **사용자 확인: 대각선은 좌상단→우하단 방향으로 정상 인쇄, 원은 타원이 아닌 정원으로 정상 인쇄됨**
- 결론: [확인됨·실물] PLAN-01 E-3 통과 조건("의도한 도형이 왜곡 없이 출력된다") 3개 패턴(체커보드/대각선/원) 전부 충족. 좌우반전 없음(대각선 방향 정상), 상하좌우 dot 밀도 대칭 확인(원이 타원으로 안 찌그러짐 → 300x300dpi 정사각 dot 가정이 맞음). 텍스트·실사진은 아직 미테스트지만 기하학적 파이프라인(리사이즈·디더링·패킹·전송·정렬보정)은 전부 검증됨

---

## [2026-09-13] E-3 — 체커보드 테스트 패턴 실물 인쇄 (실물 확인) ★전체 이미지 파이프라인 검증★

- 보낸 것: `src/07_print_image.py --send --test-pattern checkerboard` (그레이스케일 생성 없이 흑백 패턴을 직접 그린 뒤 Floyd-Steinberg 없이 1bpp 패킹 → 1304x652dot, 163byte/line, 106,300byte 전체). `captures/sent/0002.bin`에 저장
- 관찰: 전송 즉시 성공(106,300/106,300byte). CUPS는 재시작돼 있었으나(systemd 소켓 활성화로 자동 재기동된 것으로 추정 — `systemctl stop cups`가 영구적이지 않음) 전송에 지장 없었음. **사용자가 육안으로 확인: 체커보드 패턴이 왜곡·반전 없이 정상 인쇄됨**
- 결론: **[확인됨·실물]** PLAN-01 E-3 통과 조건("의도한 도형이 왜곡 없이 출력된다") 첫 패턴(체커보드) 충족. 비트 극성(`--invert` 미사용, 기본 1=검정) 정상, 방향·좌우반전 문제 없음. 대각선·원·텍스트·실사진은 아직 미테스트
- **운영 메모**: `systemctl stop cups`가 소켓 활성화 때문에 일시적일 수 있음이 재확인됨 — pyusb 전송 직전에는 매번 `systemctl is-active cups`로 재확인하는 습관이 필요

---

## [2026-09-13] E-3 — 수평 정렬 보정(`--h-offset-mm`) 실측

- 보낸 것: `07_print_image.py --send --test-pattern checkerboard --h-offset-mm 2.0` — 콘텐츠를 벤더 PPD의 `AdjustHoriaontal`과 동일한 방식(캔버스 내 좌우 이동, 전송 폭은 불변)으로 오른쪽으로 24dot(2mm) 이동. `captures/sent/0004.bin`
- 관찰: 보정 전(오프셋 0mm)은 왼쪽 여백 ~2mm·오른쪽 여백 0mm. **오프셋 +2mm 적용 후: 왼쪽 ~1mm·오른쪽 ~1mm로 대칭화됨.** 한쪽으로 완전히 없어지지 않고 양쪽에 분산된 것으로 보아, 정렬 오차만이 아니라 **현재 폭 설정(1304dot=163byte, ≈110.5mm)이 실제 인쇄 가능 폭보다 총 ~2mm 정도 넓게 잡혀 있음**을 시사함
- 결론: [확인됨·실물] `--h-offset-mm`이 의도대로 동작함(양수=오른쪽 이동, 벤더 소스의 `nj = j + hOffset`과 동일 방향). +2mm에서 좌우 대칭 각 ~1mm로 실용적으로 양호. 완전히 0으로 만들려면 폭 자체를 ~24dot(163→약 160byte) 줄이는 시도가 필요하나, 이 프로젝트(개인용 라벨/사진 인쇄 PoC)에는 대칭 1mm 여백으로 충분하다고 판단 — **`--h-offset-mm` 기본값을 2.0으로 확정**(사용자 결정). 이제 옵션 없이 실행해도 자동 적용됨. 0으로 override 가능(다른 매체·다른 개체 프린터 재보정용)

---

## [2026-09-13] 업스트림 기여 (phomemo-tools PR #51)

- 보낸 것: 프린터에는 아무것도 안 보냄(오프라인 검증만). `vivier/phomemo-tools`에 `cups: add M832 driver` PR(https://github.com/vivier/phomemo-tools/pull/51, 브랜치 `feature/add-M832`; 같은 커밋의 #50은 이름 변경으로 대체·종료) — 새 `.drv` + `rastertopm832.py` + 등록 3곳 + README, 커밋 `a3257ad`, 작업 클론 `~/Data/phomemo-tools-m832`
- 관찰: 새 필터 출력이 실물 검증된 `captures/filter/w110h146/t3n.bin2`와 겹치는 비트맵 16,300바이트 중 차이 0, A4는 3508줄 패딩+3바이트 꼬리 확인. 검증 중 `cupsPageSizeName`에 null 뒤 잔여 바이트(`'A4\x00ter'`)가 섞여 오는 CUPS 쪽 문제를 발견해 필터에서 첫 null 앞만 쓰도록 처리
- 결론: [확인됨·오프라인] 110mm 롤 경로는 벤더 출력과 비트맵 동일. A4/Letter/80mm/53mm는 [미검증·실물]로 PR에 명시. 상세는 `.temp/UPSTREAM-01.md`

---

---

## [2026-09-17 07:22] V2 — BT 서비스 탐색 (서버 세션, 페어링 없이 SDP만)

- 보낸 것: 없음 (`bluetoothctl scan on`, `sdptool browse C5:0D:F7:B7:B2:A1` — 조회만, 프린터로 바이트 전송 없음)
- 관찰: MAC `C5:0D:F7:B7:B2:A1`, 이름 `M832`, Class 0x00140680(Icon: printer)로 스캔에 잡힘 — `.temp/01-orangepi-poc-작업지시서-v1.2.md` 기기 대장의 1호기(Q253E6831170035)와 MAC 일치. SDP 조회 결과 서비스 레코드 1개: `Service Class ID List: "HCR Print" (0x1126)`, `Protocol: L2CAP PSM 4107`, `Profile: Hardcopy Cable Replacement (0x1125) v0x0100`. **Classic SPP(RFCOMM)이 아니라 HCRP(L2CAP 직결)를 광고한다.**
- 결론: [확인됨·실물] init_plan.md의 "같은 계열(M04S/M834)은 SPP/BLE [추정]"은 M832에는 맞지 않는다 — M832는 HCRP다. 다음 단계는 L2CAP PSM 4107로 소켓을 열어 이미 검증된 `captures/sent/0002.bin`(체커보드, USB로 인쇄 확인됨)을 그대로 써보는 것 — HCRP가 세션 핸드셰이크 없이 원시 데이터를 그대로 받는지, 아니면 별도 프로토콜 레이어가 있는지는 아직 [미검증]

---

## [2026-09-17] V2 — 페어링 성공, SPP UUID도 노출됨

- 보낸 것: `bluetoothctl pair C5:0D:F7:B7:B2:A1` — 페어링 요청뿐, PIN 없이 성공(Just Works로 추정)
- 관찰: 페어링 성공 후 `Bonded: yes`, `Paired: yes`. 이전(미인증) `sdptool browse`에서는 안 보이던
  `UUIDs: 00001101-...`(SPP, Serial Port Profile)가 `00001126-...`(HCR Print)와 함께 나타남.
  즉 M832는 HCRP뿐 아니라 **SPP도 지원**하며, 미인증 SDP 조회는 서비스 목록을 일부만 보여준 것으로 보임
- 결론: [확인됨·실물] init_plan.md의 "같은 계열은 SPP [추정]"이 완전히 틀린 건 아니었다 — HCRP·SPP 둘 다 있다.
  SPP가 RFCOMM 기반 단순 시리얼 파이프라 USB bulk-out과 의미상 더 가까울 가능성이 높음. 다음은 SPP의
  RFCOMM 채널 번호를 조회하고, 페어링된 상태로 HCRP L2CAP(PSM 4107) 재시도 — 앞서 미페어링 상태에서는
  L2CAP connect가 `EPERM`(Permission denied)으로 거부됐음(root로 실행해도 동일 — 링크 레벨 인증 문제로 추정)

---

## [2026-09-17] V2 — SPP(RFCOMM) 채널 확인: 채널 1, 서비스명 JL_SPP

- 보낸 것: 없음 (`sdptool search SP` — SDP 조회만)
- 관찰: `sdptool browse`(전체 브라우즈)에는 안 잡히던 SPP 레코드가 `sdptool search SP`(타깃 조회)로는
  잡힘. `Service Name: JL_SPP`, `Service Class: "Serial Port"(0x1101)`, `Protocol: RFCOMM Channel 1`.
  "JL"은 JieLi 계열 BT 칩셋에서 흔한 접두어로, 단순 시리얼 패스스루로 추정됨
- 결론: [확인됨·실물] SPP/RFCOMM 채널=1. HCRP(L2CAP PSM 4107, 페어링 안 된 상태에서 EPERM)보다
  프로토콜이 단순하고 USB bulk-out과 의미상 더 가까워 보임 — 다음 실험은 RFCOMM 채널 1로
  검증된 체커보드 바이트(0002.bin) 전송
