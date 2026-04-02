# 03. 문서 업로드와 OCR 흐름

## 목표

- 문서 업로드부터 OCR 작업 생성, 추출 약 저장, 재시도까지 어떤 순서로 돌아가는지 이해합니다.
- `Document`, `OcrJob`, `OcrRawText`, `ExtractedMed`가 어떻게 연결되는지 익힙니다.

## 메모

### 파일

- `app/apis/v1/document_routers.py`
- `app/services/documents.py`
- `app/services/ocr.py`
- `app/models/documents.py`

### 무엇을 하는가

- `document_router`는 문서 업로드, 목록 조회, 파일 조회, OCR 상태 조회, OCR 원문 조회, 추출 약 조회/수정, OCR 재시도, 바코드 디코드, MFDS 검색의 입구입니다.
- 실제 문서 관리와 환자 접근 검증은 `DocumentService`가 맡고, OCR 처리 본체는 `OcrService`가 맡습니다.
- 데이터 모델은 `Document`, `OcrJob`, `OcrRawText`, `ExtractedMed`가 핵심입니다.

### 어떻게 동작하는가

- 문서를 업로드하면 `DocumentService.upload_document()`가 파일을 저장하고 `Document`와 `OcrJob`를 함께 생성합니다.
- 업로드 직후 `asyncio.create_task()`로 `OcrService.process_ocr_job()`가 비동기 실행됩니다.
- OCR 처리 중 바코드 인식과 OCR 텍스트 추출을 시도하고, 원문은 `OcrRawText`, 추출 약 정보는 `ExtractedMed`에 저장합니다.
- 성공하면 job 상태가 `success`, 실패하면 `failed`와 에러 정보가 남습니다.
- 이후 사용자는 상태 조회, 원문 조회, 추출 약 수정, OCR 재시도 같은 API를 다시 호출합니다.

### 문제점

- `document_router`가 담당하는 범위가 넓습니다.
- `DocumentService`가 파일 저장, 권한 검증, 문서 관리, 약 수정/확정, 바코드 디코드까지 함께 맡고 있습니다.
- `OcrService`도 OCR 후처리, 정규식 파싱, 알림 발송까지 많은 책임이 한곳에 몰려 있습니다.
- OCR 실행 트리거가 worker 큐가 아니라 `asyncio.create_task()` 기반입니다.

### 개선 방향

- 업로드, OCR 실행, 추출 결과 검증, 환자 복약 데이터 반영 단계를 더 분리할 수 있는지 봅니다.
- `DocumentService`와 `OcrService`의 책임 경계를 먼저 문서화한 뒤, 리팩터링 후보를 정리합니다.
- `Document -> OcrJob -> OcrRawText / ExtractedMed` 흐름을 기준 구조로 문서화합니다.

### 회고 한 줄

- 당시에는 문서를 올리면 바로 결과가 보이는 흐름을 빠르게 만드는 데 집중했지만, 지금 다시 보니 업로드와 OCR, 검증, 확정 반영 로직이 한 덩어리처럼 엮여 있어 설명과 분리가 어렵습니다.

### 한마디로 정리하면

- 문서 관련 요청 입구는 `document_router`이고, 실제 업로드/조회/수정 흐름은 `DocumentService`, OCR 처리 본체는 `OcrService`가 맡고 있습니다.

### 내가 지금 이해한 흐름

1. 사용자가 문서를 업로드하면 `document_router`가 `DocumentService.upload_document()`를 호출합니다.
2. `DocumentService`는 대상 환자 접근 권한을 확인하고, 파일 확장자와 크기를 검사한 뒤 파일을 저장합니다.
3. 문서 레코드 `Document`와 OCR 작업 레코드 `OcrJob`를 함께 만듭니다.
4. 업로드 직후 `asyncio.create_task()`로 `OcrService.process_ocr_job()`를 비동기로 실행합니다.
5. `OcrService`는 OCR job 상태를 `processing`으로 바꾸고, 바코드 인식과 OCR 텍스트 추출을 시도합니다.
6. 추출한 원문은 `OcrRawText`에 저장하고, 파싱한 약 정보는 `ExtractedMed`에 저장합니다.
7. 성공하면 job 상태가 `success`로 바뀌고, 실패하면 `failed`, `error_code`, `error_message`가 남습니다.
8. 사용자는 상태 조회, 원문 조회, 추출 약 조회, 약 수정/확정, OCR 재시도 요청을 다시 API로 호출합니다.

### 데이터 모델 관계를 내가 이해한 방식

- `Document`
  - 업로드한 실제 문서 메타데이터입니다.
  - 어떤 환자 문서인지, 누가 올렸는지, 파일 URL이 무엇인지 들고 있습니다.

- `OcrJob`
  - 한 문서에 대해 OCR을 몇 번 돌렸는지 남기는 작업 기록입니다.
  - 상태, 재시도 횟수, 에러 코드를 들고 있습니다.

- `OcrRawText`
  - 특정 OCR job의 원문 텍스트 결과입니다.
  - `OcrJob`와 사실상 1:1 관계입니다.

- `ExtractedMed`
  - OCR 원문에서 뽑아낸 약 정보 조각입니다.
  - 한 OCR job에서 여러 개가 나올 수 있습니다.

### 같이 봐야 하는 함수

- `DocumentService.upload_document()`
- `DocumentService.get_document_ocr_status()`
- `DocumentService.get_document_drugs()`
- `DocumentService.patch_document_drugs()`
- `OcrService.process_ocr_job()`
- `OcrService.retry_document_ocr()`

### 아직 헷갈리는 점

- OCR이 외부 OCR API를 어떻게 호출하는지, `_build_combined_raw_text()` 내부 세부 로직은 더 읽어봐야 합니다.
- `patch_document_drugs()` 이후 `PatientMed`, `MedSchedule`로 어떻게 확정 반영되는지 아직 끝까지 보지 못했습니다.
- 업로드 직후 `asyncio.create_task()`를 쓰는 방식이 운영상 얼마나 안정적인지는 더 생각해봐야 합니다.

### 지금 바로 보이는 문제

- `document_router`가 담당하는 기능 범위가 넓습니다. 업로드, 목록, 파일 조회, OCR 상태, OCR 재시도, 바코드 디코드, MFDS 검색까지 모두 모여 있습니다.
- `DocumentService`도 파일 저장, 권한 체크, 문서 관리, 약 수정/확정, 바코드 디코드, 가이드용 데이터 조합까지 너무 많은 책임을 같이 들고 있습니다.
- `OcrService`는 정규식, OCR 후처리, 바코드 인식, 알림 발송까지 한 클래스에 몰려 있습니다.
- OCR 실행 트리거가 worker 큐가 아니라 `asyncio.create_task()` 기반이라 앱 프로세스 수명에 더 의존하는 구조처럼 보입니다.

### 나중에 다시 확인할 포인트

- `Document -> OcrJob -> OcrRawText/ExtractedMed` 흐름을 다이어그램으로 정리하기
- OCR 실패 코드 종류와 재시도 정책 정리하기
- MFDS 검증이 정확히 어느 단계에서 붙는지 확인하기
- 약 수정 확정 이후 `PatientMed`와 스케줄 생성으로 이어지는 흐름 확인하기

### 지금 시점 회고 메모

- 당시에는 문서를 올리면 바로 결과가 보이는 흐름을 빨리 만드는 것이 우선이었을 것 같습니다.
- 지금 다시 보니 "업로드", "OCR 실행", "추출 결과 검증", "환자 복약 데이터 반영"이 한 서비스 층에 많이 모여 있어 설명도 어렵고 분리 포인트도 필요해 보입니다.
