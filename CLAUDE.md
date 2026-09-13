# Phomemo M832 프로토콜 리버싱

> Claude Code는 항상 `~/Data/detox-printer`(이 파일이 있는 위치)에서 실행된다.
> 실제 코드/실험 대상은 `m832/` 하위 디렉터리이며, `reference/`는 읽기 전용 참고자료(vivier/phomemo-tools 클론)다.

## 이 프로젝트의 목표

M832에 임의의 텍스트/이미지를 출력하는 **최소한의 파이썬 코드**를 확보한다.
최종 타깃은 Orange Pi Zero 2W에 프린터를 붙이고 cron으로 매일 정해진 시각에
자동 출력시키는 것이다. 지금은 그 전 단계인 **프로토콜 확보 PoC**다.

따라서 코드는 처음부터 다음을 만족해야 한다.

- 순수 파이썬 + pyusb만 사용. CUPS / 프린터 드라이버 / GUI 의존성 금지
  (단, PLAN-01 A~D단계에서 벤더 드라이버·CUPS를 **분석 도구**로 쓰는 것은 허용. E단계 이후 최종 코드에는 의존 금지)
- x86 WSL에서 짠 코드가 ARM SBC에서 그대로 돌아갈 것
- 외부 네트워크 의존 없음

## 확정된 사실 (추측으로 덮어쓰지 말 것)

**하드웨어**
- Phomemo M832, 300 x 300 DPI. PPD(M832.ppd)는 A4/Letter/**w110h146(110mm×146mm)**/w80h106/w53h70 5개 PageSize 지원
- USB-C로 PC 직결 중, Bluetooth도 지원하나 이번 PoC에서는 USB만 사용
- **WIDTH_BYTES는 PageSize에 종속된 값이지, 고정 하드웨어 상수가 아니다.** 매체를 바꾸면 반드시 재확인한다
  - A4: WIDTH_BYTES=288byte(2304dot), HEIGHT_LINES=3484(고정 패딩) — ~~이론값 310byte/2480dot~~는 A·C단계로 반증됨
  - **110mm(w110h146) — 현재 실제 장착 용지**: **WIDTH_BYTES=163byte(1300dot)**, HEIGHT_LINES은 고정 패딩 없이 실제 이미지 높이 그대로. 꼬리에 `1B 64 01`+`1B 64 02`(bCmdAfter)가 추가로 붙음(A4/Letter는 안 붙음)
  - (C단계 `rastertoM08F` 실제 출력의 `bCmdBMP` xL/xH 실측값. `m832/docs/protocol.md` 참고)

**프로토콜 (C단계·1단계로 확정, 110mm은 D단계 실물 인쇄로 최종 확인됨)**
- 명령 체계는 ESC/POS가 아니라 `1F 11 xx` 계열 + 래스터 블록 `1D 76 30 00 xL xH yL yH`(bCmdBMP)
- 압축 없음(raw bitmap 확정, `1F 11 35 00`)
- 벤더 필터: `rastertoM08F` (cupsModelNumber 77832), 필터 입력은 `cupsColorSpace 1`(RGB) `cupsBitsPerColor 8`
- 벤더 드라이버는 x86_64/i386/aarch64/arm/armhf 전부 존재(aarch64 포함) — E단계가 필요한 이유는 아키텍처 이식성이 아니라 이 프로젝트 목표(CUPS/드라이버 비의존) 때문
- USB: VID:PID `0483:5740`, 인터페이스 0 하나(Printer class 7, SubClass 0x01, Protocol 0x02 양방향), BULK OUT `0x02` / BULK IN `0x81`, 둘 다 `wMaxPacketSize=64`
- **[확인됨·실물] 110mm 용지에 모서리 사각형 실제 인쇄 성공** (D단계: CUPS+벤더필터 경로, E-1: 순수 파이썬 pyusb 경로 — 둘 다 동일한 결과. `m832/docs/findings.md` 참고) — WIDTH_BYTES=163·1=검정·헤더/꼬리 구조가 실제 하드웨어에서 검증됨. A4 값(288byte)은 아직 필터 출력만 확인됐고 실물 인쇄로는 검증되지 않음(현재 A4 용지 미장착)
- **[확인됨·실물] 프로젝트 핵심 목표 달성: CUPS·벤더 드라이버 완전히 없이 순수 파이썬(pyusb)만으로 M832 인쇄 성공** (`src/05_replay.py`, `captures/sent/0001.bin`). `src/06_generate.py`도 A4·110mm 둘 다 벤더 필터 출력과 바이트 단위 완전 동일 재현(PASS)
- **[확인됨·실물] `src/07_print_image.py`(임의 이미지 인쇄 파이프라인) 완성·검증** — 체커보드·대각선·원 3종 실물 인쇄 성공(왜곡·좌우반전 없음, 정원 확인). `--h-offset-mm` 기본값 **2.0으로 확정**(실측: 원래 좌측 2mm 여백/우측 0mm → +2mm 보정 후 좌우 대칭 각 1mm. 완전 0으로 만들려면 폭을 24dot 추가로 줄여야 하나 이 프로젝트엔 충분하다고 판단해 보류)

