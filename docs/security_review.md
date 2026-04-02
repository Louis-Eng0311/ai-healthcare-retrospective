# 보안 점검 기록

## 목적

이 문서는 팀 프로젝트 코드를 다시 읽으면서, 보안 관점에서 확인한 상태와 실제로 적용한 보완을 근거 중심으로 정리한 기록입니다.

## 범위

- 인증/인가 정책
- 쿠키/JWT 처리
- 접근 제어 중복 구조
- 민감정보/로그 노출 가능성
- API 방어 전략(rate limiting 등)

## 회고: 현재 구조에서 확인한 점

### 1) 인증/JWT

확인 파일:

- `app/apis/v1/auth_routers.py`
- `app/services/auth.py`
- `app/services/jwt.py`
- `app/dependencies/security.py`

상태:

- access token + refresh token 구조 사용
- refresh token은 HttpOnly 쿠키 저장
- role 기반 로그인 검증 존재

회고 관점에서 확인한 한계:

- 인증 정책과 UI 진입(HTML 반환) 책임 분리 필요
- 토큰 재발급 엔드포인트 메서드 일관성 정리 필요
- 인증 응답의 캐시 방지 헤더 명시 필요

### 2) 인가(Authorization)

확인 파일:

- `app/apis/v1/chat_routers.py`
- `app/apis/v1/guide_routers.py`
- `app/services/patient_profile_access.py`

상태:

- 환자/세션 접근 권한 검사를 라우터에서 직접 수행
- 보호자/환자/관리자 role 분기 로직 존재

회고 관점에서 확인한 한계:

- 유사한 권한 검사 로직이 라우터마다 반복됨
- 공통 접근 정책 계층으로 이동 필요

### 3) 알림/큐 및 운영 로그

확인 파일:

- `app/services/queue_service.py`
- `app_worker/main.py`

상태:

- 큐 처리 흐름은 동작
- worker에서 처리 결과를 DB에 반영

회고 관점에서 확인한 한계:

- 큐/Redis 설정 일부 하드코딩
- `print` 기반 로그를 구조화 로깅으로 전환 필요

### 4) API 방어

확인 파일:

- 전체 API 라우터 및 서비스

상태:

- 입력 검증은 DTO 수준에서 일부 적용

회고 관점에서 확인한 한계:

- 전역 rate limiting 부재
- 민감 엔드포인트(로그인/토큰/파일업로드) 보호 전략 보강 필요

## 이번 단계에서 적용한 개선

### refresh cookie SameSite 정책 명시

변경 파일:

- `app/apis/v1/auth_routers.py`

변경 내용:

- `_cookie_samesite()` helper 추가
- `set_cookie()`에 `samesite` 속성 명시
- 환경별 정책:
  - `prod`: `none`
  - 그 외: `lax`

의도:

- 보안 속성 누락을 명시적으로 제거
- 소셜 로그인 콜백 환경까지 고려한 정책으로 정리

선택 이유 / 대안 비교:

- `SameSite`는 교차 사이트 요청에서 쿠키 전송 제어를 담당하므로 인증 쿠키 보안의 핵심 축입니다.
- `Domain`은 전송 범위 제어 옵션이며 중요하지만, 이번 단계에서는 교차 사이트 전송 위험 완화가 우선순위였습니다.
- 대안 비교:
  - `Strict`: 가장 엄격, 외부 유입/소셜 로그인 플로우 제약 가능
  - `Lax`: 일반 웹 플로우에서 보안/호환 균형
  - `None`: 교차 사이트 허용, `Secure` 필수

검증 기준:

- 코드상 환경 분기: `prod` / `non-prod`
- 쿠키 속성 명시 여부: `samesite` 적용 확인

### 토큰 재발급 엔드포인트 정리

변경 파일:

- `app/apis/v1/auth_routers.py`
- `app/tests/auth_apis/test_token_api.py`

변경 내용:

