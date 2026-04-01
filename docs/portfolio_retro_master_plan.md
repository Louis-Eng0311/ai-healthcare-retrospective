# AI Healthcare Retrospective Master Plan

## 목적

이 저장소는 팀 프로젝트 결과물을 그대로 복제한 저장소가 아니라, 아래 목표를 가진 개인 회고/개선 프로젝트로 운영한다.

- 팀 프로젝트 코드를 실제로 다시 읽고 이해한다.
- 멘토 및 참여기업 피드백을 코드와 구조에 연결한다.
- 보안, OCR 검증, AI 상호작용, 품질 관리 측면에서 개선한다.
- 개선 과정을 브랜치와 문서 단위로 남겨 포트폴리오와 노션에 재사용한다.

핵심 포지셔닝 문장:

> 부트캠프 팀 프로젝트로 구현한 AI 헬스케어 서비스를, 멘토 및 참여기업 피드백을 바탕으로 구조, 보안, 데이터 검증, AI 상호작용 측면에서 재검토하고 개선한 개인 확장 프로젝트

## 현재 코드베이스 요약

### 서비스 구성

- FastAPI API 서버: [app/main.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/main.py)
- AI worker: [ai_worker/main.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/ai_worker/main.py)
- 알림/스케줄 worker: [app_worker/main.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app_worker/main.py)
- React 프론트엔드: [frontend/src/App.jsx](/Users/louis/Louis_workplace/ai-healthcare-retrospective/frontend/src/App.jsx)
- Docker 실행 구성: [docker-compose.yml](/Users/louis/Louis_workplace/ai-healthcare-retrospective/docker-compose.yml)
- 품질 설정: [pyproject.toml](/Users/louis/Louis_workplace/ai-healthcare-retrospective/pyproject.toml), [.github/workflows/checks.yml](/Users/louis/Louis_workplace/ai-healthcare-retrospective/.github/workflows/checks.yml)

### 주요 도메인

- 인증/인가: [app/apis/v1/auth_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/auth_routers.py), [app/services/auth.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/auth.py)
- 문서/OCR/약물 처리: [app/apis/v1/document_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/document_routers.py), [app/services/documents.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/documents.py), [app/services/ocr.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/ocr.py), [app/services/mfds.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/mfds.py)
- 가이드 생성: [app/apis/v1/guide_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/guide_routers.py), [app/services/guide.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/guide.py)
- 챗봇: [app/apis/v1/chat_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/chat_routers.py), [app/services/chat.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/chat.py)
- 알림: [app/services/notifications.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/notifications.py)

### 이미 확인한 구조적 특징

- 기능 범위는 넓다.
- 서비스별 역할은 분리되어 보이지만 공통 정책과 책임 경계는 약하다.
- 라우터 단의 권한 검사가 중복되어 있다.
- 서비스 클래스가 비대하다.
- 프론트엔드 루트 파일이 크다.
- CI는 lint 위주로만 실제 동작 중이고 테스트 자동화는 덜 연결되어 있다.
- 문서 사이트는 비어 있다.

## 멘토 및 참여기업 피드백 연결

### 멘토 피드백

강점

- 요구사항 정의와 문서화가 세밀함
- 상호작용 및 중복 섭취 체크 로직이 실무적 가치가 있음
- Git/컨벤션 등 협업 프로세스가 성숙함

아쉬운 점

- 사용자 피드백이 모델 개선 구조로 이어지지 않음
- 보안 설계 미완성
- AI 모델 품질의 정량 평가 부재
- 피드백 루프의 실제 활용 로직 부족

### 참여기업 피드백

강점

- 진료 기록 기반 복약 안내와 생활 습관 가이드를 통합한 기획 의도
- OCR과 맞춤형 가이드 챗봇을 결합해 실제 복약 오류를 줄이려는 방향성

개선 포인트

- OCR 추출 데이터의 정합성 강화 필요
- 식약처 표준 코드/API 기반 검증 보강 필요
- 다약제 상호작용 검증 강화 필요
- 능동형 인터랙션 강화 필요
- 복약 리포트/선제적 상호작용 기능 확장 여지 존재

## 가장 먼저 이해할 순서

이 프로젝트는 파일 순서가 아니라 사용자 흐름 순서로 이해해야 한다.

### 1단계. 실행 구조 이해

목표:

- 이 프로젝트가 어떤 프로세스들로 구성되는지 설명할 수 있어야 한다.

볼 파일:

- [docker-compose.yml](/Users/louis/Louis_workplace/ai-healthcare-retrospective/docker-compose.yml)
- [app/main.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/main.py)
- [ai_worker/main.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/ai_worker/main.py)
- [app_worker/main.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app_worker/main.py)
- [app/apis/v1/__init__.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/__init__.py)

