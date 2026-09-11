# 아침 한 송이 · Morning Bloom

하루 1~3분, 바탕화면 한쪽의 꽃을 돌보는 PC 힐링 육성 게임.

**목표: Python + PySide6 / 2D 전용 / Windows 우선**

**Python 초안 구현 완료:** 루트의 `run-python.bat`으로 실행하세요. [Python 실행 방법·구현 상태](python/README.md)를 확인하세요.

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

- 정사각 창, 제목 드래그 이동, 항상 위 표시, 창 불투명도 10~100%, 복구 버튼
- 데이터 카탈로그 기반 데이지·튤립 5단계 애니메이션과 물방울 피드백
- 첫 꽃 60초 튜토리얼, 이후 현실 시간 성장, 무료 물주기·분무
- 테라리움 보관, 품종별 씨앗 구매·파종, 품종별 꽃 판매
- 72시간 오프라인 상한, 24시간 돌봄 유예, 회복, 휴가 모드
- 30초·행동·정상 종료 저장, 임시 파일 교체 및 직전 정상 백업
- 별도 데모 저장, 실제 게임 저장에 영향을 주지 않는 시간 가속

**아직 구현하지 않은 기능:** 5개 전체 화면, 추가 화분, 나머지 식물 3종, 햇빛·비료 보너스, 온도, 장식장, 꽃꽂이, 교배, 트레이/클릭 통과, OS 알림. [구현 상태](docs/implementation-status.md)에서 기획과 실제 구현을 구분합니다.

## 저장 데이터

Windows 기본 위치: `%APPDATA%\MorningBloom\` (설정에서 `저장 폴더 열기`로 확인).

- `garden.json`: 실제 재배
- `demo-garden.json`: 데모
- `.bak`: 직전 정상 저장, `.tmp`: 저장 교체용

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
- [구조와 Windows 검증 방법](docs/development.md)

원본 기획: [꽃 키우기 프로젝트](https://app.notion.com/p/32ca1215692880a58ae2ee9d85ed96a1).

## 저장소

기획서와 초기 시제품은 `badbed7/morning-bloom`에 저장되어 있습니다.

## 저작물

앱 코드는 프로젝트 소유자의 별도 라이선스 결정 전까지 All rights reserved입니다. 꽃·화분은 프로토타입용 코드 도형입니다. 포함된 Noto Sans CJK KR 서브셋은 [SIL Open Font License](assets/fonts/OFL.txt)를 따릅니다. 현재 AI 생성 이미지나 음원은 포함하지 않았습니다.


최신 Python 기능: [상점·가방·화분 2개](python/README.md). 후속 기획: [꽃별 성장 시간과 가격 차별화](docs/next-proposals.ko.md).
