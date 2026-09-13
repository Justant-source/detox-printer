# PLAN-01 — 공식 Linux 드라이버 기반 접근

> 이 문서는 폐기된 구 m832/PLAN.md(0~6단계)를 **대체**한다.
> 파일은 m832/.temp/에 있지만 모든 상대경로는 m832/ 기준이다. Claude Code는 레포 루트에서 실행된다. venv는 m832/.venv.
> 모든 bash 블록은 첫 줄 `cd ~/Data/detox-printer/m832`로 시작하고, 블록 안에서 추가 `cd`를 하지 않는다.
> 각 단계는 통과 조건을 만족해야 다음으로 넘어간다. 새 사실은 즉시 docs/findings.md에 기록하고, 단계 종료 시 커밋 여부를 사용자에게 묻는다.
> `[미검증·사전열람]`/`[미검증·소스기반]` 표기는 계획 수립 시 읽기만 한 값이다. 해당 단계에서 직접 재확인해야 "확인됨"이 된다.

> **현재 상태 (2026-09-13, 최신)**: 0-a·A·B(B-1+B-2)·C·0-b·1단계·D단계·E-1·**E-2·E-3 전부 완료(전부 실물 인쇄 성공, 110mm 용지)**. **CUPS·벤더 드라이버 없이 순수 파이썬(pyusb)만으로 M832 인쇄 — 프로젝트 핵심 목표 실물 달성.**
>
> - 매체: 사용자 실제 장착 용지는 A4 아닌 110mm(w110h146) — WIDTH_BYTES=163(A4는 288, 매체 종속값)
> - `src/06_generate.py`: 벤더 필터 출력을 순수 파이썬으로 바이트 단위 완전 재현, A4·110mm 둘 다 PASS
> - `src/07_print_image.py`: 임의 이미지→그레이스케일→디더링→패킹→전송 전체 파이프라인 완성. 체커보드·대각선·원 3종 전부 실물 인쇄 성공(왜곡·반전 없음, 정원 확인 → 300x300dpi 정사각 dot 가정 검증됨). **`--h-offset-mm` 기본값 2.0으로 확정**(실측 보정: 원래 좌측 2mm 여백/우측 0 → +2mm 적용 후 좌우대칭 각 1mm. 완전히 0이 안 되는 건 현재 폭(1304dot)이 실제 인쇄가능폭보다 총 ~2mm 넓기 때문 — 원하면 폭을 24dot 줄여 추가 개선 가능, 현재는 충분하다고 판단해 보류)
> - `src/05_replay.py`: 110mm 실전송 성공(`captures/sent/0001.bin`)
> - **운영 이슈 발견 및 조치**: usbipd-wsl이 USB 장치 claim/release 반복 시 간헐적으로 연결이 끊김(재현 3회+). `dmesg` 분석으로 근본 원인 규명 — WSL2 기본 NAT 네트워킹이 usbipd의 TCP 터널을 유휴 타임아웃으로 끊는 것으로 추정. `C:\Users\Justant\.wslconfig`에 `networkingMode=mirrored` 추가로 조치했으나 **`wsl --shutdown` 재시작 후 실측 재확인 필요**(아직 [미검증·조치완료] 상태)
>
> 남은 것: F단계(불필요해 보임 — 스니핑 없이 이미 프로토콜 완전 확보), G단계(cron — `08_print_daily.py`의 용지확인 TODO 미확정 상태로 여전히 인쇄 안 하게 안전하게 막혀 있음, findpaper 응답 포맷 확정 필요 — E-1에서 BULK IN 무응답 관찰했었음), 텍스트/실사진 테스트(선택사항, 기하학적 파이프라인은 이미 검증 완료). **다음 단계는 WSL 재시작 후 usbipd 안정성 재확인부터.** 확정 사실은 CLAUDE.md·docs/findings.md·docs/protocol.md·docs/filter-source-map.md 참고.

---

## 1. 왜 계획을 바꾸는가

Phomemo가 M832용 Linux 드라이버(`QY_Printer_Driver_Linux.zip`, Ubuntu/CentOS7)를
공식 배포하고 있다는 것이 확인됐다. 이건 거의 확실히 **CUPS 드라이버**다.
CUPS 드라이버는 두 조각으로 되어 있다.

- **PPD 파일** — 해상도, 용지 크기, 인쇄 가능 영역이 텍스트로 적힌 명세서
- **필터 바이너리** — CUPS 래스터를 stdin으로 받아 프린터 바이트를 stdout으로 뱉는 실행 파일

중요한 건 **필터가 독립 실행 파일이라는 점**이다. 프린터 없이, CUPS 없이,
셸에서 직접 돌려서 출력 바이트를 파일로 받을 수 있다.
즉 **정답지를 먼저 읽고 나서 재현하는** 순서가 가능해졌다.

