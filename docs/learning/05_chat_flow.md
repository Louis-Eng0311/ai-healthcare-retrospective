# 05. 챗봇 흐름

## 목표

- 채팅 세션 생성부터 메시지 응답 완료까지의 실행 경로를 설명할 수 있어야 합니다.
- `chat_router`, `ChatService`, `ai_worker` 간 책임을 구분합니다.

## 메모

### 파일

- `app/apis/v1/chat_routers.py`
- `app/services/chat/__init__.py`
- `app/services/chat_legacy.py`
- `app/services/chat/*`
- `ai_worker/main.py`
- `app/models/chat.py`
- `app/services/rag.py`

### 무엇을 하는가

- `chat_router`는 세션 생성, 메시지 전송, 메시지 조회, 피드백 수집 API의 입구입니다.
- `ChatService`는 `chat` 패키지 모듈과 `chat_legacy.py`를 통해 요청자 권한, 세션/메시지 저장, 응답 생성 규칙, worker 큐 연동을 담당합니다.
- `ai_worker`는 `generate_chat_reply` 작업을 소비해 비동기 응답 생성을 수행합니다.

### 어떻게 동작하는가

1. 사용자가 `/api/v1/chat/sessions`로 세션을 생성합니다.
2. 사용자가 `/messages`로 메시지를 보내면 라우터가 세션 접근 권한을 먼저 확인합니다.
3. `ChatService.create_message()`가 사용자 메시지를 저장합니다.
4. 요청 의도에 따라 동기 응답 또는 worker 큐 비동기 응답으로 분기됩니다.
5. 비동기일 경우 `chat_tasks` 큐에 작업이 등록되고, `ai_worker`가 응답을 생성합니다.
6. 사용자는 `/messages` 조회 API로 응답 상태를 확인합니다.
7. 응답 후 `/feedback`으로 사용자 피드백(도움됨/유형/코멘트)을 저장합니다.

### 문제점

- 라우터 내 환자/세션 접근 권한 검사 로직이 큽니다.
- 챗봇 의도 분기/키워드 규칙이 서비스 파일 하나에 많이 모여 있습니다.
- 피드백 수집은 존재하지만 품질 개선 루프로 자동 연결되는 구조는 약합니다.

### 개선 방향

- 환자 접근 권한 검사 로직은 공통 정책 계층을 유지하고, 세션 접근 검사 구조를 더 단순화할 수 있는지 검토합니다.
- `ChatService`에서 의도 분기 규칙, 응답 조합, persistence 책임 분리를 이어서 진행합니다.
- 피드백 데이터 활용 경로(집계/분석/개선 반영)를 문서화합니다.

### 회고 한 줄

- 당시에는 챗 기능의 사용성 확보를 우선해 빠르게 연결했지만, 지금 다시 보니 권한 정책과 응답 규칙이 한 서비스에 몰려 있어 품질 개선 지점을 분리해 추적하기 어렵습니다.

### 한마디로 정리하면

- 채팅 API는 `chat_router`가 받고, 실제 응답 구성은 `ChatService`, 무거운 비동기 응답은 `ai_worker`가 처리하는 구조입니다.

### 내가 지금 이해한 흐름

1. 세션 생성
2. 사용자 메시지 저장
3. 응답 생성(동기/비동기 분기)
4. 메시지 목록 조회
5. 피드백 저장

### 같이 봐야 하는 함수

- `_assert_can_access_session()` in `chat_routers.py`
- `ChatService.create_session()`
- `ChatService.create_message()`
- `ChatService.generate_assistant_reply()`

### 아직 헷갈리는 점

- 동기 응답과 비동기 응답 분기 조건의 경계가 명확한지 추가 확인이 필요합니다.
- 응답 실패 시 재시도와 사용자 노출 정책을 더 파봐야 합니다.

### 지금 보이는 문제

- 권한 검사 중복
- 서비스 비대화
- 피드백 활용 루프 미완성

### 나중에 다시 볼 포인트

- 피드백 지표 정의(도움됨 비율, 재질문율 등)
- 응답 지연/실패율 계측 포인트
- `guide` 흐름과 챗 컨텍스트 조합의 중복 여부
