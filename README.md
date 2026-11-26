# 페르시아의 왕자 전사의 길 (GC) 한글 패치

게임큐브 북미판 `G2OE41` 리비전 0용 비공식 한글 패치입니다. 최신 시험판은 **v0.7.0**입니다.

- 메뉴, 메모리 카드 안내, 조작법, 지도 및 목표, 무기·시간의 힘 설명을 한글화했습니다.
- 대사 자막 350줄에 한국어를 적용하고 게임큐브판 표시 시간을 유지했습니다.
- 워헤이븐 Regular를 20px로 그려 각 글자의 획 비율과 기준선을 유지했습니다.
- 영어 메뉴 리소스를 사용합니다. 대사 자막은 게임의 **옵션 → 화면 → 자막 → 예**에서 켭니다.

## 패치 적용

본인이 덤프한 북미판 원본 ISO와 7차 xdelta가 필요합니다. RVZ는 Dolphin에서 ISO로 변환합니다.

1. 원본 ISO와 패치 파일을 준비합니다.
2. Python 3.13에서 `python -m pip install pyxdelta==0.3.0`을 실행합니다.
3. 다음과 같이 적용하고 결과 ISO를 Dolphin에서 엽니다.

```powershell
python patcher/apply_patch.py "input/original.iso" "release/PopWW-Korean-Warhaven-native-v07.xdelta" "build/PopWW-Korean.iso"
```

패처는 입력과 결과의 SHA-256을 확인합니다. 소스 ISO와 출력 ISO의 크기는 1,459,978,240바이트입니다. [원본·패치 검증값](patcher/manifest.json)

## 직접 빌드

빌드는 Python 3.13에서 검증했습니다. 원본 ISO와 워헤이븐 Regular 파일을 로컬에 준비합니다.

```powershell
python -m pip install -r requirements.txt
python tools/build.py "input/original.iso" "build/PopWW-Korean.iso" --font "input/WarhavenR.woff2"
```

빌더는 원본에서 메뉴와 자막을 읽어 한국어 리소스를 만들고, 표시 시간과 재압축된 데이터를 확인합니다. v0.7.0에서 사용한 워헤이븐 파일의 SHA-256은 `46931a692a0dccf6c3f8c3d2a8ec11521157bf8f1618228b4a516aad210b9f85`입니다. [빌드와 번역 수정 안내](docs/build.md)

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| [`tools/`](tools/) | 원본 ISO를 읽고 한국어 리소스와 ISO를 조립하는 도구 |
| [`translations/ko/`](translations/ko/) | 메뉴, 시스템, 대사의 한국어 번역 |
| [`patcher/`](patcher/) | xdelta 적용 도구와 릴리스 검증값 |
| [`docs/`](docs/) | 빌드·번역 및 확인 범위 |
| `input/`, `build/`, `release/` | 로컬 입력, 결과 ISO, 배포 패치 |
| `work/` | 기존 분석과 검수 작업 공간 |

원본과 패치된 게임 이미지, 추출한 영어 리소스, 글꼴 파일과 실행 캡처는 Git에서 제외합니다.

[변경 내역](CHANGELOG.md)

## 크레딧

한국어 대사는 프로젝트에 제공된 모바일판 번역을 토대로 게임큐브판 자막과 대조했습니다. 워헤이븐의 제작사는 넥슨입니다. 게임 및 글꼴의 권리는 각 권리자에게 있습니다.