그리고 이번엔 한 걸음 더 나갔다: 배포된 zip에는 필터의 **C++ 소스까지 동봉되어 있다**.
바이너리를 실행해 보기 전에 소스를 먼저 읽을 수 있다는 뜻이다. `c/rastertoM08F.cxx`를
계획 단계에서 메모리로만(디스크에 풀지 않고) 열람한 결과가 아래 2절에 정리돼 있으며,
그 결과 구 PLAN-02의 여러 전제가 틀렸다는 것도 이미 밝혀졌다(대표적으로 "x86_64만 있으면
Orange Pi에서 못 돈다" — 실제로는 aarch64 바이너리도 존재한다).

---

## 2. 패키지 사전 열람 결과

> 아래는 전부 계획 수립 단계에서 **메모리로만** 읽은 결과다. 소스 줄번호는 직접 확인했지만,
> 실행 단계에서 재확인하기 전까지는 `[미검증·사전열람]`(PPD/패키지 관련) 또는
> `[미검증·소스기반]`(소스 관련)으로 취급한다.

### 패키지 구조 `[미검증·사전열람]`

- zip sha256 `6fc307f5792519d1ab75b4e433c29796b80becc795b020a5723a9d64fd07e9d5`, 내부에는
  `QY_Printer_Driver_Linux/QY_Printer-2.1.0.3.tar.gz` 1개(중첩 구조)만 있다. tar를 풀면 최상위가
  `QY_Printer-2.1.0.3/`.
- 구성: `ppds/*.ppd` 75개(gzip 아님, 평문), `x86_64/ i386/ aarch64/ arm/ armhf/` 각 아키텍처 디렉터리에
  `rastertoM08F` · `rastertolabelmxxx` · `rastertoD480` · `qyInstall` · `qyUninstall`,
  `c/`에 **필터 소스**(`rastertoM08F.cxx` 15,015줄, OpenCV+miniLZO 포함; `qyInstall.c` 등),
  루트에 `install` · `uninstall` · `linux`(벤더 빌드 스크립트). **`install.sh`라는 파일은 없다** —
  실행 스크립트 이름은 `install`이다. tar 원본 안에 0777 권한 항목이 있다.
- `install` 스크립트의 동작(읽은 내용, 실행하지 않음): root 권한 필수, 기존
  `/usr/local/share/qy/printer/uninstall`이 있으면 먼저 실행, 추출 디렉터리에
  `chown -R root:root ./*`, 필터 3종을 CUPS filter 디렉터리로 복사, PPD 전부를 `<model>/qy/`로 복사,
  `chmod 4755 /usr/local/share/qy/printer`, `qyInstall`(IPP로 큐 생성·활성화) 실행, CUPS 재시작.
  → 이 스크립트는 어떤 단계에서도 실행하지 않는다.
- ELF NEEDED (`x86_64/rastertoM08F`): `libOpenCL.so.1 libc.so.6 libcups.so.2 libcupsimage.so.2 libdl.so.2
  libgcc_s.so.1 libm.so.6 libpthread.so.0 libstdc++.so.6 libz.so.1` (aarch64 빌드는 `libz` 없이 링크됨).
  Ubuntu 24.04 기본 상태에는 `libcupsimage2t64`·`ocl-icd-libopencl1`이 미설치라, cups 패키지만 깔면
  필터가 로드되지 않는다.
- **aarch64용 필터가 실제로 존재한다** → 구 PLAN-02의 "x86_64 바이너리뿐이면 Orange Pi에서 못 돈다 →
  E단계가 필수"라는 논리는 **틀렸다**. E단계가 필요한 진짜 이유는 CLAUDE.md의 목표(순수 파이썬+pyusb,
  CUPS·벤더 드라이버 비의존)이지, 아키텍처 이식성 문제가 아니다.

### M832.ppd `[미검증·사전열람]`

- `*cupsFilter: "application/vnd.cups-raster 0 rastertoM08F"`, `*cupsModelNumber: 77832`,
  `*DefaultColorSpace: Gray`.
- `*DefaultResolution: 300dpi`. Resolution 줄에 `cupsBitsPerColor 8` / `cupsRowCount 8` /
  `cupsColorSpace 1` → 필터 입력은 **RGB 8bit**다 (소스 14101행에서 `cupsColorSpace == 1`이면
  픽셀당 3바이트로 읽는다).
- A4: `*PaperDimension "595 842"`, `*ImageableArea "14.17 30 580.83 812"` →
  가로 `(580.83 - 14.17) = 566.66pt` → `566.66/72*300 = 2361.08 dot` → **296 byte 잠정**.
  Letter: `*ImageableArea "14.17 30 597.83 762"` → 2432 dot → 304 byte.
- 옵션 기본값: `Darkness=Default`, `ColorOption=GrayScale`, `DegreeOfBlackRecognition=4`,
  `DegreeOfGrayRecognition=7`, `AdjustHoriaontal=0`(PPD 원문 오타 그대로), `AdjustVertical=0`,
  `Rotate=0`, `zeMediaTracking=Continuous`. `LineEnhance` 옵션은 `M832D.ppd`에만 있다
  — M832와 M832D의 차이는 이름·`LineEnhance`·번역 줄뿐이다.

