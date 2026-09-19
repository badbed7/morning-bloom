# 아침 한 송이 · Morning Bloom

하루 1~3분, 바탕화면 한쪽의 꽃을 돌보는 PC 힐링 육성 게임.

**목표: Python + PySide6 / 2D 전용 / Windows 우선**

**Python 실행:** Release의 Python-BAT ZIP을 풀고 `run-python.bat`으로 실행하세요. 매번 GitHub 최신 버전을 확인하고 기존 정원을 유지하며 업데이트합니다. [Python 실행 방법·구현 상태](python/README.md)를 확인하세요.

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

- 정사각 창, 제목 드래그 이동, 작업 표시줄 최소화, 항상 위 표시, 창 불투명도 10~100%
- 데이터 카탈로그 기반 데이지·별꽃·튤립 5단계 애니메이션과 물방울 피드백
- 모든 꽃은 첫 물주기 후 성장, 첫 데이지 60초 튜토리얼
- 별꽃 3시간·데이지 24시간·튤립 48시간의 품종별 성장과 가격
- 새 재배는 물 30분·분무 15분 간격의 선택 돌봄, 성장 -3분·-1분과 첫 분무 판매가 10% 보너스
- 미니게임 3라운드 중 2회 성공으로 비료 1개, 비료 사용 시 선택 화분 성장 -10분
- 비료 보유 상한 5개, 공통 보상 대기 3분과 화면의 초 단위 카운트다운, 작물당 비료 단축 상한 25%
- 잔디 정원에 꽃 화분 전시, 돈주머니 영역으로 드래그 판매
- 화분 화면의 보관 꽃 목록과 우클릭 플로팅·복귀
- 정원 꽃의 20분 주기 햇빛 생산, 클릭 수집 효과와 대기 상한 9개
- 아이콘으로 선택하는 정원 배경과 화분 스킨, 햇빛 구매·무료 재적용
- 화분·상점·정원 순환 화살표 메뉴, 오른쪽 아래 별도 설정
- 개별 재배 화분은 양 끝에서 멈추는 좌우 슬라이드로 선택, 화분 번호·총 개수·꽃 이름 표시
- 재배·상점의 씨앗 봉투 아이콘 선택, 크림색·세이지색 코티지 UI
- 최대 네 화분의 순차 구매·독립 성장과 전체 돌봄 준비 요약
- 알림과 돌봄 상태가 바뀌어도 유지되는 화분 그림 크기
- 72시간 오프라인 상한, 휴가 중 성장·돌봄·비료 보상 대기 정지
- v1~v7 저장의 v8 이전, 기존 재배는 수확까지 옛 규칙 유지, 30초·행동·정상 종료 저장과 직전 정상 백업
- Google 계정 연결 시 변경된 로컬 정원을 5분마다 비공개 Drive 앱 데이터에 자동 백업
- 설정에서 개발자 모드 전환, 별도 테스트 저장의 `+6시간` 시간 가속

**아직 구현하지 않은 기능:** 다섯·여섯 번째 화분, 일괄 돌봄, 정원 소품·수집 효과 스킨, 온도 효과, 장식장, 꽃꽂이, 교배, 트레이/클릭 통과, OS 알림. [타이쿤 돌봄·비료](docs/tycoon-care-fertilizer.ko.md)와 [Python 구현 상태](python/README.md)를 확인하세요.

## Python 저장 데이터

Windows 기본 위치: `%LOCALAPPDATA%\MorningBloomPython\`.

- `garden.json`: 실제 재배
- `demo-garden.json`: 개발자 모드의 별도 테스트 정원
- `.json.bak`: 직전 정상 저장
- `.json.v3-migration.bak`: v1~v3에서 처음 이전할 때의 원문
- `.json.v5-migration.bak`: v5에서 v6으로 처음 이전할 때의 원문
- `.json.v6-migration.bak`: v6에서 v7로 처음 이전할 때의 원문
- `.json.v7-migration.bak`: v7에서 v8로 처음 이전할 때의 원문
- `.cloud-sync.json`: Google 자동 백업의 마지막 성공 지문(토큰 없음)
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
- [타이쿤 반복 돌봄·비료 미니게임 기획·첫 구현](docs/tycoon-care-fertilizer.ko.md)
- [구조와 Windows 검증 방법](docs/development.md)

원본 기획: [꽃 키우기 프로젝트](https://app.notion.com/p/32ca1215692880a58ae2ee9d85ed96a1).

## 저장소

기획서와 초기 시제품은 `badbed7/morning-bloom`에 저장되어 있습니다.

## 저작물

앱 코드는 프로젝트 소유자의 별도 라이선스 결정 전까지 All rights reserved입니다. 꽃·화분은 프로토타입용 코드 도형입니다. 포함된 Noto Sans CJK KR 서브셋은 [SIL Open Font License](assets/fonts/OFL.txt)를 따릅니다. 현재 AI 생성 이미지나 음원은 포함하지 않았습니다.


최신 Python 기능: [네 화분·반복 돌봄·비료·아이콘 상점과 정원 꾸미기](python/README.md). 후속 기획: [다음 개발 제안](docs/next-proposals.ko.md).

## Windows 실행 파일과 업데이트

최신 [v0.7.3 Release](https://github.com/badbed7/morning-bloom/releases/tag/v0.7.3)는 바탕화면 꽃을 일반 폴더·앱보다 위에 표시하고 비료 보상 대기시간을 실시간으로 보여 줍니다. Python-BAT ZIP 또는 Windows-x64 ZIP을 받아 전체 압축을 풀고 실행하세요. v0.7.0부터 제공한 자동 업데이트와 v0.7.2의 Google 계정·비공개 Drive 백업·복원도 그대로 유지합니다.

Python BAT는 Python 3.12 64비트로 실행하며, EXE는 Python 설치가 필요 없습니다. 사용자 배포에는 MSIX를 사용하지 않습니다. v0.6.0 이하를 쓰던 사용자는 v0.7.0 런처로 한 번 교체하면 이후 실행부터 자동 업데이트됩니다.

공개 저장소의 최신 Release에서 인증 없이 업데이트를 받습니다. 게임 저장은 `%LOCALAPPDATA%/MorningBloomPython`에 보존합니다. [실행 순서·실패 복구·새 버전 게시](release/README.md)를 확인하세요.