- `POST /api/v1/auth/token/refresh` 엔드포인트 추가
- 기존 `GET /api/v1/auth/token/refresh`는 하위 호환용으로 유지
- GET/POST 모두에 대한 테스트 케이스 추가

의도:

- 토큰 재발급의 목적(상태 변경 성격)을 반영한 메서드 정합성 확보
- 기존 클라이언트 호환성 유지

검증 기준:

- GET/POST 동시 지원
- 테스트 파일에서 GET/POST 성공/실패 케이스 존재

### 인증 응답 캐시 방지 헤더 적용

변경 파일:

- `app/apis/v1/auth_routers.py`

변경 내용:

- 로그인/소셜 콜백/토큰 재발급/로그아웃 응답에 아래 헤더 적용
  - `Cache-Control: no-store`
  - `Pragma: no-cache`

의도:

- 인증 토큰 응답이 브라우저/프록시에 캐시되는 위험 완화

검증 기준:

- auth 응답에 `Cache-Control: no-store`, `Pragma: no-cache` 포함 여부

### 권한 검사 공통화

변경 파일:

- `app/services/access_policy.py`
- `app/apis/v1/chat_routers.py`
- `app/apis/v1/guide_routers.py`

변경 내용:

- 중복된 환자 접근 권한 검사 로직을 공통 모듈로 이동
- `assert_can_access_patient` / `resolve_requester_role`를 라우터 공용으로 사용

의도:

- 권한 정책 분산으로 인한 불일치 위험 완화
- 정책 변경 시 수정 지점 축소

검증 기준:

- 두 라우터에서 중복 함수 제거 여부
- 공통 함수 호출로 통일 여부

### 인증 민감 엔드포인트 Rate Limiting 적용

변경 파일:

- `app/dependencies/rate_limit.py`
- `app/apis/v1/auth_routers.py`
- `app/core/config.py`
- `app/tests/auth_apis/test_token_api.py`

변경 내용:

- 인증 라우트에 요청 제한 의존성을 추가
  - `POST /auth/login`
  - `POST /auth/admin/login`
  - `GET/POST /auth/token/refresh`
  - `POST /auth/reset-password`
- 설정값 기반으로 제한 임계치/윈도우를 조정 가능하게 구성
- refresh API에서 429 응답 동작 테스트 추가

의도:

- 인증 민감 엔드포인트에 대해 무차별 요청 1차 방어선 확보
- 환경별 운영 정책을 설정값으로 통제 가능하도록 정리

검증 기준:

- 임계치 초과 시 `429 Too Many Requests` 반환
- 테스트에서 `RATE_LIMIT_EXCEEDED` 코드 확인
- 설정값 변경으로 제한 정책 조정 가능

## 남은 과제 (우선순위)

1. 운영 로깅 정리

- worker `print` 로그를 구조화 logger로 교체
- 실패 코드/재시도 횟수 추적 포인트 추가
- 선택 기준:
- 장애 추적 시간을 줄일 수 있는 로그 필드(요청 키, 작업 ID, 상태) 포함
- 검증 기준:
- 오류 재현/원인 분석 소요 시간
- 재시도 실패율 집계 가능 여부

2. 보안 체크리스트 자동화

- CI에서 최소 보안 정적 점검 항목 검토
- 보안 회귀 항목 문서화
- 선택 기준:
- 배포 전 최소 기준을 강제할 수 있는 자동화 항목 우선
- 검증 기준:
- CI 체크 항목 수
- 보안 관련 PR 차단 건수

## 정리 기준

- 팀 프로젝트 당시에는 기능 완성에 집중했고, 이후 개인 회고 단계에서 보안 속성 누락/접근 정책 분산/과도 요청 방어 부재를 위험 관점으로 다시 점검했습니다.
- 단순 구현 여부보다 운영 환경에서의 보안 정책을 기준으로 문제를 식별했고, 확인된 항목부터 순차적으로 보완했습니다.
- 현재는 `SameSite`/인증 응답 캐시 방지/토큰 재발급 정합성/권한 공통화/rate limiting까지 1차 보완을 반영했습니다.