### `c/rastertoM08F.cxx` M832 경로 앵커 `[미검증·소스기반]`

계획 시점 줄번호. 실행 시에는 심볼/문자열로 재검색해서 재확인한다.

| 줄 | 내용 |
|---|---|
| 11315 | `#define M832 77832` |
| 11347–11363 | `bCmdDensity {1F 11 02 06}`, `bCmdSpecial {1F 11 37 96}`, `bCmdBMP {1D 76 30 00 xL xH yL yH}`(11349), `bCmdCompressionOn {1F 11 35 01}`, `bCmdCompressionOff {1F 11 35 00}`, `findpaper {1F 11 11}`, `askSn {1F 11 09}`, `bCmdGap {1F 11 PAPER_*}`, `bCmdAntiwrinkling {1F 11 88 02}`, `bCmdAfter {1B 64 02}`(11363) |
| 11905–11935 | `getHardVer()`: `1F 11 07` 질의를 응답 올 때까지 `while(1)` |
| 12037–12072 | `waitFree()`: M832면 `getHardVer()` 먼저, hardver<0x10005면 `GetCoverStatus()` 후 반환, 아니면 `1F 11 43` 반복 전송+`cupsBackChannelRead` 대기 |
| 12080 | `compressBitmap()` (miniLZO) |
| 12107 | `StartPage()` |
| 12724–12755 | StartPage `case M832`: `skipAsk == 0`일 때만 `waitFree()` + 커버/용지 상태 루프(용지 확인될 때까지 무한) |
| 13405–13432 | OutputLine `case M832`: gray ≤ 128이면 비트 1, MSB-first(`128>>j`), `~` 반전 없음 → **1=검정** |
| 14033–14037 | `DEVICE_URI`에 `bluetooth:` 포함 시 `skipAsk = 1` — **오프라인 실행의 유일한 대기 우회로** |
| 14043–14046 | `DEVICE_URI`에 `socket:` 포함 시 `isSocket=1`, `askSn` 선전송, 256B 청크 → 이번 계획에서는 쓰지 않음 |
| 14050 | `cupsRasterReadHeader2` 메인 루프, 14091–14130 RGB→gray·8배수 패딩 |
| 14612–14637 | `ModelNumber == M832` && 연속용지: **높이만** A4=295mm·Letter=11in로 0xFF 패딩. 폭(cupsWidth)은 불변 |
| 14696 | `bytewidth = (cupsWidth+7)/8` |
| 14754–14763 | 압축 On 대상은 S821·M04S·P832Pro·Q302·S822. **M832는 else → `1F 11 35 00`(Off)** |
| 14781–14788 | `bCmdBMP` xL xH=bytewidth, yL yH=전체 높이 → **페이지당 래스터 1블록** |
| 14832 / 14845 | fwrite 256B(socket 전용) / 4096B(그 외). CUPS 파이프 단위이지 USB 전송 단위 아님 |
| 14913–14920, 14934–14940 | M832 && 연속용지 && 페이지가 A4·Letter **아닐 때만** 페이지마다 `1B 64 01`, 작업 끝 `1B 64 02`. A4 테스트에선 안 나감 |
| 14958 | 831 외 모델은 작업 끝에 `findpaper 1F 11 11` |

### reference 레포 기지 패턴 `[미검증·사전열람]` (비교용, 상수 복사 금지)

프리앰블 `1b 40`/`1b 61 01`/`1f 11 xx`, 래스터 `1d 76 30 00 xL xH yL yH`+MSB-first 1bpp(1=검정),
꼬리 `1b 64 nn`/`1f f0 05 00 1f f0 03 00`. 300dpi 동족 `reference/cups/filter/rastertopm04.py`는
`1f 11 02/37/35` 명령군과 페이지 단일 블록을 사용하며, 중간 래스터 헤더를 무시하는 기종 주석이
108–111행에 있다. M02 USB는 CDC-ACM(if0)+Printer class(if2), VID `0x0493`
(`reference/README.md:52-72`).

### 로컬 환경 `[미검증·사전열람]`

미설치 — `unzip`, `usbutils`, `libusb-1.0-0`, `python3.12-venv`, CUPS 전부, `libcupsimage2t64`,
`ocl-icd-libopencl1`, `pyusb`, `Pillow`. 설치됨 — `file`, `binutils`(`readelf`/`strings`), `xxd`,
`cmp`, python 3.12.3, `gh`, `git`. PID1=systemd. 배포판 `Ubuntu-24.04`. `/dev/bus/usb` 없음
(USB가 아직 WSL에 연결되지 않음). `cups-daemon`의 Recommends에 `cups-browsed`·`ipp-usb`가 있고,
이들이 프린터 인터페이스를 선점할 수 있다.

---

## 3. 구 PLAN.md 단계 → PLAN-01

