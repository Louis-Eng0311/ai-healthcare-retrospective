# AI Healthcare Retrospective

이 저장소는 디지털 헬스케어 팀 프로젝트 코드를 다시 점검하고, 운영 관점에서 필요한 개선을 반영한 결과를 정리한 프로젝트입니다.

## 프로젝트 범위

- 인증/인가 정책 강화
- OCR 결과 검수 기준 명확화
- 가이드/챗/알림 흐름 재정리
- 알림 처리 성능 개선
- 코드와 문서의 설명 가능성 개선

## 진행 원칙

보안 측면에서 보완할 수 있는 항목은 더 많았지만, 모든 항목을 한 번에 구현하는 방식보다 우선순위를 정해 단계적으로 반영했습니다.  
이 프로젝트는 팀 프로젝트 코드에서 시작했기 때문에, 다른 팀원이 작성한 코드를 먼저 이해하고 학습하는 과정을 핵심으로 두고 개선을 진행했습니다.

## 주요 개선 결과

상세 내용은 [docs/improvement_highlights.md](docs/improvement_highlights.md)에 정리했습니다.

핵심 반영 항목:

1. refresh cookie `SameSite` 환경 분기 적용
2. `POST /api/v1/auth/token/refresh` 추가 및 기존 `GET` 호환 유지
3. `chat`, `guide` 접근 권한 검사 공통화
4. 인증 민감 엔드포인트 요청 제한 적용
5. OCR 검수 사유(후보 매칭/표준코드 누락) 분리
6. 복약 알림 생성 로직의 조회 쿼리 최적화
7. 챗봇 서비스 모듈 분해 및 계약 테스트 추가

## 미완료 항목

아래 항목은 확인했지만 이번 범위에서는 미완료로 남겨두었습니다.

- `docker-compose.yml`의 `app-worker` 고정 `container_name` 정리
- OCR 실행 트리거(`asyncio.create_task`)를 queue 기반으로 전환
- `queue_service.py`, `app_worker/main.py`의 하드코딩/`print` 로깅 구조화
- 인증 라우터의 API 책임과 HTML 반환 책임 분리

## 기술 스택

- Backend: FastAPI, Tortoise ORM
- Database/Queue: MySQL, Redis
- Worker: `ai_worker`, `app_worker`
- Frontend: React (Vite)
- Infra: Docker Compose, Nginx

## 빠른 실행

### 1. 환경 파일 준비

```bash
cp envs/example.local.env envs/.local.env
```

### 2. 서비스 실행

```bash
docker compose up --build -d
```

### 3. 접속 주소

- API 문서: `http://localhost/api/docs`
- 웹 앱: `http://localhost/auth-demo/app`

## 테스트

```bash
python3 -m pytest -q
```

환경에 따라 DB/Redis 및 테스트 의존 패키지 설정이 추가로 필요할 수 있습니다.

## 문서

- 아키텍처 요약: [docs/architecture.md](docs/architecture.md)
- 보안 점검 기록: [docs/security_review.md](docs/security_review.md)
- 개선 결과와 트러블슈팅: [docs/improvement_highlights.md](docs/improvement_highlights.md)
