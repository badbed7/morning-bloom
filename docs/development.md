# 개발 구조와 검증

## 구조

- `plant_state.gd`: 순수 게임 상태. UI나 디스크에 의존하지 않는 시간 계산·행동.
- `save_store.gd`: JSON 유효성 검사, 임시 저장, 정상 백업, 복구.
- `main.gd`: 창·UI·입력·저장 시점. 실제 시각을 상태에 전달.
- `flower_view.gd`: 코드 도형 기반 임시 아트와 짧은 애니메이션.
- `tests/test_runner.gd`: 외부 테스트 플러그인 없이 실행하는 Godot 테스트.

## 시간 규칙

UTC Unix 초로 계산하고 UI에는 남은 시간을 표시합니다. 한 번의 재접속은 72시간까지만 성장 및 돌봄을 계산하고 나머지는 두 시계 모두 휴면 처리합니다. 필수 돌봄 만료 중 가장 이른 시각에 24시간 유예를 더해 성장 정지 경계를 구합니다. 완료 식물은 손상되지 않습니다. 시간 역행에서는 이전 기준시각을 유지해 중복 성장을 막습니다.

## 저장 규칙

메모리 상태 검증 → 임시 파일 쓰기·flush → 임시 파일 재검증 → 기존 정상 파일만 백업 → 임시 파일을 주 파일로 교체. 오류 시 기존 기록을 보존하고 안내합니다. 최신 버전의 저장 또는 손상된 주 파일과 백업을 발견하면 자동 초기화하지 않습니다.

## Windows 수동 확인

| 항목 | 확인 방법 | 기대 결과 |
| --- | --- | --- |
| 첫 실행 | Godot 내장 실행을 끄고 F5 | 우하단 독립 정사각 창 |
| 입력 | 메모장 입력 중 게임 관찰 | 주기적 갱신이 포커스를 빼앗지 않음 |
| 이동·복구 | 제목 드래그, 재실행, 모니터 분리 | 위치 유지 또는 화면 안 복구 |
| 투명도 | 10%→100%, 설정 열기 | 게임만 흐려지고 설정은 읽을 수 있음 |
| DPI | Windows 배율 100·150·200% | 주요 버튼·글자가 창 밖으로 넘치지 않음 |
| 돌봄 | 씨앗 심기, 물·분무 | 애니메이션, 중복 클릭 성장 이득 없음 |
| 첫 순환 | 60초 대기, 보관, 판매, 재파종 | 첫 꽃 50G, 이후 24시간 성장 |
| 오프라인 | 종료 후 재실행 | 경과 시간만큼 복원, 중복 보상 없음 |
| 손상 | 백업 후 테스트 파일 JSON 일부 훼손 | 정상 백업 복구, 둘 다 손상이면 덮어쓰기 금지 |
| 데모 | `-- --demo` 실행 | +6시간 버튼, 실제 저장 영향 없음 |

이 환경의 Linux 검증이 Windows 실기 검증을 대체하지 않습니다. 배포 전 Windows Export Template을 설치하고 Export Preset에서 Windows Desktop을 생성하세요. 실행 파일은 `builds/`에 내보내며 저장소에 포함하지 않습니다.

## 기술 근거

- [Godot Window](https://docs.godotengine.org/en/stable/classes/class_window.html)
- [Godot DisplayServer](https://docs.godotengine.org/en/stable/classes/class_displayserver.html)
- [Godot Windows export](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_windows.html)
- 검증 엔진: Godot 4.7.2 stable 공식 Linux 바이너리.