| 구 PLAN.md 단계 | PLAN-01 대응 |
|---|---|
| 0단계 환경 준비 | 0단계 |
| 1단계 장치 지문 | 1단계 |
| 2단계 링크 생존 확인 | 부록(보류) |
| 3단계 헤드 폭 실측 | A단계 + B-2 (실측은 F-2) |
| 4단계 이미지 출력 | E-3 |
| 5단계 USB 스니핑 | F-1 |
| 6단계 cron PoC | G단계 |

---

## 4. 전체 진행 순서

```
0-a → A → B → [보고#1] → C → [보고#2] → 0-b → 1 → D → [보고#3] → E-1 → E-2 → E-3 → G
```

F단계는 A~E 중 어딘가에서 막힐 때만 발동한다. A~C는 프린터가 없어도 진행할 수 있다.

---

## 5. 0단계 — 환경 준비

구 PLAN.md 0단계를 이식한다.

### 0-a (프린터 불필요)

```bash
cd ~/Data/detox-printer/m832
sudo apt update && sudo apt install -y unzip usbutils libusb-1.0-0 python3.12-venv
python3 -m venv .venv && .venv/bin/pip install pyusb pillow
```

통과 조건:

```bash
.venv/bin/python -c "import usb.backend.libusb1 as b, PIL; assert b.get_backend() is not None; print('ok')"
```

이 출력이 `ok`여야 한다.

### 0-b (1단계 직전, 프린터 필요)

**Windows 관리자 PowerShell**

```powershell
usbipd list  # M832의 BUSID와 VID:PID 확인
usbipd bind --busid <x-y>
usbipd attach --wsl --busid <x-y>
```

WSL에서 확인:

```bash
lsusb
ls /dev/bus/usb/*/
```

통과 조건: `lsusb` 출력에 M832로 보이는 장치가 있다. 그 한 줄을 그대로 `docs/findings.md`에 붙여넣는다.

막히면 다음 3가지 중 해당하는 것을 시도한다:

- `usbipd bind`가 거부됨 → Windows 장치 관리자에서 Phomemo 장치를 "사용 안 함" 처리 후 재시도
- `lsusb`에 안 보임 → 프린터 전원이 켜져 있는지 먼저 확인
- `Access denied` → udev 규칙을 만들거나 일단 `sudo`로 진행

---

## 6. A단계 — 드라이버 패키지 해부

프린터 불필요.

```bash
cd ~/Data/detox-printer/m832
unzip -q .temp/driver/QY_Printer_Driver_Linux.zip -d .temp/driver/extracted
tar xzf .temp/driver/extracted/QY_Printer_Driver_Linux/QY_Printer-2.1.0.3.tar.gz -C .temp/driver/extracted
ls .temp/driver/extracted/QY_Printer-2.1.0.3/{c,ppds,x86_64,aarch64}
sha256sum .temp/driver/QY_Printer_Driver_Linux.zip .temp/driver/extracted/QY_Printer_Driver_Linux/QY_Printer-2.1.0.3.tar.gz .temp/driver/extracted/QY_Printer-2.1.0.3/ppds/M832.ppd .temp/driver/extracted/QY_Printer-2.1.0.3/{x86_64,aarch64}/rastertoM08F
```

- `sudo`로 풀지 않는다 (tar 안에 0777 항목이 있다). `.gitignore`에 `m832/.temp/driver/`가 있는지 확인한다.
- **절대 하지 말 것**: `install`·`qyInstall`을 실행하지 않는다.
- 인벤토리: `find .temp/driver/extracted -type f | sort`, 각 파일에 `file` 실행. 찾을 것에 `c/` 소스,
  `x86_64/i386/aarch64/arm/armhf` 5개 아키텍처, 루트의 `linux` 스크립트를 추가한다. PPD는 gzip이 아니다.
- PPD 읽기: `cat .temp/driver/extracted/QY_Printer-2.1.0.3/ppds/M832.ppd` (전체 `*.ppd` 75개를 전부
  덤프하지 않는다). `diff M832.ppd M832D.ppd` 결과를 기록한다.
- 추출 표에 `*cupsModelNumber`, Resolution 줄의 `cupsColorSpace`/`cupsBitsPerColor`/`cupsRowCount`,
  옵션 기본값을 추가한다.
- WIDTH_BYTES 예시를 실제 값으로 교체한다: `(580.83 - 14.17) / 72 * 300 = 2361.08 dot → ceil(/8) = 296`.
- 통과 조건:
  - `M832.ppd` 존재를 확인했다
  - `WIDTH_BYTES` 잠정값을 findings.md에 `[미검증·PPD계산]`으로 기록했다 (확정은 C단계 `bCmdBMP`의
    `xL xH`로 한다)
  - `*cupsFilter`가 가리키는 필터의 실제 파일 경로를 확인했다
  - zip·tar·PPD·필터 바이너리의 sha256을 기록했다

M832 PPD가 없으면 여기서 멈추고 보고한다 → F단계로 간다.

---

## 7. B단계 — 검증 + 소스 지도

### B-1

