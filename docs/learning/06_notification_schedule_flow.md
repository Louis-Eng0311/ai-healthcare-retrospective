# 06. 알림/스케줄 흐름

## 목표

- 알림 생성, 큐잉, worker 처리, 사용자 읽음 처리까지 end-to-end로 설명할 수 있어야 합니다.
- 수동 리마인드와 자동 스케줄 알림의 차이를 구분합니다.

## 메모

### 파일

- `app/apis/v1/notification_routers.py`
- `app/services/notifications.py`
- `app/services/queue_service.py`
- `app/services/medication_notifications.py`
- `app/services/hospital_schedule_notifications.py`
- `app_worker/main.py`

### 무엇을 하는가

- `notification_router`는 목록/읽음/삭제/설정/수동 리마인드 API 입구입니다.
- `NotificationService`는 권한 검증과 DB 저장을 담당합니다.
- `queue_service`는 Redis `notification_queue`에 job을 넣습니다.
- `app_worker`는 큐를 소비해 `sent_at`을 기록하고, 주기적으로 자동 알림을 생성합니다.

### 어떻게 동작하는가

1. 수동 리마인드: 보호자가 `/notifications/remind` 호출
2. 서비스에서 권한 검증 후 `Notification` 레코드 생성
3. `enqueue_send_notification()`으로 큐에 `SEND_NOTIFICATION` job push
4. `app_worker`가 큐를 소비해 해당 notification의 `sent_at` 업데이트
5. 별도 루프에서 복약/병원 일정 기반 자동 알림 생성
6. 사용자는 목록 조회, 읽음 처리, 삭제, 설정 수정을 API로 수행

### 초기 문제점

- `notification_routers.py`와 `notifications.py`에 팀 작업 과정의 임시/설명성 주석이 많아 유지보수 가독성이 떨어집니다.
- `queue_service.py`의 Redis host/port, queue name이 하드코딩되어 환경 유연성이 낮습니다.
- `app_worker` 로깅은 `print` 중심이라 운영 관측성이 약합니다.

### 개선 방향

- 알림 도메인 문서와 코드 주석을 제품 관점으로 정리합니다.
- 큐 관련 설정을 환경 변수 기반으로 일원화합니다.
- worker 로깅/에러 처리/메트릭 포인트를 구조화합니다.

### 현재 반영 상태

- 복약 알림 중복 판정/설정 조회는 배치 조회 방식으로 개선했습니다.
- queue/worker 하드코딩과 `print` 중심 로깅은 아직 미완료입니다.
- 운영 관측성 개선(구조화 로그, 메트릭)은 다음 단계 과제로 남아 있습니다.

### 회고 한 줄

- 알림 기능은 사용자 기능 관점에서 구현됐지만, 지금 다시 보니 큐 처리와 운영 관측성까지 고려한 운영 설계로 보강할 여지가 큽니다.

### 한마디로 정리하면

- 알림은 API에서 생성되고 Redis 큐를 거쳐 app worker가 발송 완료를 반영하는 이벤트 기반 흐름입니다.

### 내가 지금 이해한 흐름

1. 알림 생성(수동/자동)
2. 큐 job 등록
3. worker 소비 및 `sent_at` 반영
4. 사용자 읽음/삭제/설정

### 같이 봐야 하는 함수

- `NotificationService.send_manual_remind()`
- `enqueue_send_notification()`
- `dispatch_due_medication_notifications()`
- `dispatch_due_hospital_schedule_notifications()`
- `handle_job()` in `app_worker/main.py`

### 아직 헷갈리는 점

- 실제 푸시 채널(FCM/APNs 등) 연동은 현재 어디까지 구현되었는지 추가 확인이 필요합니다.

### 지금 보이는 문제

- 하드코딩 설정
- 운영성 로그 부족
- 문서/코드 표현 혼재

### 나중에 다시 볼 포인트

- 능동형 인터랙션 확장(주간 리포트/선제 질문)
- 알림 실패 재처리 전략
- 알림 중복 방지 키 정책 테스트
