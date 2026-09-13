# M832 필터 소스 지도 (`c/rastertoM08F.cxx`)

대상 파일: `.temp/driver/extracted/QY_Printer-2.1.0.3/c/rastertoM08F.cxx` (15,015 lines, 미수정).
레포에는 복사하지 않고, 아래 표의 줄 번호로만 참조한다.

## 0. 모델 상수

```
11309  #define M08F     0x15
11310  #define S821     0x16
11311  #define S822     0x17
11313  #define M04S     400
11314  #define P831     831
11315  #define M832     77832
11316  #define Q302     302
11317  #define TP86     848086
11318  #define P832Pro  808320
```

`M832 == 77832`. 뒤에 나오는 `if (ModelNumber == 831)`(14953행)은 **P831**(정수 831) 검사이며
M832와는 무관하다 — 처음 봤을 때 오탐하기 쉬운 지점이라 명시해 둔다.

## 1. 줄 번호 앵커 표

| 항목 | 줄 번호 | 비고 |
|---|---|---|
| `skipAsk` 선언 | 11345 | `int skipAsk = 0;` |
| `getHardVer()` 정의 | 11905–11933 | `1F 11 07` 질의 루프 |
| `GetPaperStatus()` 정의 | 11938–11970 | `1F 11 11` 질의 루프 |
| `GetCoverStatus()` 정의 | 11973–12005 | `1F 11 12` 질의 루프 |
| `GetSN()` 정의 | 12009–12033 | `1F 11 09` (M832 StartPage에서는 호출 안 함) |
| `waitFree()` 정의 | 12037–12071 | `1F 11 43` 질의 루프, M832 전용 `getHardVer()` 선행 호출 포함 |
| `skipAsk == 0` #1 (M08F/P832Pro/TP86 case) | 12188 | M832 아님 |
| `skipAsk == 0` #2 (P831 case) | 12306 | M832 아님, `waitFree()` 호출 포함 |
| `skipAsk == 0` #3 (Q302 case) | 12510 | M832 아님 |
| `StartPage case M832` 블록 | 12724–12858 | 본 문서 (a)(b)(c) 핵심 구간 |
| `skipAsk == 0` #4 (M832 case, 실제 관련 지점) | 12725 | `waitFree()` + 용지/커버 폴링 루프 |
| `OutputLine` switch, `case M832` | 13401–13429 | 비트 극성, (d) |
| `OutputLine case TSPL` (대조군) | 13434–13457 | `putchar(~temp)` — 반전 있음 |
| DEVICE_URI → `skipAsk = 1` | 14033–14036 | `strstr(device_uri, "bluetooth:")` |
| `isSocket` 분기 | 14043– | `strstr(device_uri, "socket:")` — 256B 청크 경로 (본 작업 금지 대상) |
| 높이 패딩, M832 분기 | 14611–14636 | (e) |
| 압축 On/Off 분기 | 14753–14764 | (b) |
| `bCmdBMP` 필드 세팅 및 출력 | 14780–14788 | (c) |
| `skipAsk` #5 (Q302 전송 청킹) | 14802 | M832 아님 |
| `bCmdAfter` per-page 트리거 (M832) | 14912–14920 | (c) 꼬리 바이트, continuous 전용 |
| `bCmdAfter` job-end 트리거 | 14934–14939 | `M832After` 플래그 기반 |
| 명령 바이트 정의 (`bCmdBMP` 등) | 11347–11363 | 아래 3절 참고 |

## 2. 명령 바이트 정의 (11347–11363)

```
11347  unsigned char bCmdDensity[4]         = { 0x1F, 0x11, 0x02, 6 };
11348  unsigned char bCmdSpecial[4]         = { 0x1F, 0x11, 0x37, 0x96 };
11349  unsigned char bCmdBMP[8]             = { 0x1D, 'v', '0', 0, 0, 0, 0, 0 };
11350  unsigned char bCmdCompressionOn[4]   = { 0x1F, 0x11, 0x35, 0x01 };
11351  unsigned char bCmdCompressionOff[4]  = { 0x1F, 0x11, 0x35, 0x00 };
...
11357  unsigned char findpaper[]            = { 0x1F, 0x11, 0x11 };   // 전역, job-end에서 재사용
11359  static unsigned char bCmdGap[3]      = { 0x1f, 0x11, PAPER_BLACK };
11361  //Antiwrinkling
11362  unsigned char bCmdAntiwrinkling[4]   = { 0x1f, 0x11, 0x88, 0x02 };
11363  unsigned char bCmdAfter[3]           = { 0x1B, 0x64, 0x02 };
```