```bash
cd ~/Data/detox-printer/m832
D=.temp/driver/extracted/QY_Printer-2.1.0.3
for a in x86_64 aarch64; do file $D/$a/rastertoM08F; readelf -l $D/$a/rastertoM08F | grep -i interpreter; readelf -d $D/$a/rastertoM08F | grep NEEDED; done
strings $D/x86_64/rastertoM08F | grep -iE 'http|https|curl|wget|socket|/dev/|/tmp/'
cat $D/install; cat $D/uninstall; cat $D/linux
```

- `ldd`는 x86_64 바이너리에 한정해서, interpreter가 `/lib64/ld-linux-x86-64.so.2`임을
  `readelf`로 확인한 뒤에만 사용한다.
- NEEDED에 나온 `libOpenCL.so.1`·`libcupsimage.so.2`는 C단계에서 apt로
  (`ocl-icd-libopencl1`·`libcupsimage2t64`) 해결한다. 그 외의 라이브러리가 not found일 때만 멈춘다.
- `strings`에서 `socket:` 히트가 나와도 이건 DEVICE_URI 문자열 비교(소스 14043행)이지 네트워크 API가
  아니다 — 오탐으로 멈추지 않는다.
- 아키텍처 판단: aarch64 바이너리가 이미 존재하므로 "x86_64뿐이라 이식 불가"는 E단계가 필요한 이유가
  **아니다**. E단계는 CLAUDE.md 목표(벤더 드라이버·CUPS 비의존) 때문에 필수다.

### B-2 (신설) — `c/rastertoM08F.cxx` → `docs/filter-source-map.md`

위 2절의 소스 앵커 표에서 출발한다. 벤더 소스는 레포에 복사하지 않고, 필요한 몇 줄만 인용한다.
정리 항목:

- (a) `skipAsk==0` 경로의 블로킹·질의 바이트(`1F 11 07`, `1F 11 43`, 용지·커버 조회)와
  `skipAsk==1` 경로의 차이. `skipAsk` 사용처(12188·12306·12510·12725·14802행) 전부 확인한다.
- (b) M832의 압축 여부(소스상 Off).
- (c) 헤더(StartPage 옵션 명령) → `1F 11 35 00` → `bCmdBMP` → 비트맵 → 꼬리 순서.
- (d) 비트 극성(13405–13432행, 1=검정).
- (e) 높이 패딩 로직과 `cupsWidth`의 출처.

통과 조건: 실행 가부 판단과 근거, 소스 지도(`docs/filter-source-map.md`) 완성. 애매하면 멈추고
**보고#1**.

---

## 8. C단계 — 필터 오프라인 실행

```bash
sudo apt install -y --no-install-recommends cups cups-client cups-filters libcupsimage2t64 ocl-icd-libopencl1
```

설치 후 `systemctl is-active ipp-usb cups-browsed`가 `active`로 나오면 멈추고 보고한다
(둘 다 프린터 인터페이스를 선점할 수 있다).

필터 호출 규약은 고정이다: `filter job-id user title copies options [filename]`.

스크립트:

- `src/01_make_testimages.py` — `t1_white`/`t2_black`/`t3_corner`/`t4_line`을 생성해
  `captures/filter/tN_*.png`로 저장
- `src/02_run_filter.py` — PNG를 `.ras`로 변환하고 필터를 실행, 결과를 저장
- `src/03_analyze_bin.py` — 크기·`xxd`·`cmp`·패턴 분석

테스트 입력 4종과 "알아내는 것":

| 이름 | 내용 | 알아내는 것 |
|---|---|---|
| `t1_white` | A4 전체 흰색 | 헤더/푸터 순수 형태 |
| `t2_black` | A4 전체 검정 | 압축 여부 (t1과 크기 비교) |
| `t3_corner` | 좌상단 100×100만 검정 | 좌표/오프셋 인코딩 |
| `t4_line` | 가로 1px 검은 줄 하나 | 라인 단위 구조 |

`.ras` 변환:

```bash
cupsfilter -m application/vnd.cups-raster -p .temp/driver/extracted/QY_Printer-2.1.0.3/ppds/M832.ppd captures/filter/t1_white.png > captures/filter/t1.ras
```

헤더의 `cupsColorSpace`/`cupsBitsPerColor`/`HWResolution`/`cupsWidth`를 확인한다. `cupsfilter`가
실패하면 Python으로 RaS3 헤더를 직접 작성한다(필드 순서는 `reference/cups/filter/rastertopm04.py:36-86`).

필터 실행 (정확히 이 형태):

```bash
cd ~/Data/detox-printer/m832
D=.temp/driver/extracted/QY_Printer-2.1.0.3
PPD=$D/ppds/M832.ppd DEVICE_URI=bluetooth://offline \
  timeout 30 $D/x86_64/rastertoM08F 1 tester test 1 "" \
  < captures/filter/t1.ras 2> captures/filter/t1.stderr.log \
  | head -c 104857600 > captures/filter/t1.bin
echo "filter exit=${PIPESTATUS[0]}"   # 124 = timeout
```