**환경 이슈 (usbipd-wsl 연결 끊김)**
- pyusb로 USB 장치를 claim/release할 때마다(특히 CUPS↔pyusb를 오갈 때) usbipd-wsl 연결이 간헐적으로 끊기는 문제 재현됨(`dmesg`에 `vhci_hcd: connection closed`). attach 후 끊기기까지 시간이 22~72초로 일정치 않아, **WSL2 기본 NAT 네트워킹이 usbipd TCP 터널을 유휴 타임아웃으로 끊는 것**으로 추정
- 조치: `C:\Users\Justant\.wslconfig`에 `[wsl2]\nnetworkingMode=mirrored` 추가(NAT 자체를 안 씀). **`wsl --shutdown` 재시작 후 실측 재확인 필요** — 아직 [미검증·조치완료]. G단계(무인 cron) 안정성에 직결되는 사안이므로 재확인 전까지 G단계 착수 금지

**참고 레포**
- `reference/` = vivier/phomemo-tools 클론
- 이 레포가 **공식 지원하는 모델은 M02 / M02 Pro / M02S / M110 / M120 / M220 / T02 뿐이며
  M832는 지원 목록에 없다**
- 레포 코드는 203dpi / 384dot(48byte) 계열 기준이다.
  폭 상수, 초기화 시퀀스, 청크 크기를 **그대로 가져다 쓰면 안 된다**
- 참고할 값은 명령어 구조뿐: 초기화 `1b 40`, 래스터 블록 `1d 76 30`, 피드 `1b 64`

**환경**
- Windows 11 + WSL2 Ubuntu, VSCode에서 작업
- USB는 `usbipd-win`으로 WSL에 attach한 상태여야 동작함
- WSL2 커널에 `usblp` 모듈이 없을 가능성이 높음
  → `/dev/usb/lp0` 리다이렉트 방식에 의존하지 말 것. **pyusb 벌크 전송이 기본**
- 작업 루트(코드/실험 대상): `~/Data/detox-printer/m832`

## 절대 금지

1. `reference/` 디렉터리 수정 금지. 읽기 전용 참고자료다.
2. **M02에서 되니까 M832에서도 될 것이라고 가정하지 말 것.**
   실제로 프린터에 보내서 눈으로 확인한 것만 "확인됨"이다.
   나머지는 전부 `m832/docs/findings.md`에 `[미검증]`으로 표시한다.
3. 프린터에 보낸 바이트는 예외 없이 `m832/captures/sent/`에 `.bin`으로 저장한다.
   재현 불가능한 실험은 하지 않는다.
4. 실패했는데 성공한 것처럼 요약하지 말 것. 무반응이면 무반응이라고 쓴다.
5. 용지가 장착되지 않은 상태에서는 래스터(인쇄) 명령을 보내지 않는다. 헤드가 상한다.
6. 토큰 최적화 / 컨텍스트 압축 / 리팩터링 계열 스킬을 자동으로 호출하지 말 것.
   CLAUDE.md와 m832/docs/findings.md는 축약 대상이 아니다.
   src/ 의 번호 붙은 스크립트를 통합하거나 중복 제거하지 말 것.

## 실험 기록 규칙

모든 실험은 끝나자마자 `m832/docs/findings.md` 맨 아래에 이 형식으로 append한다.
길게 쓰지 말고 3줄로 끝낸다.

```
## [2026-09-13 14:32] 실험명
- 보낸 것: 1b 40 1d 76 30 00 30 01 18 00 + 0xFF * 1152  (captures/sent/0007.bin)
- 관찰: 종이 약 8mm 이송, 출력 없음. 3초 뒤 STALL
- 결론: [미검증] 폭 304byte는 버퍼 초과로 보임. 다음은 216byte로 재시도
```

## 코드 규칙

- 스크립트는 `m832/src/NN_이름.py` 형식, 번호는 실행 순서
- 모든 USB write는 타임아웃을 명시하고, 실패 시 예외를 삼키지 말고 그대로 출력
- 하드코딩한 상수 옆에는 반드시 근거 주석을 단다
  (`WIDTH_BYTES = 163  # 110mm(w110h146) 용지 C단계 bCmdBMP 실측값(A4는 288, 매체마다 다름). m832/docs/protocol.md 참고`)
- 새 실험 스크립트를 만들 때 이전 스크립트를 덮어쓰지 말고 새 번호로 추가한다.
  실패한 코드도 남긴다. 뭘 이미 시도했는지가 이 프로젝트의 자산이다.

## 진행 방식

`m832/.temp/PLAN-01.md`의 단계를 순서대로 진행한다.
각 단계에는 통과 조건이 있다. **통과 조건을 만족하기 전에 다음 단계로 넘어가지 않는다.**
막히면 추측으로 진행하지 말고 멈추고 물어본다.
