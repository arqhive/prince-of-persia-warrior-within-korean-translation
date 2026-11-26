페르시아의 왕자 전사의 길 한글 패치 v1.0 (GameCube)
====================================================

게임큐브 북미판 Prince of Persia: Warrior Within에 적용하는 비공식 한글 패치입니다.
사용하려면 본인이 소유한 디스크에서 만든 원본 이미지가 필요합니다.


[사용법]

  1. ZIP을 풀고 이 폴더에 원본 이미지를 넣은 다음 「패치하기.bat」을 실행합니다.
     원본 이미지를 배치 파일 위에 끌어 놓는 방법도 있습니다.
  2. 완료하면 원본과 같은 폴더에 이름 끝에 「 (KOR)」가 붙은 이미지가 생깁니다.
     예를 들어 원본이 Warrior Within.iso면 결과는 Warrior Within (KOR).iso입니다.
     원본 이미지는 보관됩니다.

  Windows 10 또는 11 64비트의 기본 Windows PowerShell을 사용합니다.
  임시 작업 공간은 ISO/GCM에서 약 2.2GB, 압축 형식에서 최대 약 4.5GB가 필요합니다.
  두 번째 인자로 기존 출력 폴더를 지정할 수 있습니다.
    패치하기.bat "원본.iso" "D:\Games"


[원본 이미지]

  게임 및 판본   Prince of Persia: Warrior Within, 게임큐브 북미판 G2OE41 리비전 0
  확인 기준     디스크 파일 목록과 변경 대상 게임 파일의 내용 및 크기

  지원 형식            결과
  ---------------      -----------------------------------------------
  ISO, GCM             같은 형식으로 바로 저장
  CISO, WIA, WDF, GCZ   동봉한 wit으로 변환 및 적용 후 같은 형식으로 저장
  RVZ                  Dolphin에서 원본 ISO로 변환 후 적용
  NKit                 원본 ISO로 복원 후 적용

  WIA 결과는 압축하지 않은 WIA 컨테이너로 저장됩니다.
  북미판 원본에 적용하세요. 패치 파일은 원본 이미지 전체의 해시를 요구하지 않습니다.


[오류 메시지]

  지원하는 북미판이 아닙니다           게임, 지역, 리비전을 확인해 주세요.
  필요한 파일이 없습니다             해당 판의 원본 ISO가 맞는지 확인해 주세요.
  원본 게임 파일이 다릅니다           이미 패치됐거나 필요한 파일이 손상된 이미지입니다.
  이미지 크기를 확인해 주세요         일부 파일이 빠졌거나 잘린 이미지입니다.
  RVZ는 Dolphin에서 ISO로 변환        Dolphin 게임 목록에서 원본을 ISO로 변환하세요.
  도구 실행에 실패했습니다             ZIP을 모두 풀었는지, 남은 공간이 충분한지 확인하세요.


[실행]

  - Dolphin에서 확인했습니다.
  - Wii U + Nintendont에서 실행과 UWUVCI 주입을 확인했습니다.
  - 게임 언어를 영어로 설정해야 한글이 표시됩니다.
  - 대사 자막은 「옵션 → 화면 → 자막 → 예」에서 켭니다.


[알려진 한계]

  - 디스크 오류 전용 화면 일부, 오프닝의 영상 속 고지, 엔딩 크레딧,
    디스크 배너와 저장 데이터 설명에는 영문 표기가 남아 있습니다.


[업데이트 기록]

  v1.0 (첫 공개)
    - 컷신과 게임 중 대사 자막 350줄 한글화
    - 메뉴, 저장 안내, 조작법, 지도와 목표, 무기와 시간의 힘 설명 한글화
    - 워헤이븐 Regular 원본 비율, 메모리 카드 안내 행간, 옵션·난이도 제목 정렬 반영


[동봉 도구 라이선스]

  Wiimms ISO Tools 3.05a r8638 및 Cygwin 구성요소
    https://wit.wiimm.de/download.html
    Wiimms ISO Tools 소스: https://download.wiimm.de/source/wiimms-iso-tools/
    Cygwin 소스 패키지: https://cygwin.com/packages/
    GPL 본문은 bin\wit-gpl-2.0.txt에 있습니다.
  xdelta3 3.1.0 (xdelta-gpl 배포본)
    https://github.com/jmacd/xdelta-gpl/releases/tag/v3.1.0
    소스: https://github.com/jmacd/xdelta-gpl/tree/v3.1.0


[제보·문의]

  발생 화면, 원본 이미지 형식, 실행 환경과 오류 문구를 알려 주세요.
  https://github.com/arqhive/prince-of-persia-warrior-within-korean-translation/issues


[면책조항]

  - 개인이 만든 비공식 팬 패치이며 Ubisoft, Nintendo와 관련이 없습니다.
  - 게임 및 글꼴, 이름과 상표의 권리는 각 권리자에게 있습니다.
  - 패치한 게임 이미지는 공유하거나 판매하지 마세요.
  - 사용에 따른 결과는 사용자의 책임입니다. 원본과 저장 데이터의 백업을 권장합니다.
