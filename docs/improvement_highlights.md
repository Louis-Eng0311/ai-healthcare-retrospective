# 개선 결과와 트러블슈팅 기록

## 범위

- 기준 브랜치: `develop`
- 통합 브랜치: `develop` 대비 개인 개선 브랜치
- 확인 명령어:
`git diff --name-status develop...HEAD`

현재 기준으로 `app/` 하위 변경 파일은 41개입니다.

## 진행 기준

보완 가능한 항목 전체를 한 번에 구현하기보다, 우선순위가 높은 영역부터 단계적으로 반영했습니다.  
또한 팀 프로젝트 기반 코드의 특성상, 기존에 작성된 코드를 정확히 이해하고 학습하는 과정을 먼저 수행한 뒤 개선 작업을 진행했습니다.

## 1) 인증 보안

### 문제

- refresh 쿠키 정책이 환경별로 명확히 드러나지 않았습니다.
- 토큰 재발급 엔드포인트가 `GET` 중심이라 의미가 약했습니다.
- 인증 민감 엔드포인트 과다 호출 방어가 부족했습니다.

### 선택

- 쿠키 정책은 `SameSite`를 우선 명시했습니다.
  - 운영: `None`
  - 비운영: `Lax`
- 재발급은 `POST /token/refresh`를 추가하고 기존 `GET`은 호환 유지.
- rate limiting은 전역이 아니라 인증 민감 구간부터 적용.

### 왜 이 선택을 했는가

- `SameSite`는 인증 쿠키 오남용 방어와 직접 연결되어 우선순위가 높습니다.
- 재발급은 상태 변경 성격이 강해 `POST`가 의도를 더 잘 전달합니다.
- 전역 제한보다 인증 구간 선적용이 부작용을 줄이고 효과를 빨리 확인할 수 있습니다.

### 코드 근거

- `app/apis/v1/auth_routers.py`
- `app/dependencies/rate_limit.py`
- `app/core/config.py`

### 수치와 검증

- 재발급 메서드 수: 2개 (`POST`, `GET`)
- rate limit 적용 엔드포인트 수: 5개
  - login, admin login, token refresh GET/POST, reset-password
- 인증 응답 캐시 제어 헤더 적용:
  - `Cache-Control: no-store`
  - `Pragma: no-cache`

## 2) 권한 검사 공통화

### 문제

- 라우터별 환자 접근 검사 코드가 분산되어 정책 변경 시 누락 위험이 있었습니다.

### 선택

- 권한 판정을 공통 서비스로 모아 라우터는 호출만 하도록 정리.

### 왜 이 선택을 했는가

- 보안 정책은 분산 구현보다 단일 지점 관리가 회귀 위험이 낮습니다.

### 코드 근거

- `app/services/access_policy.py`
- `app/apis/v1/chat_routers.py`
- `app/apis/v1/guide_routers.py`

### 수치와 검증

- `chat_routers.py`, `guide_routers.py`에서 `_assert_can_access_patient` 중복 정의 제거 확인
- 두 라우터 모두 `assert_can_access_patient` 공통 호출 사용

## 3) OCR 검수 기준 강화

### 문제

- 후보 매칭과 표준코드 누락이 같은 수준으로 보여 검수 우선순위가 모호했습니다.

### 선택

- 검수 사유를 케이스별로 분리.
  - `표준코드 확정이 필요한 후보 매칭`
  - `표준코드 누락`

### 왜 이 선택을 했는가

- 의료 데이터는 추출 성공보다 검증 가능성이 중요해서, 검수 사유가 구체적이어야 운영 판단이 가능합니다.

### 코드 근거

- `app/services/documents.py`
- `app/tests/user_apis/test_document_validation_logic.py`

### 수치와 검증

- 검수 규칙 테스트 파일 1개 신규 추가
- 케이스별 사유 문자열이 고정되어 회귀 시 테스트로 즉시 확인 가능

## 4) 알림 처리 성능 개선

### 문제

- 복약 알림 생성 루프에서 사용자 설정 조회/중복 알림 확인이 반복 쿼리로 수행되었습니다.

### 선택

- 사용자 설정과 기존 reminder key를 배치 조회 후 메모리 set 판정으로 변경.

### 왜 이 선택을 했는가

- 대상자가 늘어날 때 반복 조회 구조는 쿼리 증가 폭이 큽니다.
- 배치 조회 + set 판정은 구현 대비 효과가 큰 안정적인 최적화 방식입니다.

### 코드 근거

- `app/services/medication_notifications.py`
- `app/tests/user_apis/test_medication_notification_utils.py`

### 수치와 검증

- 루프 내부 `get_or_none`, `exists()` 직접 호출 제거
- 보조 유틸 테스트 1개 파일 신규 추가

## 5) 챗 서비스 구조 분해

### 문제

- 기존 `chat.py` 단일 파일이 너무 커서 책임 경계가 흐리고 수정 영향 범위 파악이 어려웠습니다.

### 선택

- 단일 파일을 역할별 모듈로 분해하고, 기존 파일은 `chat_legacy.py`로 이관.

### 왜 이 선택을 했는가

- 기능 추가보다 유지보수 가능성을 먼저 확보해야 이후 품질 개선이 가능합니다.

### 코드 근거

- 삭제: `app/services/chat.py`
- 추가: `app/services/chat/*.py` (모듈 분해)
- 추가: `app/services/chat_legacy.py`
- 추가: `app/tests/user_apis/test_chat_quality_contract.py`

### 수치와 검증

- 기존 단일 파일 크기: 6424줄
- 분해 후 모듈 합계: 4912줄 (`app/services/chat/*.py`)
- 분해 모듈 수: 27개
- 챗 계약 테스트 파일 1개 신규 추가

## 실행 환경 트러블슈팅

### 1. Docker 컨테이너 이름 충돌

- 증상:
`/app-worker is already in use`
- 원인:
기존 컨테이너가 살아있는 상태에서 동일 이름으로 재생성 시도
- 처리:
기존 컨테이너 정리 후 재기동

### 2. MySQL 포트 충돌

- 증상:
`0.0.0.0:3306 bind: address already in use`
- 원인:
호스트 3306 사용 중
- 처리:
기존 점유 프로세스/컨테이너 확인 후 포트 정리 또는 포트 변경

### 3. Git index.lock 충돌

- 증상:
`Unable to create .git/index.lock`
- 원인:
동시 git 작업 또는 이전 작업 잔여 락
- 처리:
동시 작업 중단 후 순차 실행으로 전환

## 미완료 항목

- `docker-compose.yml`의 `app-worker` 고정 `container_name` 정리
- OCR 실행 트리거를 queue 기반으로 전환
- 알림 queue/worker의 하드코딩 설정 제거
- `print` 중심 로그를 구조화 로깅으로 전환
- 인증 라우터의 API/HTML 책임 분리

## 최종 검증 체크리스트

1. 변경 파일 확인
`git diff --name-status develop...HEAD`
2. 커밋 이력 확인
`git log --oneline --decorate -n 20`
3. 챗 모듈 문법 확인
`python3 -m py_compile app/services/chat_legacy.py $(find app/services/chat -type f -name '*.py')`
4. 핵심 테스트 존재 확인
- `app/tests/user_apis/test_chat_quality_contract.py`
- `app/tests/user_apis/test_document_validation_logic.py`
- `app/tests/user_apis/test_medication_notification_utils.py`