`PAPER_GAP=0x0A`, `PAPER_CONTINUES=0x0B`, `PAPER_BLACK=0x26` (11319–11321).

## (a) `skipAsk` 전체 사용처와 M832 경로의 블로킹 지점

`skipAsk`가 등장하는 줄은 파일 전체에 **정확히 6곳**이다 (grep 검증):

| 줄 | 소속 case | 내용 |
|---|---|---|
| 11345 | 전역 | `int skipAsk = 0;` 선언, 기본값 0 |
| 12188 | `case M08F: case P832Pro: case TP86:` (StartPage) | `if (skipAsk==0)`이면 `GetPaperStatus()`/`GetCoverStatus()` 폴링 루프 실행. M832와 무관 |
| 12306 | `case P831:` (StartPage) | `if (skipAsk==0)`이면 `waitFree()` + 용지 상태 대기. M832와 무관 |
| 12510 | `case Q302:` (StartPage) | `if (skipAsk==0)`이면 (일부 모델명 한정) 용지/커버 폴링. M832와 무관 |
| **12725** | **`case M832:` (StartPage)** | **`if (skipAsk==0) { waitFree(); ... 용지/커버 폴링 루프 ... }`** — M832에 실제로 적용되는 유일한 skipAsk 분기 |
| 14802 | Q302 전송 청킹 (`else if (ModelNumber==Q302 && skipAsk)`) | Q302 전용 4096바이트 청크 전송 방식 선택. M832와 무관 |

`skipAsk`는 `DEVICE_URI`로 결정된다 (14033–14036):

```
14033  char* device_uri = getenv("DEVICE_URI");
14035  if (device_uri && strstr(device_uri, "bluetooth:")) {
14036      skipAsk = 1;
14037  }
```

M832 StartPage 블록의 실제 코드 (12724–12750):

```
12724  case M832: {
12725      if (skipAsk == 0) {
12726          waitFree();
12727          int loopCount = 0;
12728          int paperCheck = 0;
12729          while (1) {
                   if (Canceled)break;
                   if (GetCoverStatus()) { paperCheck = -1; continue; }
                   if (GetPaperStatus() == 1 && mymon.Coverstatus == 0) { paperCheck++; }
                   else { paperCheck = 0; }
                   if (paperCheck >= 2)break;
                   if (Page == 1 && paperCheck)break;
                   loopCount++;
                   sleep(1);
               }
               ...
12750      }
```

`waitFree()` 자체는 M832일 때 먼저 `getHardVer()`(`1F 11 07` 질의, 응답 올 때까지 무한 루프)를
호출하고, 그 값이 `0x10005` 미만이면 `GetCoverStatus()` 한 번만 부르고 리턴한다. 그렇지 않으면
`1F 11 43`(`free[]`)을 반복 전송하며 `mymon.freeStatus`가 설정될 때까지 블로킹한다
(12037–12071). `GetPaperStatus`/`GetCoverStatus`/`getHardVer`/`waitFree` 네 함수 모두 내부
루프에 `Canceled`가 아니면 빠져나갈 다른 조건이 없다 — 응답이 오지 않으면 무한 대기한다.

**M832 경로에서 `skipAsk==1`일 때는 이 `if` 블록 전체가 실행되지 않는다.** 즉
`waitFree()`, `getHardVer()`, `GetPaperStatus()`, `GetCoverStatus()` 호출이 전부 스킵되고
바로 `hOffset = vOffset = FeedOffset = Rotate = AutoDotted = 0;` (12751행)로 넘어간다.

## (b) 압축 여부 — M832는 Off

14753–14764:

```
14753  //压缩
14754  if (ModelNumber == S821 || ModelNumber == M04S || ModelNumber == P832Pro ||
           (ModelNumber == Q302 && isQ302) || ModelNumber == S822) {
14755      fwrite(bCmdCompressionOn, sizeof(bCmdCompressionOn), 1, stdout);
           unsigned char* combuff = ...
           buffersize = (unsigned int)compressBitmap((char*)sendBuf, (char*)combuff, (int)buffersize);
           ...
14763  }
14764  else {
           fwrite(bCmdCompressionOff, sizeof(bCmdCompressionOff), 1, stdout);
       }
```