- 필터는 절대 `sudo`로 실행하지 않는다.
- `DEVICE_URI=bluetooth:`는 소스 14033–14037행의 대기 우회를 이용한 것이다. `socket:`은 금지
  (256B 청크 경로로 빠진다).
- `skipAsk=0` 변형(DEVICE_URI 미지정)도 같은 형태로 1회 실행해 `t1.ask.bin`으로 저장하고 비교한다.
- 3회 시도 내로 해결하지 못하면 F단계로 간다.

파일명 고정: `tN_*.png → tN.ras → tN.bin / tN.stderr.log`, 변형은 `tN.ask.bin`.

결정성: 같은 입력을 2회 실행한 뒤 `cmp`로 비교한다. 가변 바이트(`skipAsk=0` 변형에서 질의 반복
횟수 등. `rubbishData`·`askSn`은 소스상 M832 경로가 아니므로 여기서 나오지 않는다)를 식별한 뒤
비교한다.

분석 체크리스트 (구 PLAN-02 유지 + 추가):

- reference 기지 패턴과 대조한다
- 소스 기대 순서: `1F 11 xx…` → `1F 11 35 00` → `1D 76 30 00 xL xH yL yH` → 비트맵
- `1d 76 30` 항목에 대해 "구 PLAN.md 가정"이라는 문구 대신 "초기 가정(ESC/POS 래스터)이며 소스상
  `bCmdBMP`로 이미 확인됨(11349, 14781–14788)"이라고 쓴다
- `xL xH`를 PPD 계산값 296과 대조한다

결과를 `docs/protocol.md`에 바이트 단위 표로 정리한다 → **보고#2**.

---

## 9. 1단계 — 장치 지문

구 PLAN.md 1단계를 이식한다.

`src/04_probe.py` 작성. pyusb로 장치를 열고 아래를 전부 출력한 뒤 `docs/device-descriptor.md`에
저장한다. 이 단계에서는 아무것도 쓰지 않는다(읽기만 한다).

수집 4항목(원문 그대로): `idVendor / idProduct / iManufacturer / iProduct / iSerialNumber`;
컨피그레이션 개수, 각 인터페이스의 `bInterfaceNumber / bInterfaceClass`(7 = Printer,
255 = Vendor specific); 모든 엔드포인트의 `bEndpointAddress`, 전송 타입, `wMaxPacketSize`;
커널 드라이버가 붙어 있는지(`is_kernel_driver_active`).

통과 조건:

- BULK OUT 엔드포인트 주소를 확정했다
- `wMaxPacketSize`를 알아냈다
- 인터페이스 클래스(7 또는 255)를 기록했다
- `BULK IN 엔드포인트 주소(있다면)를 기록했다 (E-1 응답 읽기·G단계 용지 확인에 필요)`

해석 힌트 (구 PLAN.md에서 교체):

- 클래스 7 → D단계(CUPS 경유)가 될 가능성이 높다
- 클래스 255 → `lpinfo -v`에 안 보일 수 있다. 그러면 D단계를 건너뛰고 E-1로 간다(F-1 확률 상승)
- 명령 체계는 소스상 `1F 11 xx`+`1D 76 30`이므로 ESC/POS 여부로 해석하지 않는다
- M02는 복합장치이고 VID `0x0493`이었으나, M832가 같은 VID라고 가정하지 않는다

---

## 10. D단계 — CUPS 실제 인쇄

```bash
sudo systemctl start cups
lpinfo -v
```

usb 백엔드는 libusb 기반이라 `usblp` 커널 모듈 없이도 동작한다.

필터 수동 설치:

```bash
sudo install -m 755 -o root -g root .temp/driver/extracted/QY_Printer-2.1.0.3/x86_64/rastertoM08F /usr/lib/cups/filter/
```

큐 생성:

```bash
sudo lpadmin -p M832 -v "usb://..." -P .temp/driver/extracted/QY_Printer-2.1.0.3/ppds/M832.ppd -o printer-error-policy=abort-job -E
```

인쇄 전 용지 장착을 육안으로 확인한다(금지 5). 실물 인쇄는 `t3_corner`·`t4_line`만 한다.
**`t2_black`은 실물 인쇄 금지.**

금지 3: 인쇄 직전, 동일 옵션으로 실행한 오프라인 필터 결과를 `captures/sent/NNNN_d_t3.bin`으로
저장하고 "CUPS 전송 추정본"이라고 표기한다. 가능하면 `cupsctl --debug-logging`으로 대조한다.

종료 직후(성공·실패 무관):

```bash
cancel -a M832; sudo cupsdisable M832; lpstat -o
```

대기 작업이 0건이어야 한다.

통과 조건: 실제로 종이에 출력됐다. 사진을 `docs/photos/`에 남겼다. C단계의 `t3.bin`과 실제 전송
바이트를 비교했다.

실패 시 진단 순서: `lpstat -t` → `/var/log/cups/error_log` → `lp` 그룹 권한 확인 → usbipd attach
상태 확인 → **보고#3**.

---

## 11. E단계 — pyusb 재현

