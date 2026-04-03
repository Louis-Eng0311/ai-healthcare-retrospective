# 04. 가이드 생성 흐름

## 목표

- 가이드 생성 요청이 들어온 뒤 어떤 검증을 거쳐 worker 작업으로 넘어가는지 이해합니다.
- `GuideService`, `generate_guide.py`, `rag.py`가 각각 어떤 역할을 맡는지 구분합니다.

## 메모

### 파일

- `app/apis/v1/guide_routers.py`
- `app/services/guide.py`
- `ai_worker/tasks/generate_guide.py`
- `app/services/rag.py`

### 무엇을 하는가

- `guide_router`는 가이드 생성, 목록 조회, 상세 조회, 재생성 요청의 입구입니다.
- `GuideService`는 문서 준비 상태 확인, 확정 약 존재 여부 확인, 가이드 레코드 생성, worker 큐 등록, 조회용 컨텍스트 조합을 맡습니다.
- `generate_guide.py`는 실제 AI 호출과 결과 저장을 담당합니다.
- `rag.py`는 가이드, 프로필, 일정, 약물, 외부 근거를 블록 단위로 묶어 컨텍스트로 만드는 보조 역할을 합니다.

### 어떻게 동작하는가

- 사용자가 가이드 생성을 요청하면 `guide_router.generate_guide()`가 먼저 문서 접근 권한을 확인합니다.
- 이후 `GuideService.create_guide_generation()`이 문서 존재 여부, OCR 완료 여부, 확정 약 존재 여부를 확인합니다.
- 조건이 맞으면 `Guide` 레코드를 `GENERATING` 상태로 만들고 Redis 큐에 생성 작업을 넣습니다.
- AI worker는 큐에서 이 작업을 받아 `generate_guide.py`를 실행합니다.
- worker는 `GuideService.build_generation_context()`로 환자 프로필, 확정 약, 일정, MFDS/KIDS 근거, RAG 컨텍스트를 모읍니다.
- 그다음 프롬프트를 만들고 OpenAI를 호출한 뒤, 결과를 검증하고 `Guide` 레코드에 저장합니다.
- 목록 조회와 상세 조회는 이미 생성된 `Guide` 레코드를 읽어 반환합니다.
- 재생성도 결국 기존 가이드를 확인한 뒤 새 버전의 `Guide`를 다시 만들고 큐에 넣는 흐름입니다.

### 초기 문제점

- `guide_router`에 환자/문서 접근 권한 검사 로직이 꽤 많이 들어 있습니다.
- `GuideService`가 검증, 조회, 버전 관리, 큐 등록, 컨텍스트 조합까지 같이 맡고 있어 범위가 넓습니다.
- 실제 AI 호출은 worker에 있지만, 컨텍스트 조합 규칙과 근거 생성 규칙이 여러 파일에 나뉘어 있어 처음 보면 흐름이 끊깁니다.
- 가이드 생성 성공/실패를 어떤 수치로 평가할지 지금 코드만으로는 보이지 않습니다.

### 개선 방향

- 접근 권한 검사 로직을 라우터 밖 공통 정책 계층으로 뺄 수 있는지 검토합니다.
- `GuideService` 안에서 "생성 요청 처리"와 "생성 컨텍스트 조합" 책임을 분리할 수 있는지 봅니다.
- RAG 근거가 어떤 순서로 섞이는지 문서화해서 AI 응답 근거 설명력을 높입니다.
- 생성 시간, 실패율, 재생성 비율 같은 품질 지표를 나중에 남길 수 있게 측정 포인트를 잡아둡니다.

### 현재 반영 상태

- 환자 접근 권한 검사는 `access_policy` 공통 계층 호출로 정리했습니다.
- 생성 시간/실패율/재생성 비율 같은 정량 지표 수집은 아직 미완료입니다.
- `GuideService` 내부 책임 분리는 아직 추가 작업이 필요합니다.

### 회고 한 줄

- 당시에는 문서와 약 정보가 준비되면 바로 가이드를 생성해주는 흐름을 빠르게 연결했지만, 지금 다시 보니 권한 검사와 생성 조건, AI 컨텍스트 조합이 여러 층에 흩어져 있어 전체 흐름을 설명하려면 먼저 구조를 정리해야 합니다.

### 한마디로 정리하면

- 가이드 기능은 "API에서 요청을 받고 -> GuideService가 조건을 검사하고 큐에 넣고 -> worker가 AI 호출로 실제 내용을 채우는 구조"입니다.

### 내가 지금 이해한 흐름

1. 사용자가 가이드 생성을 요청합니다.
2. 라우터가 요청자의 문서/환자 접근 권한을 먼저 확인합니다.
3. `GuideService`가 OCR 완료 여부와 확정 약 존재 여부를 검사합니다.
4. 조건이 맞으면 `Guide` 레코드를 `GENERATING` 상태로 만들고 Redis 큐에 작업을 넣습니다.
5. AI worker가 큐를 읽고 가이드 생성 작업을 실행합니다.
6. worker가 프로필, 약물, 일정, 외부 근거를 모아 프롬프트를 만듭니다.
7. OpenAI 응답을 검증한 뒤 `Guide` 본문과 요약을 저장합니다.

### 같이 봐야 하는 함수

- `guide_router.generate_guide()`
- `GuideService.create_guide_generation()`
- `GuideService.build_generation_context()`
- `GuideService._assert_document_ready()`
- `build_rag_context()`
- `generate_guide()` in `ai_worker/tasks/generate_guide.py`

### 아직 헷갈리는 점

- `generate_guide.py`에서 응답 검증과 저장이 어떤 세부 단계로 끝나는지 더 읽어봐야 합니다.
- `GuideService._enqueue_generate_task()` 구현과 실제 큐 메시지 형식도 더 확인이 필요합니다.
- 실패한 가이드 생성이 사용자에게 어떻게 보이는지, 재생성 UX는 어떤지 더 봐야 합니다.

### 지금 바로 보이는 문제

- 권한 검사 로직이 라우터 안에 길게 들어 있습니다.
- 컨텍스트 조합 규칙이 `guide.py`, `generate_guide.py`, `rag.py`에 분산돼 있습니다.
- 품질 기준은 보이는데 품질 측정 기준은 아직 문서로 남아 있지 않습니다.

### 나중에 다시 확인할 포인트

- 가이드 생성 평균 시간 측정하기
- 실패 코드와 재생성 비율 정리하기
- 어떤 근거 블록이 실제 프롬프트에 가장 많이 들어가는지 보기
- 채팅 흐름과 가이드 흐름의 컨텍스트 조합이 얼마나 겹치는지 비교하기
