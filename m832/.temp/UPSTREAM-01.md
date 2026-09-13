# UPSTREAM-01 — vivier/phomemo-tools에 M832 지원 기여

> 이 문서는 detox-printer 쪽에 남기는 기록이다. 기여 코드는 여기 없고 별도 클론에 있다.
> PR: https://github.com/vivier/phomemo-tools/pull/51 (2026-09-13 생성, OPEN) — 같은 커밋의 #50은 브랜치 이름 변경으로 대체되어 닫힘

## 1. 작업 위치와 저장소 관계

| 항목 | 값 |
|---|---|
| 작업 클론 | `~/Data/phomemo-tools-m832` (`vivier/phomemo-tools`를 직접 clone) |
| 브랜치 | `feature/add-M832` (upstream `master` `d0522f0` 위 커밋 1개) |
| 커밋 | `a3257ad cups: add M832 driver` |
| push 대상 | `Justant-source/detox-printer` 저장소의 `feature/add-M832` 브랜치 (remote 이름 `fork`) |
| PR | `vivier:master` ← `Justant-source:feature/add-M832`, 6 files, +247/-1, maintainer 수정 허용 |

**왜 detox-printer 저장소로 push했나**: `Justant-source/detox-printer`는 세션 초반 `vivier/phomemo-tools`를 fork한 뒤 이름을 바꾸고 내용을 덮어쓴 저장소다. GitHub는 계정당 같은 원본을 한 번만 fork할 수 있으므로 `Justant-source/phomemo-tools` 새 fork 생성은 거부됐다(API HTTP 500, 웹 UI "No available destinations to fork this repository"). `gh repo view`로 확인한 결과 detox-printer는 여전히 `isFork: true, parent: vivier/phomemo-tools`다. PR은 브랜치 단위라서 fork 기본 브랜치(detox-printer 프로젝트 내용)와 무관하게 `feature/add-M832` 브랜치의 diff만 올라간다 — 올바르게 동작함을 PR의 changedFiles=6으로 확인.

**주의 (PR이 열려있는 동안)**:
- `Justant-source/detox-printer`의 `feature/add-M832` 브랜치를 삭제·force-push하지 말 것 (PR이 깨진다)
- detox-printer 저장소를 삭제하거나 fork 네트워크에서 분리(Leave fork network)하지 말 것
- 리뷰 반영은 `~/Data/phomemo-tools-m832`에서 커밋 후 `git push fork feature/add-M832`
- 참고: 커밋 중 5회 이상 실패한 fork/PR 생성은 GitHub 부분 장애(githubstatus.com "Partial System Outage")와 겹쳤다

`reference/`는 이 작업 내내 읽기만 했고 수정하지 않았다.

## 2. 보낸 파일

| 파일 | 내용 |
|---|---|
| `cups/drv/phomemo-m832.drv` | 신규. 300dpi, `ColorModel Gray`, 롤 3종(w110h146 기본/w80h106/w53h70, 풀블리드) + A4/Letter(여백 14.17/30pt) |
| `cups/filter/rastertopm832.py` | 신규. `read_ras3` 공유 파서 그대로 + M832 헤더/래스터/꼬리 |
| `cups/Makefile` | install 3줄 |
| `Makefile` | `FILES +=` 2줄 |
| `phomemo-tools.spec` | `%files` 3줄 (M04 커밋 `c40e268`과 같은 방식, 버전/changelog는 건드리지 않음) |
| `README.md` | 4행 모델 목록에 M832 추가 |

## 3. 출처 규칙

벤더 C++ 소스(`QY_Printer-2.1.0.3`)는 비공개·재배포 불가. 기여물에는 **관찰한 와이어 바이트 사실만** 사용하고, 코드는 reference 레포 기존 필터(`rastertopm04.py`) 스타일로 새로 작성했다. `docs/filter-source-map.md`는 내부 분석용이며 PR에 인용하지 않았다. 벤더 PPD의 용지 치수(PaperDimension/ImageableArea)는 물리적 사실값으로 사용했다.

## 4. 우리 결론 → 기여물 매핑

| 우리 쪽 결론 | 기여물 반영 | 확신도 |
|---|---|---|
| `1f 11 0b` + `1f 11 35 00` 헤더, density/heat 없음 | `print_header()` | [확인됨·실물] |
| bCmdBMP `1d 76 30 00 xL xH yL yH`, MSB-first, 1=검정 | `print_raster()` + `invert → convert('1')` | [확인됨·실물 + 바이트 동일 검증] |
| WIDTH_BYTES는 매체 종속 | 하드코딩 없음, `cupsWidth`에서 계산 | [확인됨] |
| 롤 꼬리 `1b 64 01` + `1b 64 02` + `1f 11 11` | `print_and_feed(1)` 페이지별, `(2)` + `query_status()` 작업끝 | [확인됨·실물] (110mm) |
| A4/Letter 꼬리 `1f 11 11`만, 페이지 전체 높이 패딩 | `SHEET_SIZES` 분기, 높이 `round(cupsPageSizeH*HWResolutionV/72)`=3508 (벤더 3484 상수 복사 안 함) | [확인됨·출력바이트 / 미검증·실물] |
| 80mm/53mm | 110mm와 같은 롤 동작으로 확장 | [미검증·추정] |
| 수평 오프셋 +2mm | **넣지 않음** — 개체별 보정값이라 범용 필터에 부적합 | — |
| Bluetooth | backend 미수정 | [미검증] |