`bCmdCompressionOn/Off`를 켜는 모델 목록은 `S821, M04S, P832Pro, Q302(isQ302 조건부), S822`
뿐이다. **`M832`는 이 목록에 없으므로 항상 `else` 분기로 떨어져 `bCmdCompressionOff`
(`1F 11 35 00`)를 쓰고, `compressBitmap()`은 호출되지 않는다.** 즉 M832는 비압축(raw
비트맵) 경로가 확정이다.

## (c) M832의 전체 출력 바이트 순서

StartPage `case M832` (12724–12858)에서 (skipAsk에 관계없이) 다음이 옵션에 따라 조건부로
출력된다 — 순서대로:

1. `bCmdGap` (`1F 11 <PAPER_GAP|PAPER_CONTINUES|PAPER_BLACK>`) — `zeMediaTracking` 옵션이
   있고 media가 gap/continuous/bline이거나, PageSize가 A4/Letter가 아니면 자동으로
   `PAPER_CONTINUES` (12770–12805).
2. `bCmdDensity` (`1F 11 02 <1|2|4>`) 또는 `bCmdSpecial` (`1F 11 37 0x96`) — `Darkness`
   옵션 (12806–12826).
3. **Antiwrinkling(`1F 11 88 xx`)는 M832 case 블록에 없다** — `Antiwrinkling` 체크는
   12227행(M08F/P832Pro/TP86 case)과 12364행(P831 case)에만 존재하며 M832 case
   (12724–12858) 안에는 해당 호출이 전혀 없다. 즉 M832는 antiwrinkling 명령을 절대
   보내지 않는다.

라인 출력 루프 이후 (14611행부터, 페이지 버퍼 조립 단계):

4. 라인별 `OutputLine()` 호출로 `sendBuf`에 1bpp 비트맵을 채움 (아래 (d) 참고). 이 단계는
   stdout에 아무것도 쓰지 않는다 — 버퍼링만 한다.
5. `SendNow()` (14742) — 여기까지 조립된 옵션 바이트들 flush.
6. (`ModelNumber != M832 && != TP86 && != M08F` 등 조건일 때만) 2048바이트 `rubbishData`
   패딩 — **M832는 이 조건에서 제외되므로 패딩 없음** (14747–14752).
7. 압축 마커: M832는 항상 `bCmdCompressionOff` = `1F 11 35 00` (위 (b), 14764행).
8. `bCmdBMP` 8바이트, `1D 76 30 00 xL xH yL yH` (14780–14788):
   ```
   14780  bCmdBMP[4] = bytewidth % 256;              // xL
   14781  //xH
   14782  bCmdBMP[5] = bytewidth / 256;              // xH
   14784  //yL
   14785  bCmdBMP[6] = header.cupsHeight % 256;      // yL
   14786  //yH
   14787  bCmdBMP[7] = header.cupsHeight / 256;      // yH
   14788  fwrite(bCmdBMP, 1, 8, stdout);
   ```
   (기준 파일의 정확한 줄 번호는 14781/14783/14785/14787 — fwrite는 14788. `bCmdBMP[0..3]`은
   고정값 `1D 76 30 00`이며 바뀌지 않는다.) `bytewidth = (header.cupsWidth+7)/8`이며,
   `header.cupsHeight`는 (e)의 패딩이 적용된 이후 값이다.
9. `sendBuf` 원본(비압축) 비트맵 바이트 그대로 전송 (M832는 압축 안 하므로 `SendNow` 루프에서
   그대로 fwrite).
10. 페이지 끝, `EndPage()` 이후 (14912–14920):
    ```
    14912  EndPage(ppd, &header);
    14913  if (ModelNumber == M832) {
    14914      if (bCmdGap[2] == PAPER_CONTINUES &&
                    strcmp(header.cupsPageSizeName, "A4") &&
                    strcmp(header.cupsPageSizeName, "Letter")) {
    14915          M832After = 1;
    14916          bCmdAfter[2] = 0x01;
    14917          fwrite(bCmdAfter, 3, 1, stdout);   // 1B 64 01
                }
            }
    ```
    **조건은 "연속지(PAPER_CONTINUES)이고 페이지 크기 이름이 A4도 Letter도 아닐 때"뿐이다.**
    A4/Letter는 `strcmp(...,"A4")`/`strcmp(...,"Letter")`가 0이 되어 `&&` 전체가 거짓이 되므로
    **A4/Letter에서는 이 페이지별 트레일러(`1B 64 01`)가 전혀 나가지 않는다.**
