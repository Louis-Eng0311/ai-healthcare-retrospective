# 01. 실행 구조 이해

## 목표

- 이 프로젝트가 어떤 프로세스로 구성되는지 설명할 수 있어야 합니다.
- 사용자의 요청이 어느 컨테이너로 들어오고, 어떤 worker가 백그라운드 작업을 처리하는지 이해합니다.

## 메모

### 한마디로 정리하면

- 이 프로젝트는 "API 서버 1개 + AI worker 1개 + 알림 worker 1개 + DB/Redis + 프론트 + Nginx" 구조입니다.

### 내가 지금 이해한 흐름

1. `mysql`과 `redis`가 먼저 올라옵니다.
2. `fastapi`가 DB와 Redis에 연결된 상태로 시작합니다.
3. `ai-worker`는 Redis 큐에서 가이드 생성, 채팅 응답 작업을 가져갑니다.
4. `app-worker`는 알림 큐를 읽고, 일정 기반 알림을 생성합니다.
5. 사용자는 주로 `nginx`를 통해 들어오고, 실제 API/HTML 응답은 FastAPI가 담당합니다.

### 같이 봐야 하는 파일

- `app/main.py`
- `ai_worker/main.py`
- `app_worker/main.py`
- `app/apis/v1/__init__.py`

### 아직 헷갈리는 점

- `frontend`가 실제로 어디까지 독립적으로 쓰이고, 어디부터 FastAPI 정적 서빙과 연결되는지 더 확인이 필요합니다.
- `nginx`가 프론트 개발 서버와 어떻게 공존하는지 아직 명확히 이해하지 못했습니다.

### 지금 바로 보이는 문제

- FastAPI가 API와 문서와 HTML 진입 경로를 함께 맡고 있습니다.
- worker가 각각 어떤 큐 메시지를 생산/소비하는지 아직 전체 그림이 완전하지 않습니다.

### 나중에 다시 확인할 포인트

- `app-worker`의 고정 container name
- `frontend`의 `npm install` 매번 수행 문제
- worker 큐 생산 지점이 어디인지