필수 이유: CLAUDE.md 목표(순수 파이썬+pyusb, CUPS·벤더 드라이버 비의존).

공통: 시작 전에 `sudo systemctl stop cups`.

### E-1. 재생 (`src/05_replay.py`)

1단계에서 얻은 VID:PID·엔드포인트를 사용해
`detach_kernel_driver → set_configuration → claim_interface` 순서로 처리한다. write 타임아웃을
명시하고 예외를 삼키지 않는다. 청크는 4096바이트에서 시작해 `wMaxPacketSize`와 실측으로 조정한다.
BULK IN 응답을 로그로 남긴다. `1F 11 11`(findpaper) 응답 형식과 "용지 있음" 값을 기록한다.
보낸 바이트는 전부 `captures/sent/NNNN.bin`으로 저장한다. 전송 전 용지 확인 후 Enter로 진행한다.

D단계와 같은 출력이 나오면 프로토콜은 확보된 것이다.

### E-2. 생성 (`src/06_generate.py`)

`captures/filter/t3.bin`(`skipAsk=1` 변형)과 바이트 단위로 동일한지 assert한다. C단계에서 식별한
가변 필드만 문서화된 마스크로 제외한다.

```python
assert generated == open('captures/filter/t3.bin', 'rb').read()
```

### E-3. 이미지 출력 (`src/07_print_image.py`, 구 PLAN.md 4단계 이식)

그레이스케일 변환 → 확정 폭으로 리사이즈 → Floyd-Steinberg 디더링으로 1bit 변환 →
MSB-first 패킹(1=검정) → 전송. 소스상 페이지당 `bCmdBMP` 1블록이 원칙이다. 잘림·버퍼 초과가
의심될 때만 블록 분할(블록당 24~64줄에서 시작, 초과 의심 시 줄인다)과 블록 사이 sleep을 시도한다.
중간 래스터 헤더를 무시하는 기종 사례(`rastertopm04.py:108-111`)를 참고 기록한다.

검증 순서: 체커보드·대각선·원 → Pillow `ImageDraw`로 텍스트 렌더링 → 사진. 방향·좌우반전을
확인한다. 래스터 전송 전에 findpaper로 용지 확인.

통과 조건: 도형이 왜곡 없이 출력된다. 텍스트가 판독 가능하게 출력된다.
`python src/07_print_image.py image.png` 만으로 인쇄된다. 벤더·CUPS 의존이 0이다.

---

## 12. F단계 — 폴백

발동 조건: M832 PPD가 없다 / 필터가 독립 실행 불가능하다 / 필터 실행이 3회 실패한다 /
backchannel 없이는 출력이 불가능함을 소스로 확인했고 우회할 수 없다. 포기 판단도 findings.md에
기록한다.

### F-1. USB 스니핑 (구 PLAN.md 5단계 이식)

```
usbipd detach --busid <x-y>
```

→ Windows에 공식 드라이버 설치, 프린터 정상 인식 확인 → Wireshark + USBPcap 설치, 해당 USB
루트 허브 캡처 시작 → 아주 단순한 것 1장 인쇄(검은 사각형 하나 / "A" 한 글자. 복잡한 문서는
분석이 몇 배로 어려워진다) → 캡처를 `captures/official/`에 저장.

분석: BULK OUT 전송만 이어붙인다. 앞뒤 수십 바이트에서 헤더/푸터를 찾는다. `1d 76 30` 블록의
반복 여부를 확인한다. 크기만 바꿔 2회 캡처해서 raw인지 압축인지 판별한다. 결과를
`docs/protocol.md`에 바이트 단위 표로 정리한다.

끝나면 `usbipd bind --force --busid <x-y>` 후 `attach --wsl` (Windows 드라이버가 장치를 다시
점유하게 한다).

통과 조건: 캡처에서 추출한 바이트를 pyusb로 재전송해서 동일한 출력을 얻었다.

### F-2. 헤드 폭 실측 (구 PLAN.md 3단계, A·B-2·C의 폭 값이 서로 어긋날 때만)

C단계에서 확인된 래스터 형식을 사용한다(ESC/POS라고 가정하지 않는다).

| 회차 | 바이트/라인 | 예상 dot | 띠 높이 | 의미 |
|---|---|---|---|---|
| 1 | 48  | 384  | 8줄  | M02 계열 |
| 2 | 72  | 576  | 16줄 | |
| 3 | 216 | 1728 | 24줄 | 80mm 영수증 계열 |
| 4 | 288 | 2304 | 32줄 | |
| 5 | 296 | 2368 | 56줄 | A4 PPD ImageableArea 계산값 |
| 6 | 304 | 2432 | 40줄 | Letter PPD 계산값 |
| 7 | 310 | 2480 | 48줄 | A4 용지 전폭 |

**띠 높이는 회차마다 달라야 한다.** 회차 사이에는 `1b 64 02`로 여백을 준다. 한 번에 하나씩 보내고
Enter로 확인한 뒤 다음으로 넘어간다.