기록할 내용:

- 어떤 컨테이너가 뜨는지
- 요청이 어디로 들어오는지
- 어떤 백그라운드 작업이 존재하는지
- DB, Redis, Nginx, Frontend의 역할

### 2단계. 사용자 흐름 이해

목표:

- 사용자 입장에서 요청이 어떤 라우터와 서비스로 이어지는지 파악한다.

우선순위 흐름:

1. 회원가입/로그인
2. 환자 정보 접근
3. 문서 업로드
4. OCR 결과 조회
5. 약물 정보 확인
6. 가이드 생성
7. 챗봇 대화
8. 알림/스케줄 확인

### 3단계. 공통 구조 이해

목표:

- `apis`, `dtos`, `services`, `models`, `repositories`, `dependencies`가 각각 무슨 역할인지 설명할 수 있어야 한다.

### 4단계. 개선 포인트 수집

목표:

- 아직 수정하지 말고, 코드에서 반복/비대화/정책 부재 지점을 찾는다.

확인 기준:

- 중복 코드
- 파일 비대화
- 예외 처리 일관성
- 보안 정책 누락
- 테스트 부재
- 문서화 부족

## 현재 기준 핵심 문제 목록

### 저장소/운영

- 루트에 중복 복사된 `AI_Health_final/` 폴더가 존재함
- [docker-compose.yml](/Users/louis/Louis_workplace/ai-healthcare-retrospective/docker-compose.yml) 의 `app-worker`는 `container_name: app-worker`를 고정해 이름 충돌을 유발함
- 문서 사이트가 [docs/index.md](/Users/louis/Louis_workplace/ai-healthcare-retrospective/docs/index.md) 기준으로 거의 비어 있음

### 보안/인가

- [app/apis/v1/auth_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/auth_routers.py) 의 refresh cookie 설정에 `SameSite` 지정이 없음
- [app/apis/v1/chat_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/chat_routers.py) 와 [app/apis/v1/guide_routers.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/apis/v1/guide_routers.py) 에 권한 검사 로직이 중복됨
- rate limiting, 민감 로그 관리, 암호화 정책은 추가 검토가 필요함

### 데이터/OCR

- [app/services/ocr.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/ocr.py) 는 정규식, 후처리, OCR 재시도, 추출 로직이 한 서비스에 많이 몰려 있음
- OCR 추출값의 표준 검증 흐름을 더 명확히 설명할 수 있어야 함
- MFDS 검증은 존재하지만, “정합성 보장 체계”로 포장되기엔 설명과 구조가 더 필요함

### AI/피드백

- [app/services/guide.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/guide.py) 와 [app/services/chat.py](/Users/louis/Louis_workplace/ai-healthcare-retrospective/app/services/chat.py) 는 도메인 규칙과 AI 입력 조합 로직이 크고 복잡함
- 피드백 수집이 실제 품질 향상 루프로 이어지는 구조는 약함
- AI 품질을 정량 평가하는 기준 문서가 없음

### 프론트엔드

- [frontend/src/App.jsx](/Users/louis/Louis_workplace/ai-healthcare-retrospective/frontend/src/App.jsx) 에 상태/유틸/흐름이 많이 몰려 있음
- 화면 수는 많지만 공통 상태 구조를 설명하기 어려움

### 품질 관리

- [.github/workflows/checks.yml](/Users/louis/Louis_workplace/ai-healthcare-retrospective/.github/workflows/checks.yml) 에서 테스트 잡이 주석 처리되어 있음
- 테스트는 존재하지만 CI에 강하게 연결되어 있지 않음

## 추천 브랜치 순서

### 1. feature/repo-cleanup

목표:

- 저장소 정체성과 문서 구조 정리

작업:

- 중복된 `AI_Health_final/` 폴더 정리
- README 개편 시작
- 회고 문서 뼈대 생성
- Docker 설정에서 고정 이름 사용 여부 검토

회고 문장:

> 팀 프로젝트 결과물을 개인 개선 프로젝트로 전환하기 위해 저장소 목적, 문서 구조, 로컬 실행 구성을 먼저 정리했다.

### 2. feature/architecture-notes

목표:

- 구조를 읽으면서 문서화

작업:

- 시스템 구성도 정리
- 사용자 흐름 정리
- API 서버, AI worker, app worker 역할 문서화

회고 문장:

> 역할 분담형 프로젝트는 기능 구현과 전체 아키텍처 이해가 분리되기 쉬워, 먼저 전체 데이터 흐름과 실행 구조를 재구성했다.

### 3. feature/security-hardening

목표:

- 인증/인가 정책과 기본 보안 강화

작업:

- refresh cookie 정책 점검 및 `SameSite` 보완
- 권한 검사 공통화 설계
- 민감정보 로그 점검
- 최소 rate limiting 또는 방어 전략 설계

회고 문장:

> 기존 프로젝트는 인증 자체는 구현됐지만, 헬스케어 서비스에 요구되는 보안 정책을 시스템 수준으로 정리하는 단계까지는 가지 못했다.

### 4. feature/document-ocr-review

목표:

- OCR 추출과 약물 검증 흐름 이해 및 보강

작업:

- OCR 파싱 흐름 문서화
- 추출 결과 검증 규칙 분리
- MFDS 표준 데이터 검증 흐름 명확화
- 실패/재시도/수정 UX 검토

회고 문장:

> OCR은 동작했지만, 의료 데이터의 특성상 추출 성공보다 정합성과 검증 가능성이 더 중요하다는 점을 기준으로 흐름을 다시 정리했다.

### 5. feature/guide-chat-quality

목표:

- AI 가이드/챗봇 품질 구조 재점검

작업:

- 프롬프트 입력 컨텍스트 정리
- 응답 실패 처리와 재시도 구조 점검
- 피드백 저장과 활용 가능성 분석
- 정량 평가 기준 초안 작성

회고 문장:

> AI 기능은 연결되어 있었지만, 품질을 어떻게 측정하고 피드백을 어떻게 개선으로 연결할지에 대한 설계는 추가 보완이 필요했다.

### 6. feature/proactive-care-features

목표:

- 능동형 상호작용 기능 확장

작업:

- 알림 기반 선제적 안내 검토
- 주간 복약 리포트 설계 또는 구현
- 보호자용 요약 시나리오 정리

회고 문장:

> 초기 서비스가 요청-응답형 상호작용에 머물렀다면, 이후에는 복약 순응도를 높이는 능동형 인터랙션 방향으로 확장 가능성을 검토했다.

### 7. feature/frontend-structure-review

목표:

- 프론트 구조 재정리

작업:

- `App.jsx` 비대화 완화
- 공통 상태와 API 호출 로직 분리
- 주요 사용자 플로우별 화면 책임 분리

회고 문장:

> 빠른 구현을 위해 한 파일에 집중된 프론트 로직을 사용자 흐름 단위로 재정리해 유지보수성을 높였다.

### 8. feature/ci-docs-hardening

목표:

- 품질 기준과 문서 마무리

작업:

- 테스트/린트/포맷 기준 정리
- CI 재정비
- README, 회고, 개선 로그 마무리

회고 문장:

> 개인 프로젝트로 다시 정리하면서, 기능 구현뿐 아니라 검증 가능한 품질 기준과 문서화의 중요성을 함께 반영했다.

## 실제 작업 순서

### 오늘 바로 할 일

1. `feature/repo-cleanup` 브랜치 생성
2. `AI_Health_final/` 중복 폴더 정리
3. README 개편 초안 작성
4. `docs/architecture.md`, `docs/retrospective.md`, `docs/improvement-log.md` 뼈대 생성

### 그다음 할 일

1. `feature/architecture-notes` 에서 구조 문서화
2. `feature/security-hardening` 에서 최소 보안 보강
3. `feature/document-ocr-review` 에서 OCR/MFDS 정합성 정리

## 노션 구성 권장안

### 페이지 1. 프로젝트 소개

- 프로젝트 한 줄 소개
- 왜 다시 회고/개선하게 되었는지
- 멘토/참여기업 피드백 요약

### 페이지 2. 구조 이해 노트

- 시스템 구성도
- 사용자 흐름
- 핵심 파일과 역할
- 아직 이해 안 된 부분

### 페이지 3. 브랜치별 개선 로그

각 브랜치마다 아래 형식 반복:

- 문제 상황
- 코드 근거
- 수정 내용
- 배운 점

### 페이지 4. 기술 개선 상세

- 보안
- OCR 검증
- AI 품질
- 프론트 구조
- CI/문서화

### 페이지 5. 최종 회고

- 팀 프로젝트 당시 한계
- 개인 프로젝트로 다시 보며 달라진 점
- 이후 확장 계획

## 각 브랜치에서 남길 md 파일

- `docs/architecture.md`
- `docs/retrospective.md`
- `docs/improvement-log.md`
- 필요시 `docs/security-review.md`
- 필요시 `docs/ocr-validation-review.md`
- 필요시 `docs/ai-quality-review.md`

## 진행 원칙

- 처음부터 큰 리팩터링을 하지 않는다.
- 읽고, 문서화하고, 작은 수정부터 한다.
- 기능보다 이해와 설명 가능성을 먼저 확보한다.
- “내가 원래 담당한 파트”처럼 쓰지 않고 “개인적으로 전체 구조를 다시 검토하며 보완했다”로 정리한다.

