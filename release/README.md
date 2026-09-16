# Windows 배포와 자동 업데이트

## Microsoft Store MSIX

Smart App Control이 켜진 PC에는 Microsoft Store 배포를 권장합니다. Store 제출본은 현재 런처를 넣지 않고 `MorningBloomGame.exe`와 런타임 전체를 MSIX로 묶습니다. 인증을 통과한 패키지는 Microsoft Store가 서명하고 업데이트도 Store가 처리합니다. 별도 PFX 인증서는 필요하지 않습니다.

최초 1회:

1. [Partner Center](https://partner.microsoft.com/dashboard)에서 Windows 앱 개인 개발자로 등록합니다.
2. **Apps and games → New product → MSIX or PWA app**에서 앱 이름을 예약합니다.
3. **Product management → Product identity**의 `Name`, `Publisher`, `Publisher display name`을 복사합니다. 대소문자까지 그대로 사용해야 합니다.
4. GitHub Actions의 **Store MSIX package → Run workflow**에서 세 값을 입력합니다.
5. 완료된 `MorningBloom-Store-MSIX` artifact의 `.msix`를 내려받아 Partner Center 제출의 **Packages**에 올립니다.
6. 가격·카테고리·연령 등급·스토어 설명·스크린샷·지원 정보를 채운 뒤 인증을 제출합니다.

`release/VERSION`의 `0.5.0`은 Store용 `1.5.0.0`으로 변환합니다. MSIX 네 번째 버전은 Store 예약 값인 `0`으로 유지합니다. 이후 제출은 `release/VERSION`을 올려 더 높은 패키지 버전을 만듭니다.

로컬 수동 패키징은 Windows 10/11 SDK의 `MakeAppx.exe`가 필요합니다. 먼저 `python release/build_windows.py`를 실행한 뒤 다음 환경 변수를 설정하고 실행합니다.

```powershell
$env:STORE_IDENTITY_NAME = 'Partner Center의 Name'
$env:STORE_PUBLISHER = 'Partner Center의 Publisher'
$env:STORE_PUBLISHER_DISPLAY_NAME = 'Partner Center의 Publisher display name'
python release/build_msix.py
```

출력은 `release-output/MorningBloom-<버전>-Store-x64.msix`입니다. 로컬 파일은 Store 제출 전까지 서명되지 않았으므로 다른 PC에 직접 배포하지 않습니다. Store 인증용 매니페스트는 Windows 10 2004 이상, x64, `packagedClassicApp`/`mediumIL`과 `runFullTrust`를 선언합니다. [Microsoft MSIX 수동 패키징](https://learn.microsoft.com/windows/msix/desktop/desktop-to-uwp-manual-conversion), [Store 패키지 요구 사항](https://learn.microsoft.com/windows/apps/publish/publish-your-app/msix/app-package-requirements), [코드 서명 선택지](https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options)를 따릅니다.

기존 저장 경로 코드는 유지됩니다. 패키지 앱의 새 AppData 쓰기는 Windows가 앱별 저장소로 가상화하며 업데이트 뒤에도 유지되지만, 앱 제거 시 함께 삭제될 수 있습니다. 제거 전에는 게임 내보내기 기능이 아직 없으므로 `%LOCALAPPDATA%\MorningBloomPython` 저장 파일을 별도 백업합니다.

## 사용자 실행

Releases의 `MorningBloom-0.4.0-Windows-x64.zip`을 받고 전체 압축을 푼 다음 `MorningBloom.exe`를 실행합니다. Python 설치는 필요 없습니다. 같은 폴더의 `MorningBloom-game.zip`과 `bundled-update.json`도 함께 보관합니다.

런처가 실행할 때마다 공개 배포 저장소의 최신 정식 Release에서 `update.json`을 확인합니다. 더 높은 버전이면 ZIP 다운로드 → SHA-256 및 크기 검사 → 별도 폴더 압축 해제 → 격리된 실행 점검 → 활성 버전 변경 → 게임 실행 순서로 진행합니다. 다운로드나 새 버전 점검이 실패하면 현재 설치 버전을 실행합니다. 최초 배포 ZIP 자체에도 게임이 있어 첫 실행도 오프라인으로 가능합니다.

이미 실행 중인 게임은 강제로 종료하지 않습니다. 런처는 게임 종료까지 잠금을 유지하므로 두 런처가 동시에 업데이트하지 않습니다. 현재 게임의 내부 잠금도 유지합니다. 업데이트는 다음 실행 때 적용됩니다.

공개 업데이트 채널이 없어도 새 배포 ZIP을 받아 전체 압축을 풀고 실행하면 포함된 버전으로 기존 설치를 갱신합니다. 포함된 버전이 더 오래됐거나 실행 점검에 실패하면 기존 설치를 유지합니다.

게임 저장: 기존 `%LOCALAPPDATA%\MorningBloomPython`. 설치 파일과 업데이트 로그: `%LOCALAPPDATA%\MorningBloomLauncher`. 저장 파일은 다운로드·교체 대상이 아닙니다. 새 게임의 기존 저장 이전 로직을 사용합니다. 이전 실행 파일은 남겨두지만 저장 형식이 달라질 수 있어 임의로 저장을 되돌리지 않습니다.

## 다른 PC의 시작 오류 확인

미배포 진단 변경은 시작 검사에 실패하면 종료 코드 또는 45초 시간 초과를 표시하고 `%LOCALAPPDATA%\MorningBloomLauncher\startup-check.log`에 실행 단계·Python 예외·네이티브 오류 출력을 보관합니다. 로그는 설치 임시 폴더 정리 후에도 남으며 저장 데이터나 환경 변수 전체를 수집하지 않습니다. 기존 v0.4.0 배포본에는 이 진단 기능이 없습니다.

기존 `New game failed startup check` 메시지만으로는 다른 PC의 원인을 확정할 수 없습니다. Windows 스마트 앱 컨트롤이 EXE나 DLL을 차단한 경우 진단 코드만 재배포해도 차단이 해제되지는 않습니다. 앱별 예외 허용은 지원하지 않습니다. 배포 측 대응은 신뢰할 수 있는 인증서로 실행 파일과 DLL 등 모든 실행 코드를 서명하는 것입니다. [Microsoft FAQ](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions), [코드 서명 안내](https://learn.microsoft.com/en-us/windows/security/book/application-security-application-and-driver-control).

## 현재 배포 채널 제약

소스 저장소 `badbed7/morning-bloom`은 비공개입니다. 여기에 게시된 Release는 접근 권한이 있는 사람만 다운로드할 수 있습니다. 일반 사용자의 자동 업데이트 대상은 기본적으로 **공개 배포 전용 저장소 `badbed7/morning-bloom-releases`**입니다. 이 저장소와 배포 연결이 마련되기 전에는 자동 업데이트 조회가 실패하고 포함된 게임을 실행합니다. 이 상태를 공개 자동 업데이트 완료로 간주하면 안 됩니다.

소스 저장소 공개 전환이나 인증 토큰의 클라이언트 포함은 하지 않습니다.

## 공개 배포 연결 최초 1회

1. GitHub에서 `badbed7/morning-bloom-releases`를 Public으로 생성하고 README로 초기화합니다. 소스 파일은 넣지 않습니다.
2. 배포 저장소에만 Contents read/write 권한을 가진 fine-grained token을 발급합니다.
3. 비공개 소스 저장소 Settings → Secrets and variables → Actions에 `BLOOM_RELEASE_TOKEN` secret으로 등록합니다. 토큰을 채팅이나 코드에 붙여넣지 않습니다.
4. 다른 배포 저장소 이름이면 Actions variable `BLOOM_RELEASE_REPO`에 `소유자/저장소`를 등록합니다. 이 값은 런처 빌드에 고정되므로 이미 배포된 런처의 주소는 바뀌지 않습니다.
5. `release/VERSION`을 다음 버전으로 올려 main에 커밋합니다. 빌드·검증 후 소스 저장소 Release와 공개 배포 저장소 Release에 ZIP과 update.json이 게시됩니다.

첫 공개 배포는 공개 feed 주소가 정확한 배포본을 공유하세요. 이후 같은 주소로 새 버전을 게시하면 기존 런처가 받습니다.

## 빌드와 게시

`Windows release` 워크플로는 main의 `release/VERSION` 변경 또는 수동 실행으로 동작합니다. 일반 코드 커밋만으로는 새 버전을 배포하지 않습니다. 버전은 `0.3.0`처럼 숫자 세 자리입니다. 기존 Release를 덮어쓰지 않으며 재배포는 새 버전을 사용합니다. 실패로 남은 draft는 관리자가 확인 후 정리할 수 있습니다.

Windows x64 / Python 3.12에서 수동 빌드:

```powershell
python -m pip install -r python/requirements.txt -r release/requirements-build.txt
python release/build_windows.py
```

출력은 `release-output`입니다. GitHub Actions는 게임·업데이터 단위/통합 테스트, 패키징한 게임의 `--smoke-test`, 런처 `--self-test`를 통과해야 게시합니다. Actions artifact도 14일 보관합니다. 실행 점검은 임시 저장 폴더만 사용합니다.

## 검증 범위와 한계

업데이트 신뢰 기준은 고정 GitHub HTTPS 배포 주소와 SHA-256입니다. 해시는 전송 손상을 검사하며 독립된 제작자 서명은 아닙니다. 현재 실행 파일에는 Windows Authenticode 서명이 없습니다. 코드 서명 인증서와 별도 업데이트 서명 키 연결은 후속 배포 강화 작업입니다.

런처는 프로토콜 1을 지원하며 게임 파일을 자동 업데이트합니다. 런처 자체의 프로토콜 변경은 새 배포본 다운로드가 필요합니다. 새 버전 실행 점검은 모든 플레이 기능의 정상 동작을 보장하지 않습니다. 실제 Windows 바탕화면 배율·보안 경고·장시간 재배는 수동 검증 대상입니다.