11. 모든 페이지 처리가 끝난 뒤, `M832After` 플래그가 한 번이라도 켜졌으면 (즉 연속지 비-A4/Letter
    작업이었으면) job 전체의 마지막에 `bCmdAfter[2]=0x02; fwrite(bCmdAfter,3,1,stdout);` (`1B 64
    02`)를 한 번 더 쓴다 (14934–14939). **A4/Letter 작업에서는 `M832After`가 결코 1이 되지
    않으므로 이 job-end 트레일러도 나가지 않는다.**
12. Job 전체가 끝난 뒤 `ModelNumber == 831`(P831, M832 아님) 분기가 아니면
    `fwrite(findpaper, 3, 1, stdout)` (`1F 11 11`)이 무조건 한 번 더 나간다 (14957–14959).
    이건 응답을 기다리지 않는 단순 write이므로 블로킹은 아니지만, M832 출력 스트림 맨 끝에
    3바이트가 더 붙는다는 점은 바이트 단위 비교 시 유의해야 한다.

요약 순서 (M832, A4/Letter, continuous 아닌 경우는 괄호 표시):

```
[bCmdGap] → [bCmdDensity|bCmdSpecial] → (OutputLine 버퍼링, stdout 없음) →
1F 11 35 00 (compression off) → 1D 76 30 00 xL xH yL yH → 원본 비트맵 바이트열 →
(연속지+비A4/Letter일 때만: 1B 64 01) → ... 다음 페이지 반복 ... →
(연속지+비A4/Letter가 한 번이라도 있었으면: 1B 64 02) → 1F 11 11 (job-end, 응답 대기 없음)
```

## (d) 비트 극성 — M832는 반전 없음, MSB-first, gray<=128 → 1

`OutputLine()`의 switch에서 `M08F, P831, S821, S822, M832, Q302, M04S, TP86, P832Pro`가
전부 같은 case 본문을 공유한다 (13401–13409 case 라벨들, 본문 13410–13429):

```
13410      if (Canceled)return;
13411      ptr = Buffer;
13412      bytewidth = (header->cupsWidth + 7) / 8;
13415      for (i = 0; i < (int)bytewidth; i++) {
13417          temp = 0;
13419          for (j = 0; j < 8; j++) {
13420              if ((i * 8 + j) < (int)header->cupsWidth) {
13421                  unsigned char pixelColor = ptr[i * 8 + j];
13422                  if (pixelColor <= 128)
13423                      temp |= (unsigned char)(128 >> j);
13424              }
13425          }
13426          sendBuf[y * (int)bytewidth + i] = temp;
13429      }
```

- `pixelColor <= 128` → 해당 비트를 1로 세팅(`128 >> j`, 즉 `j=0`이 MSB) — **MSB-first
  패킹**.
- 반전 연산(`~`)이 이 case 안에는 전혀 없다. 결과는 `sendBuf`에 그대로 저장된다(압축 전
  단계).

대조: `case TSPL:` (13434–13457)은 동일한 비트 계산을 하지만 `putchar(temp)` 대신
`putchar(~temp)`로 **반전해서 직접 stdout에 쓴다** (13456행 부근). M832는 이 반전이
없고, 게다가 stdout에 직접 쓰지 않고 `sendBuf` 버퍼에 채워 넣었다가 나중에 압축 마커/BMP
헤더 다음에 한꺼번에 fwrite된다는 점도 TSPL과 다르다(TSPL은 라인마다 즉시 stdout에 쓴다).

## (e) 높이 패딩 — 높이만, A4/Letter, `cupsWidth`는 그대로

14611–14636:

```
14611  else if (ModelNumber == M832) {
14612      if (bCmdGap[2] == PAPER_CONTINUES) {
14613          tmpw = header.cupsWidth;
14614          if (!strcmp(header.cupsPageSizeName, "A4")) {
14615              tmph = 295.0 * header.HWResolution[1] / 25.4;
14617          }
14618          else if (!strcmp(header.cupsPageSizeName, "Letter")) {
14619              tmph = 11 * header.HWResolution[1];
14621          }
14622          else {
14623              tmph = header.cupsHeight;
14624          }
14625          if (tmph > header.cupsHeight) {
14626              unsigned char* tempbuf = (unsigned char*)malloc(tmph * tmpw);
14627              memset(tempbuf, 0xFF, tmph * tmpw);
                   for (i = 0; i < header.cupsHeight; i++) {
                       for (j = 0; j < header.cupsWidth; j++) {
                           tempbuf[i * tmpw + j] = tmp[i * header.cupsWidth + j];
                       }
                   }
                   free(tmp);
                   tmp = tempbuf;
                   header.cupsHeight = tmph;
14636              header.cupsWidth = nw = tmpw;
               }
           }
       }
```

