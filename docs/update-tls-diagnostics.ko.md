# 업데이트 인증서 오류 수정과 검증

적용 버전: v0.8.14. v0.8.13에는 이 SSL 수정이 포함되지 않습니다. 새 런처가 포함된 전체 v0.8.14 ZIP을 사용합니다.

## 확인된 증상

`Installed before: 0.8.12 / Latest verified: unavailable / Selected: 0.8.12`와 함께 GitHub API·대체 공개 주소 모두 `CERTIFICATE_VERIFY_FAILED: unable to get issuer certificate`가 기록됐습니다. 같은 코드를 쓰는 v0.8.13 ZIP을 새로 받으면 동봉된 v0.8.13은 설치되지만 최신 조회는 같은 이유로 실패할 수 있습니다.

확정된 것은 인증서 체인 검증 실패입니다. 사용자의 어떤 인증서가 누락됐는지, 보안 프로그램·프록시의 HTTPS 검사 영향인지는 이 로그만으로 확정하지 않습니다.

## 변경

- Windows에서 업데이트용 HTTPS 컨텍스트를 `truststore==0.10.5`의 CryptoAPI 기반 인증서 체인 검증으로 바꿉니다. Windows 신뢰 저장소와 중간 인증서 조회를 사용합니다. 시스템이 신뢰하지 않는 인증서는 계속 거부합니다.
- GitHub API, 고정·대체 업데이트 JSON, ZIP 다운로드에 같은 검증 컨텍스트를 사용합니다. HTTPS와 호스트 이름 검증, 다운로드 크기·SHA-256 검사를 유지합니다. SSL 전역 패치나 인증서 검증 해제는 하지 않습니다.
- EXE에는 네이티브 백엔드를 포함하고, BAT에는 truststore 패키지와 라이선스를 동봉합니다. BAT 런처의 인증서 처리를 게임용 pip 설치에 의존시키지 않습니다.
- `update.log`에 TLS 백엔드와 인증서 검증 코드·설명을 기록하며 경고에서 인증서 문제를 안내합니다.
- v0.8.14 전체 ZIP으로 런처를 한 번 교체해야 합니다. 게임 payload 자동 업데이트는 런처 자체를 바꾸지 않습니다. 저장 폴더는 삭제하지 않습니다.

## 읽기 전용 진단

EXE 폴더에서 다음 명령을 실행합니다. 게임 설치나 저장 변경 없이 EXE·BAT의 공개 업데이트 정보를 검사합니다.

```bat
MorningBloom.exe --diagnose-updates --diagnostic-log "%TEMP%\MorningBloom-update-check.log"
notepad "%TEMP%\MorningBloom-update-check.log"
```

BAT 배포본은 다음과 같습니다.

```bat
py -3.12 release\launcher.py --diagnose-updates --diagnostic-log "%TEMP%\MorningBloom-update-check.log"
```

`--download-test`를 추가하면 임시 폴더로 두 ZIP도 받아 크기·SHA-256을 확인하고 삭제합니다. 게임과 저장에는 적용하지 않습니다.

## 자동 검증

`.github/workflows/launcher-tls.yml`에서 Windows Python 3.12로 다음을 실행합니다.

1. 임시 루트·중간·서버 인증서와 localhost 서버를 만듭니다. 시스템 인증서 저장소를 편집하지 않습니다.
2. 서버가 중간 인증서를 보내지 않는 상황에서 기존 OpenSSL 방식의 발급기관 오류를 재현합니다.
3. Windows 네이티브 방식으로 인증서의 AIA 주소에서 중간 인증서를 조회하고 체인을 검증하는지 확인합니다. 테스트 루트는 해당 컨텍스트에만 명시적으로 제공합니다.
4. 정상 체인은 허용하고 신뢰하지 않는 루트·다른 호스트 이름·만료 인증서는 거부하는지 확인합니다.
5. 실제 windowed PyInstaller EXE와 격리 모드(`-I`)로 실행한 BAT 구성 모두에서 같은 검사를 반복합니다.
6. 두 배포 구성에서 실제 공개 업데이트 JSON과 ZIP을 받아 크기·SHA-256을 검증합니다. 공개 릴리즈는 만들지 않습니다.

통과 결과는 PR CI에서 확인합니다. 이 검사는 사용자의 PC·네트워크를 복제하지 않으므로 특정 PC에서의 최종 성공은 새 런처 로그로 확인해야 합니다.