해석: 여러 줄로 접혀서 나온다 → 폭이 과대, 한 단계 줄인다 / 왼쪽 일부만 나온다 → 폭이 과소,
한 단계 늘린다 / 전부 무반응 → F-1로 간다.

mm로 실측한 뒤 `dot = mm / 25.4 * 300`으로 역산한다. 확정된 `WIDTH_BYTES`를 findings.md에
굵게 기록한다.

---

## 13. G단계 — cron 자동 출력 PoC

구 PLAN.md 6단계를 이식한다.

`src/08_print_daily.py` 작성: `messages/YYYY-MM-DD.txt`를 Pillow로 렌더링해 출력한다. 파일이
없으면 기본 문구로 대체한다(실패해도 매일 뭔가는 나와야 한다). 성공/실패를 `logs/print.log`에
남긴다. 프린터 미연결 시 조용히 실패하지 말고 로그에 명시한다.

**래스터 전송 전에 `1F 11 11` 응답을 E-1에서 기록한 "용지 있음" 값과 비교한다. 불일치·무응답이면
인쇄하지 않고 로그만 남긴다. 응답 형식이 E-1에서 확정되기 전에는 G단계를 시작하지 않는다.**

```
0 7 * * * cd ~/Data/detox-printer/m832 && .venv/bin/python src/08_print_daily.py
```

**WSL 주의**: WSL 인스턴스가 떠 있을 때만 cron이 동작한다. Windows 작업 스케줄러에서 다음을
호출하는 방식이 안전하다.

```
wsl.exe -d Ubuntu-24.04 -e bash -lc "cd ~/Data/detox-printer/m832 && .venv/bin/python src/08_print_daily.py"
```

Orange Pi로 넘어가면 이 문제는 해소된다.

통과 조건: 3일 연속 사람 손 없이 07시에 출력됐다.

---

## 14. 부록 — 보류된 구 2단계 (링크 생존 확인)

구 PLAN.md 2단계는 폐기하지 않고 보류한다(링크 생존 확인). 용지를 넣고 `1b 40` 전송 → 0.3초
대기 → `1b 64 03` 전송. 보낸 바이트는 `captures/sent/`에 저장한다.

결과 해석:

- (A) 종이가 이송됨 / (B) write는 성공했으나 무반응 → E-1 진단을 계속한다
- (C) `USBError: Pipe error` 또는 timeout → F-1로 간다

**M832는 `1f 11` 명령군을 쓰므로 ESC/POS 반응을 기대하지 않는다.** E-1이 애매하게 실패할 때만
스모크 테스트로 사용한다. 스크립트 번호는 09 이상에서 부여한다.

---

## 15. 스크립트 번호 규칙

`01~08`은 예약(번호=계획상 실행 순서)이다. 같은 단계의 재시도·F단계·부록 스크립트는 09부터
작성 순서대로 번호를 매긴다. 기존 파일은 재번호·덮어쓰기·통합하지 않는다(CLAUDE.md 코드 규칙·
금지 6).

---

## 16. 진행 방식

첫 작업은 `0-a → A → B`까지 하고 멈춰서 보고한다. 이후 보고 지점은 보고#1(B단계 후),
보고#2(C단계 후), 보고#3(D단계 후)이다.

사유: "x86_64인지 arm64인지"가 아니라, 소스 지도로 드러난 M832 경로(대기 우회·압축·폭)와
필터 로드 가능 여부가 이후 전체 경로를 결정한다. A~C는 프린터 없이 진행 가능하므로, 프린터가
연결돼 있지 않아도 작업할 수 있다.

---

## 17. 확정되면 CLAUDE.md에 반영할 것

구 PLAN-02 내용을 유지하되 아래로 수정한다.

- `WIDTH_BYTES` = (C단계 필터 출력 `bCmdBMP`의 `xL xH` 값)
- 해상도 = (PPD의 `DefaultResolution`)
- 프로토콜 계열 (ESC/POS 래스터인지 전용 포맷인지)
- 압축 여부
- 벤더 필터 아키텍처 목록 (aarch64 존재. E단계 필요성과는 무관)
- 필터 이름 · `cupsModelNumber`
- 필터 입력 형식
- VID:PID·엔드포인트 (1단계 후)

`"310 byte/line"`처럼 이미 확정된 사실로 적혀 있던 값이 반증되면, 지우지 말고 취소선과 함께
정정 사유를 남긴다.

---

## 재사용할 기존 자산

- RaS3 헤더 필드 순서: `reference/cups/filter/rastertopm04.py:36-86`; 1bpp·단일 블록 출력: `:88-149`
- Bluetooth RFCOMM 청크·응답 드레인 패턴(USB 아님): `reference/cups/backend/phomemo.py:140-198`;
  USB class 7 탐색·VID 0x0493: `:50-94`
- M02 스트림 검증기 구조: `reference/tools/format-checker.py` (cwd에 PNG 생성 → 임시 디렉터리에서만
  실행)
- 스킬: `investigate-first`(C·E 실패 진단), `verify-and-stop`(통과 조건만 증명)
