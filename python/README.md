# Morning Bloom Python 초안

Python 3.11~3.12와 PySide6 6.8.3을 사용하는 2D 데스크톱 시제품입니다.

## Windows 실행

1. Python 3.12 **64비트**를 설치합니다(Python Launcher 포함). 다른 Python 버전과 함께 설치해도 됩니다.
2. 저장소 전체를 다운로드하고 압축을 풉니다.
3. 루트의 `run-python.bat`을 더블클릭합니다. 첫 실행은 가상환경과 의존성을 설치하므로 인터넷이 필요합니다.

실행 파일은 Python 3.12를 명시적으로 선택하고 `.venv-py312` 환경을 검사합니다. 이전 `.venv`는 사용하거나 삭제하지 않습니다.

### PySide6 설치 오류가 발생했다면

`PySide6==6.8.3`은 Python 3.14 이상을 지원하지 않습니다. 기존 실행 파일의 `py -3`이 최신 Python을 선택해 발생할 수 있습니다. Python 3.12 64비트를 설치하고 최신 `run-python.bat`으로 다시 실행하세요. pip 업데이트만으로는 해결되지 않습니다. `py -0p`로 설치된 Python을 확인할 수 있습니다.

직접 실행할 수도 있습니다.

```powershell
cd python
py -3.12 -m venv .venv-py312
.venv-py312\Scripts\python.exe -m pip install -r requirements.txt
.venv-py312\Scripts\python.exe -m morning_bloom
# 독립 저장 + 6시간 가속 버튼
.venv-py312\Scripts\python.exe -m morning_bloom --demo
```

## 구현 범위

- 데이지 1종, 성장 5단계, 첫 개화 60초 / 이후 24시간
- 심기, 물주기, 분무, 개화 꽃 보관, 보관 꽃 50G 판매, 씨앗 부족 시 20G 재파종
- 120G와 씨앗 1개로 시작, 첫 수확 시 씨앗 1개 추가
- 48시간 돌봄 주기, 24시간 유예 후 성장 정지, 무료 회복
- 72시간 오프라인 계산 상한, 휴가 모드, 시스템 시간 역행 방어
- 제목 드래그, 항상 위, 창 불투명도, 창 위치 저장
- 행동 직후·30초마다·종료 시 저장, 정상 백업, 손상 및 미래 버전 보호
- 동일 저장 파일의 앱 중복 실행 방지

물·분무는 만료 전 12시간부터 타이머를 갱신합니다. 그보다 이른 클릭은 애니메이션만 보여주며 성장을 가속하지 않습니다. 닫기는 저장 후 종료입니다.

## 저장 위치

Qt의 `AppLocalDataLocation` 아래 `MorningBloomPython` 앱 폴더를 사용합니다. Windows는 일반적으로 `%LOCALAPPDATA%\MorningBloomPython`입니다. 일반 게임 `garden.json`, 데모 `demo-garden.json`, 직전 백업 `.json.bak`을 사용합니다. Godot 저장 파일은 자동으로 읽거나 변경하지 않습니다.

손상된 본 파일은 정상 백업으로 복구합니다. 양쪽이 모두 손상되거나 더 높은 저장 버전이면 시작을 멈추고 원본을 보존합니다. 저장 실패 시 화면에 오류를 표시하며 종료 여부를 선택할 수 있습니다.

## 검증

```powershell
cd python
$env:QT_QPA_PLATFORM = 'offscreen'
.venv-py312\Scripts\python.exe -m unittest discover -s tests -v
```

2026-09-10 Linux에서 상태·저장 테스트 9개와 실제 Qt 버튼을 누르는 UI 통합 테스트 1개가 통과했습니다. 오프스크린 화면 렌더링도 확인했습니다. Windows의 실제 창 이동·최상단·불투명도·배율·다중 모니터와 배치 실행은 현지 수동 검증이 필요합니다. CI는 Windows/Python 3.12로 같은 테스트를 실행하도록 추가했습니다.

## 다음 범위

별도 상점·가방 화면, 추가 화분, 식물 5종, 햇빛·비료·온도, 장식장·꽃꽂이, 트레이·OS 알림, 실행 파일 패키징은 미구현입니다. 현재 그림은 QPainter로 그린 2D 도형이며 최종 아트가 아닙니다. 시제품 창은 420×650이며 화면 너비 20% 자동 크기 조절은 후속 작업입니다.

기존 루트 Godot 프로젝트와 관련 문서는 이전 시제품 기록입니다. 2026-09-10의 기획 문서에 있는 ‘Python 미구현’ 문구는 그 시점의 상태이며, 최신 구현 상태는 이 문서를 따릅니다.
