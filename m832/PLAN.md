> **이 문서의 모든 상대경로는 `m832/` 기준이다.**
> Claude Code는 레포 루트(`~/Data/detox-printer`)에서 실행되므로, 이 문서의 `src/01_probe.py`는 실제로 `m832/src/01_probe.py`다.
> venv도 `m832/.venv`에 만든다.

# 실행 계획

각 단계는 **통과 조건**을 만족해야 다음으로 넘어간다.
단계가 끝날 때마다 `docs/findings.md`에 기록하고 커밋한다.

---

## 0단계 — 환경 준비

**할 일**

```bash
sudo apt update && sudo apt install -y libusb-1.0-0 usbutils
python3 -m venv .venv && source .venv/bin/activate
pip install pyusb pillow
```

Windows 관리자 PowerShell에서 USB를 WSL로 넘긴다.

```powershell
usbipd list                       # M832의 BUSID와 VID:PID 확인
usbipd bind   --busid <x-y>
usbipd attach --wsl --busid <x-y>
```

WSL에서 확인:

```bash
lsusb
ls /dev/bus/usb/*/
```

**통과 조건**
- `lsusb` 출력에 M832로 보이는 장치가 있다
- 그 한 줄을 `docs/findings.md`에 그대로 붙여넣었다

**막히면**
- `usbipd bind`가 거부되면 Windows 장치 관리자에서 Phomemo 장치를 "사용 안 함" 처리 후 재시도
- `lsusb`에 안 나오면 프린터 전원이 켜져 있는지 먼저 확인. 꺼져 있으면 USB로도 안 잡힌다
- 권한 문제(`Access denied`)는 udev 규칙을 만들거나 일단 `sudo`로 진행

---

## 1단계 — 장치 지문 뜨기

**할 일**

`src/01_probe.py` 작성. pyusb로 장치를 열고 아래를 전부 출력한 뒤
`docs/device-descriptor.md`에 저장한다.

- idVendor / idProduct / iManufacturer / iProduct / iSerialNumber
- 컨피그레이션 개수, 각 인터페이스의 bInterfaceNumber / bInterfaceClass
  (7 = Printer class인지, 255 = Vendor specific인지가 중요하다)
- 모든 엔드포인트의 bEndpointAddress, 전송 타입, wMaxPacketSize
- 커널 드라이버가 붙어 있는지 (`is_kernel_driver_active`)

이 단계에서는 **아무것도 쓰지 않는다.** 읽기만 한다.

**통과 조건**
- BULK OUT 엔드포인트 주소를 하나 이상 확정했다
- `wMaxPacketSize`를 알아냈다 (뒤에서 청크 크기 결정에 쓴다)
- 인터페이스 클래스가 Printer(7)인지 Vendor(255)인지 기록했다

**해석 힌트**
- 클래스 7이면 표준 프린터 프로토콜 → ESC/POS일 가능성이 높아진다
- 클래스 255면 전용 프로토콜일 가능성이 커지고 5단계(스니핑) 확률이 올라간다

---

## 2단계 — 링크 생존 확인 (인쇄 없이)

**할 일**

`src/02_feed.py` 작성. 용지를 넣고, **인쇄 없이 이송만** 시키는 명령을 보낸다.

1. `1b 40` (ESC @, 초기화) 전송
2. 0.3초 대기
3. `1b 64 03` (ESC d 3, 3줄 피드) 전송

보낸 바이트는 `captures/sent/`에 저장한다.
필요하면 `detach_kernel_driver` → `set_configuration` → `claim_interface` 순서로 처리.

**통과 조건 (셋 중 하나)**
- (A) 종이가 눈에 띄게 이송됨 → ESC/POS 계열 확정에 가깝다. 3단계로
- (B) write는 성공(반환 길이 정상)했는데 아무 반응 없음 → 3단계로 가되 기대치를 낮춘다
- (C) `USBError: Pipe error` / timeout → 5단계(스니핑)로 바로 점프

어느 쪽인지 `docs/findings.md`에 명확히 쓴다. 이게 이 프로젝트에서 가장 중요한 한 줄이다.

---

## 3단계 — 헤드 폭 실측

여기가 M832와 M02가 갈라지는 지점이다. 추측하지 말고 자로 잰다.

**할 일**

`src/03_width_probe.py` 작성. 래스터 명령으로 **검은 띠**를 출력한다.

```
1d 76 30 00  xL xH  yL yH  + (0xFF * xL_xH * y)
```

`xL xH`(라인당 바이트 수)를 아래 순서로 바꿔가며 시도한다.

| 회차 | 바이트/라인 | 예상 dot | 띠 높이 | 의미 |
|---|---|---|---|---|
| 1 | 48  | 384  | 8줄  | M02 계열 폭 (거의 확실히 너무 좁음) |
| 2 | 72  | 576  | 16줄 | |
| 3 | 216 | 1728 | 24줄 | 80mm 영수증 프린터 계열 폭 |
| 4 | 288 | 2304 | 32줄 | |
| 5 | 304 | 2432 | 40줄 | A4 유력 후보 |
| 6 | 310 | 2480 | 48줄 | A4 이론상 최대 |