## 5. 의도적으로 다르게 한 점

- **롤 용지 뒤쪽 공백 줄 크롭**: 벤더는 전체 높이(1725줄)를 보내지만, 우리는 M04 필터처럼 내용 높이까지만 보내 용지 절약
- **RGB 대신 Gray**: 벤더 PPD는 `cupsColorSpace 1`(RGB)이지만 repo의 다른 4개 필터와 맞춤
- **M832D 제외**: 이름+옵션 2개만 다른 미검증 모델명이라 PR 본문에 "확인되면 추가"로 안내
- **M04 필터 버그 미복사**: `rastertopm04.py`의 `print_raster()`가 인자 `file` 대신 바깥 `stdout`에 쓰는 버그를 따라하지 않음

## 6. 로컬 검증 결과

| 검증 | 결과 |
|---|---|
| `ppdc -z drv/phomemo-m832.drv` / `drv/*` 전체 | exit 0, 12개 PPD 전부 빌드 |
| PPD 속성 | `cupsFilter rastertopm832`, PageSize 5종, A4 `ImageableArea 14.17 30 580.83 812`, Letter `14.17 30 597.83 762`, 롤 풀블리드 |
| 110mm 롤 (t3n_corner.png) | 헤더·폭(163)·꼬리 9바이트 일치, **겹치는 비트맵 16,300바이트 중 차이 0** (실물 인쇄로 검증된 `captures/filter/w110h146/t3n.bin2` 대비) |
| A4 시트 (t3_corner.png) | 3508줄, 원본 3257줄보다 패딩됨, 꼬리 `1f1111` 3바이트뿐, 패딩 구간 전부 0x00 |
| 실물 인쇄 (새 필터로) | 안 함 — 비트맵 바이트 동일로 대체 |

### 검증 중 발견해서 계획과 다르게 고친 것 2가지

1. **`CustomMedia`가 A4/Letter의 `*PageSize` PostScript 코드를 빈 문자열로 만듦** (`*PageSize A4/A4: ""`). 여백은 맞았지만 불완전해서, `HWMargins 14.17 30 14.17 30` 전환 후 `media.defs`의 표준 `MediaSize "A4"`/`"Letter"`를 쓰는 방식으로 교체 → PageSize/PageRegion 정상
2. **`cupsPageSizeName`에 null 뒤 잔여 바이트가 섞여 옴**: A4 raster에서 `'A4\x00ter'`(이전 값 "Letter"의 꼬리). 공유 파서 `read_ras3()`의 `rstrip('\x00')`은 끝의 null만 지워서 `== 'A4'` 비교가 실패 → A4가 롤로 처리됨(93줄 크롭). 공유 파서는 그대로 두고 필터에서 `split('\x00', 1)[0]`로 첫 null 앞만 사용. 기존 4개 필터는 이 필드로 분기하지 않아 드러난 적 없는 잠재 문제

## 7. 상태 기록

- 2026-09-13: PR #50(`cups-m832`) 생성 → 같은 커밋 `a3257ad`를 `feature/add-M832` 브랜치로 옮겨 PR #51 생성, #50은 "Superseded by #51" 댓글과 함께 닫고 `cups-m832` 브랜치 삭제. 리뷰 코멘트·머지 결과가 오면 아래에 append

- 2026-09-13: detox-printer에도 사본 보관 — `m832/cups/drv/phomemo-m832.drv`, `m832/cups/filter/rastertopm832.py` (커밋 `a3257ad`에서 그대로 복사, blob 해시 동일). phomemo-tools 저장소 전체를 merge하지 않은 이유: `feature/add-M832`는 phomemo-tools 히스토리 위의 브랜치라 detox-printer master와 공통 조상이 없어, merge 시 phomemo-tools 루트 전체가 들어오고 `.gitignore`가 충돌하며 `reference/`와 중복되기 때문. PR 반영(리뷰 수정 등)은 계속 `~/Data/phomemo-tools-m832`에서 하고, 필요할 때 이 사본을 다시 동기화한다
- **주의**: GitHub `Justant-source/detox-printer`의 `feature/add-M832` 브랜치는 PR #51의 head다. detox-printer 로컬에서 그 이름으로 push하지 말 것

## 8. 이 프로젝트에 미치는 영향

없음. detox-printer의 `src/07_print_image.py` pyusb 경로와 G단계(cron)는 CUPS를 쓰지 않으므로 무관. 업스트림에 머지되면 CUPS 경로가 필요할 때 선택지가 하나 생긴다.