핵심 확인 사항:

- 패딩은 `bCmdGap[2] == PAPER_CONTINUES`(연속지)일 때만 발동한다.
- `tmpw = header.cupsWidth`로 **폭은 그대로 복사**(`tmpw`는 원래 폭과 동일한 값)한다 —
  폭을 늘리거나 줄이는 계산이 없다.
- `tmph`는 A4일 때 `295.0mm`, Letter일 때 `11in` 기준으로 해상도(`HWResolution[1]`)를
  곱해 계산한, **더 큰 높이**로 설정된다. `tmph > header.cupsHeight`일 때만 실제로
  버퍼를 새로 만들어 `0xFF`(흰색)로 채우고 원본 데이터를 위쪽에 복사한다.
- 마지막 줄 `header.cupsWidth = nw = tmpw;`는 대입만 할 뿐 **값 자체를 바꾸지 않는다**
  (`tmpw`가 `header.cupsWidth`의 원본 복사본이므로). 즉 `cupsWidth`는 PPD가 선언한 값
  그대로 유지된다.
- 이후 `bytewidth = (header.cupsWidth + 7) / 8;` (14696행, 라인 출력 루프 직전)이
  이 패딩되지 않은 원본 `cupsWidth`로 계산되므로, **PPD가 선언한 폭이 그대로
  `bytewidth`/`bCmdBMP`의 `xL/xH`로 흘러 들어간다.** 패딩은 순수하게 세로(높이) 방향
  프레임 확장이며 가로 폭에는 전혀 손대지 않는다.

## 결론 — `skipAsk==1`에서 M832는 `waitFree()`/용지 상태 루프를 절대 타지 않는다

M832에 대해 `waitFree()`, `getHardVer()`, `GetPaperStatus()`, `GetCoverStatus()` 호출이
등장하는 곳은 StartPage의 `case M832:` 블록 안, **`if (skipAsk == 0) { ... }`
(12725–12750) 단 한 곳뿐**이다. 파일 전체를 통틀어 M832가 이 네 함수를 다른 경로로
호출하는 지점은 없다(다른 skipAsk 지점 12188/12306/12510/14802는 모두 다른 모델
케이스 소속임을 위 (a)에서 확인함; job-end의 `GetPaperStatus()`(14889행)는 Q302 전용,
14977행의 `GetPaperStatus()`는 완전히 주석 처리된 죽은 코드).

따라서 `DEVICE_URI`에 `"bluetooth:"`가 포함되어 `skipAsk = 1`이 설정되면(14033–14036),
M832 StartPage는 `waitFree()`/용지·커버 폴링 루프를 완전히 건너뛰고 바로 옵션 처리로
진입한다. 남는 잠재적 대기 지점은 두 가지뿐이며 둘 다 무한 블로킹이 아니다:

1. Job 종료 시 `fwrite(findpaper, 3, 1, stdout)` (14958행) — 응답을 기다리지 않는 단순
   쓰기(질의 바이트만 스트림에 섞여 나감, side-channel 읽기 없음).
2. `mon()` 감시 스레드 종료 대기 루프 (`while(1){ if(mymon.end) break; sleep(1);}`,
   14963행 부근) — 그 직전 줄(14961행)에서 `mymon.status = 0;`이 설정되면, `mon()`
   스레드(11792–11820)는 루프 최상단에서 `if (mymon.status == 0) break;`(11801–11803행)로
   빠져나가 `mymon.end = 1;`(11818행)을 설정한다. 이미 `cupsBackChannelRead`를 호출한
   상태였다면 그 1초 타임아웃만큼만 더 걸린다 — 이 대기는 초 단위로 유계(bounded)이고
   `skipAsk`와 무관하게 항상 짧다.

즉 **`DEVICE_URI=bluetooth://offline` 트릭은 계획대로 동작한다** — M832 경로에서
무한 대기를 유발하는 것은 오직 `if (skipAsk==0)` 블록의 `waitFree()`/폴링 루프이며,
이는 정확히 이 트릭으로 우회된다. 다만 `socket:`이 포함된 DEVICE_URI는 `isSocket=1`을
설정해(14043행 이하) 별도의 256바이트 청크 전송 경로로 빠지므로 계획대로 금지 대상이다.
