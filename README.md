# 아침 한 송이 · Morning Bloom

하루 1~3분, 바탕화면 한쪽의 꽃을 돌보는 PC 힐링 육성 게임.

**목표: Python + PySide6 / 2D 전용 / Windows 우선**

**Python 2D 초안 구현:** 루트의 `run-python.bat`으로 실행하세요. [Python 실행 방법·구현 상태](python/README.md)를 확인하세요.

아래 Godot 실행·테스트 안내는 보존된 이전 시제품에 해당합니다.

## 실행

1. [Godot 공식 다운로드](https://godotengine.org/download/windows/)에서 **Standard 4.7.2**를 설치합니다(.NET 버전 불필요).
2. Godot 프로젝트 목록에서 이 폴더의 `project.godot`를 가져옵니다.
3. **F6가 아닌 F5**로 프로젝트를 실행합니다. 편집기의 내장 게임 실행(Embed Game)을 끄면 독립 플로팅 창을 확인할 수 있습니다.
4. `씨앗 심기`를 누릅니다. 첫 꽃은 60초, 이후 데이지는 24시간에 자랍니다.
5. 개화 후 보관하거나, 보관함에서 50G에 판매하고 새 씨앗을 심습니다.

CLI로도 실행할 수 있습니다. 아래 `godot`는 내려받은 Godot 실행 파일 경로입니다.

```sh
godot --path .
# 별도 저장 파일을 사용하는 개발 데모 (+6시간 버튼)
godot --path . -- --demo
```

## 이번 버전

- 정사각 창, 제목 드래그 이동, 항상 위 표시, 창 불투명도 10~100%
- 데이터 카탈로그 기반 데이지·별꽃·튤립 5단계 애니메이션과 물방울 피드백
- 모든 꽃은 첫 물주기 후 성장, 첫 데이지 60초 튜토리얼
- 별꽃 3시간·데이지 24시간·튤립 48시간의 품종별 성장과 가격
- 튤립 중간 물주기와 지연 성장, 선택 분무의 판매가 10% 보너스
- 잔디 정원에 꽃 화분 전시, 돈주머니 영역으로 드래그 판매
- 정원 꽃의 20분 주기 햇빛 생산, 클릭 수집 효과와 대기 상한 9개
- 햇빛으로 구매하는 크림·하늘·라벤더 정원 배경과 무료 재적용
- 화분·상점·정원 순환 화살표 메뉴, 오른쪽 아래 별도 설정
- 72시간 오프라인 상한, 두 화분 독립 성장, 휴가 모드
- v1~v4 저장의 v5 이전, 30초·행동·정상 종료 저장과 직전 정상 백업
- 설정에서 개발자 모드 전환, 별도 테스트 저장의 `+6시간` 시간 가속

**아직 구현하지 않은 기능:** 화분 스킨·정원 소품·수집 효과 스킨, 세 번째 이후 화분, 비료, 온도 효과, 장식장, 꽃꽂이, 교배, 트레이/클릭 통과, OS 알림. [햇빛 상호작용 기획·구현](docs/sunlight-interaction.ko.md)과 [Python 구현 상태](python/README.md)를 확인하세요.

## Python 저장 데이터

Windows 기본 위치: `%LOCALAPPDATA%\MorningBloomPython\`.

- `garden.json`: 실제 재배
- `demo-garden.json`: 개발자 모드의 별도 테스트 정원
- `.json.bak`: 직전 정상 저장
- `.json.v3-migration.bak`: v1~v3에서 처음 이전할 때의 원문
- `.tmp`: 저장 교체용 임시 파일

미래 버전 또는 복구 불가능한 저장 파일은 자동으로 덮어쓰지 않습니다. 오류 안내를 확인하고 원본을 백업한 뒤 복구합니다. 창의 X는 **저장 후 완전 종료**이며 트레이 최소화가 아닙니다.

## 테스트

```sh
godot --headless --path . --editor --import
godot --headless --path . --script tests/test_runner.gd
godot --headless --path . --script tests/ui_smoke.gd -- --demo
```

시간 경계·시간 역행·오프라인 상한·휴가·복구·중복 수확 및 판매·저장 손상·버전 호환을 검증합니다. GitHub Actions에서 동일한 테스트를 실행하도록 구성했습니다. Windows 창 동작과 배율은 별도 수동 점검 대상입니다.

## 문서

- [승인된 게임 기획서 — GitHub 보기](docs/game-design-v0.1.ko.md)
- [승인된 기획서 DOCX](docs/game-design-v0.1.ko.docx)
- [현재 구현 범위 및 다음 작업](docs/implementation-status.md)
- [v0.4 성장·돌봄·경제 상세 기획](docs/game-design-v0.4.ko.md)
- [정원·순환 메뉴 수정 기획 및 작업본 검증](docs/garden-ui-revision.ko.md)
- [햇빛 클릭 수집·꾸미기 상점 기획과 개발자 모드](docs/sunlight-interaction.ko.md)
- [타이쿤 반복 돌봄·비료 미니게임 변경안 — 미구현](docs/tycoon-care-fertilizer.ko.md)
- [구조와 Windows 검증 방법](docs/development.md)

원본 기획: [꽃 키우기 프로젝트](https://app.notion.com/p/32ca1215692880a58ae2ee9d85ed96a1).

## 저장소

기획서와 초기 시제품은 `badbed7/morning-bloom`에 저장되어 있습니다.

## 저작물

앱 코드는 프로젝트 소유자의 별도 라이선스 결정 전까지 All rights reserved입니다. 꽃·화분은 프로토타입용 코드 도형입니다. 포함된 Noto Sans CJK KR 서브셋은 [SIL Open Font License](assets/fonts/OFL.txt)를 따릅니다. 현재 AI 생성 이미지나 음원은 포함하지 않았습니다.


최신 Python 기능: [품종별 성장·돌봄·경제와 상점·정원·화분 2개](python/README.md). 후속 기획: [다음 개발 제안](docs/next-proposals.ko.md).

## Windows 실행 파일과 업데이트

현재 EXE 빌드·릴리스 게시·자동 업데이트 배포 작업은 보류합니다. 이번 변경은 소스 코드와 기획 문서에만 반영합니다.

Python 설치 없이 실행하는 배포본은 Releases에 게시합니다. [자동 업데이트·배포 채널 설정](release/README.md)을 확인하세요. 소스 저장소는 비공개이며 일반 사용자용 자동 업데이트는 공개 배포 저장소 연결이 필요합니다.
