# Architecture Overview

이 문서는 이 프로젝트의 최종 아키텍처 요약본입니다.  
학습 과정에서 작성한 상세 탐색 메모는 `docs/learning/*.md`를 기준으로 관리합니다.

## 1) 프로젝트 한 줄 요약

- FastAPI 백엔드, Redis 큐 기반 worker, React 프론트엔드를 결합한 디지털 헬스케어 서비스입니다.
- 핵심 기능은 인증/권한, 문서 OCR, 약물 정보 검증, 가이드 생성, 챗봇, 복약/병원 일정 알림입니다.

## 2) 시스템 구성

### 런타임 컴포넌트

- `fastapi`: API 엔드포인트, 인증, 도메인 로직 진입점, 일부 HTML/정적 경로 서빙
- `ai_worker`: 가이드 생성 및 챗봇 비동기 응답 처리 (`ai_tasks`, `chat_tasks`)
- `app_worker`: 알림 큐 소비 및 일정 기반 자동 알림 생성 (`notification_queue`)
- `mysql`: 주 데이터 저장소
- `redis`: worker 큐 브로커
- `nginx`: 외부 진입 프록시
- `frontend`: 개발용 Vite 서버

### 구성 파일

- 실행 구성: `docker-compose.yml`
- API 진입점: `app/main.py`
- AI worker 진입점: `ai_worker/main.py`
- 알림 worker 진입점: `app_worker/main.py`

## 3) 요청/처리 흐름

### A. 인증/권한

1. `/api/v1/auth/*` 요청 진입
2. `AuthService`에서 사용자 검증/역할 검증/JWT 발급
3. 보호 API는 `get_request_user`로 access token 검증

핵심 파일:

- `app/apis/v1/auth_routers.py`
- `app/services/auth.py`
- `app/dependencies/security.py`

### B. 문서 업로드 -> OCR -> 약물 데이터

1. 문서 업로드 요청
2. `Document`, `OcrJob` 생성
3. OCR 처리 후 `OcrRawText`, `ExtractedMed` 저장
4. 추출 약 수정/확정 후 환자 복약 데이터와 연결

핵심 파일:

- `app/apis/v1/document_routers.py`
- `app/services/documents.py`
- `app/services/ocr.py`
- `app/models/documents.py`

### C. 가이드 생성

1. 생성 요청 시 환자/문서 접근 권한 확인
2. `GuideService`가 생성 가능 상태 검증 후 `Guide` 레코드 생성
3. worker 큐 등록
4. `ai_worker`가 컨텍스트 조합 후 AI 응답 생성/저장

핵심 파일:

- `app/apis/v1/guide_routers.py`
- `app/services/guide.py`
- `ai_worker/tasks/generate_guide.py`
- `app/services/rag.py`

### D. 챗봇

1. 세션 생성/메시지 요청 진입
2. 세션 접근 권한 확인
3. 응답 생성 (동기/비동기 분기)
4. 비동기는 `chat_tasks` 큐로 처리
5. 피드백 저장

핵심 파일:

- `app/apis/v1/chat_routers.py`
- `app/services/chat/__init__.py`
- `app/services/chat_legacy.py`
- `app/services/chat/*`
- `app/models/chat.py`

### E. 알림/복약/병원 일정

1. 수동 리마인드 또는 일정 기반 자동 알림 생성
2. `Notification` 저장 후 큐 job push
3. `app_worker`가 큐 소비 후 `sent_at` 반영
4. 사용자 읽음/삭제/설정 API 처리

핵심 파일:

- `app/apis/v1/notification_routers.py`
- `app/services/notifications.py`
- `app/services/queue_service.py`
- `app/services/medication_notifications.py`
- `app/services/hospital_schedule_notifications.py`

## 4) 모듈 맵

### API 레이어

- `app/apis/v1/*`

### 서비스 레이어

- 인증: `auth.py`, `jwt.py`, `social_auth.py`
- 문서/OCR: `documents.py`, `ocr.py`, `mfds.py`
- AI: `guide.py`, `chat_legacy.py`, `chat/*`, `rag.py`
- 알림/스케줄: `notifications.py`, `queue_service.py`, `medication_notifications.py`, `hospital_schedule_notifications.py`

### 워커 레이어

- `ai_worker/*`
- `app_worker/*`

### 데이터 레이어

- `app/models/*`

핵심 엔티티 관계:

- `Document -> OcrJob -> OcrRawText / ExtractedMed`
- `Guide` (문서/환자 기반 생성)
- `ChatSession -> ChatMessage -> ChatFeedback`
- `Notification`, `NotificationSettings`

## 5) 현재 구조의 리스크

1. 권한 검사 공통화는 진행했지만, 세션 단위 접근 검사(`_assert_can_access_session`)는 라우터에 남아 있음
2. 대형 서비스 파일(`documents.py`, `chat_legacy.py`, `ocr.py`)의 책임이 여전히 넓음
3. 알림 큐 관련 설정이 일부 하드코딩되어 환경 유연성이 낮음
4. 프론트엔드 상태/유틸이 `App.jsx`에 집중됨
5. CI에서 테스트 자동 검증이 약함 (lint 중심)

## 6) 개선 우선순위

1. 구조 정리
2. 보안/인가 정리
3. OCR/검증 정리
4. AI 품질/피드백 루프 정리
5. 프론트 구조 정리
6. 품질 게이트 정리

## 7) 상세 학습 문서 링크

- `docs/learning/01_execution_structure.md`
- `docs/learning/02_auth_flow.md`
- `docs/learning/03_document_ocr_flow.md`
- `docs/learning/04_guide_flow.md`
- `docs/learning/05_chat_flow.md`
- `docs/learning/06_notification_schedule_flow.md`

## 8) 회고 포인트 한 줄

- 팀 프로젝트 단계에서는 구현 완주가 우선이었고, 개인 프로젝트 단계에서는 구조 설명 가능성, 보안, 데이터 검증, 운영성 기준으로 재정비했습니다.