**띠 높이를 회차마다 다르게 하는 게 핵심이다.** 나중에 출력물만 보고 몇 번째
시도가 성공했는지 구분할 수 있다. 회차 사이에는 `1b 64 02`로 여백을 준다.

각 회차는 사용자가 결과를 눈으로 확인할 수 있게 **한 번에 하나씩** 보내고,
진행 전에 콘솔에서 Enter를 기다린다. 전부 연속으로 쏟아붓지 말 것.

**통과 조건**
- 종이 폭을 꽉 채우는(또는 일정 폭에서 잘리는) 검은 띠가 나온 회차를 찾았다
- 띠의 실제 너비를 mm로 재서 `dot = mm / 25.4 * 300` 으로 역산했다
- 확정된 `WIDTH_BYTES` 값을 `docs/findings.md`에 굵게 기록했다

**이런 결과가 나오면**
- 띠가 여러 줄로 접혀서 나온다 → 지정한 폭이 실제 폭보다 크다. 한 단계 줄인다
- 띠가 종이 왼쪽 일부에만 나온다 → 폭이 실제보다 작다. 한 단계 늘린다
- 전부 무반응 → 래스터 명령 자체가 다르다. 5단계로

---

## 4단계 — 이미지 출력

3단계에서 폭이 확정된 뒤에만 진행한다.

**할 일**

`src/04_print_image.py` 작성.

1. Pillow로 이미지 로드 → 그레이스케일 → 확정된 폭에 맞춰 리사이즈
2. Floyd-Steinberg 디더링으로 1bit 변환
3. 1비트/픽셀 패킹 (MSB first, 검정 = 1 인지 0 인지는 실험으로 확인)
4. **청크 분할 전송** — 한 번에 전부 보내지 말고 `1d 76 30` 블록을 여러 개로 쪼갠다.
   시작값은 블록당 24~64줄. 버퍼 오버플로가 의심되면 줄인다
5. 블록 사이에 짧은 sleep

먼저 작은 테스트 이미지(체커보드, 대각선, 원)로 검증한다.
사진은 마지막에 한다. 방향이 뒤집히거나 좌우 반전되는지 확인하기 좋다.

**통과 조건**
- 의도한 도형이 왜곡 없이 출력된다
- 텍스트를 이미지로 렌더링해서(Pillow ImageDraw) 읽을 수 있게 출력된다

---

## 5단계 — USB 스니핑 (2~4단계가 막혔을 때만)

USB라서 Bluetooth HCI 스니핑보다 훨씬 쉽다.

**할 일**

1. WSL에서 분리: `usbipd detach --busid <x-y>`
2. Windows에 Phomemo 공식 드라이버 설치, 프린터 정상 인식 확인
3. Wireshark + USBPcap 설치, 해당 USB 루트 허브 캡처 시작
4. 공식 드라이버로 **아주 단순한 것** 하나 인쇄 (검은 사각형 하나 / "A" 한 글자)
   복잡한 문서를 인쇄하면 분석이 몇 배로 어려워진다
5. 캡처를 `captures/official/` 에 저장

**분석 지시**
- BULK OUT 전송만 필터링해서 바이트 스트림을 이어붙인다
- 앞쪽 수십 바이트(헤더)와 뒤쪽 수십 바이트(푸터)를 찾아낸다
- 데이터 본문이 `1d 76 30`으로 시작하는 블록의 반복인지 확인한다
- 아니라면 압축/전용 포맷이다. 같은 이미지를 크기만 바꿔 두 번 캡처해서
  길이가 어떻게 변하는지 비교하면 raw인지 압축인지 구분된다
- 결과를 `docs/protocol.md`에 바이트 단위 표로 정리한다

**통과 조건**
- 캡처에서 추출한 바이트 시퀀스를 그대로 pyusb로 재전송해서 동일한 출력을 얻었다

여기까지 오면 프로토콜은 확보된 것이다.

---

## 6단계 — cron 자동 출력 PoC

**할 일**

`src/print_daily.py` 작성.

- `messages/YYYY-MM-DD.txt` 를 읽어 Pillow로 이미지 렌더링 후 출력
- 파일이 없으면 기본 문구로 대체 (실패해도 매일 뭔가는 나와야 한다)
- 성공/실패를 `logs/print.log`에 남긴다
- 프린터 미연결 시 조용히 실패하지 말고 로그에 명시

```
0 7 * * * cd ~/Data/detox-printer/m832 && .venv/bin/python src/print_daily.py
```

**WSL 주의 (중요)**
WSL의 cron은 WSL 인스턴스가 떠 있을 때만 돈다. 컴퓨터를 켜둬도 WSL이 자고 있으면
07시에 안 돌아간다. 한 달 테스트를 제대로 하려면 Windows 작업 스케줄러에서
`wsl.exe -d Ubuntu -e bash -lc "..."` 를 호출하는 방식이 안전하다.
Orange Pi로 넘어가면 이 문제는 사라진다.

**통과 조건**
- 3일 연속으로 사람 손 없이 07시에 출력됐다

---

## 요약: 지금 당장 할 것

0단계 → 1단계 → 2단계.
2단계 결과가 (A)인지 (B)인지 (C)인지가 이 프로젝트의 분기점이다.
거기까지만 하고 결과를 보고할 것.
