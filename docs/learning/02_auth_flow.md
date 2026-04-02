# 02. 인증 흐름

## 목표

- 로그인, 회원가입, 소셜 로그인, 토큰 재발급이 어떤 흐름으로 동작하는지 이해합니다.
- 인증 정책과 페이지 반환 책임이 어떻게 섞여 있는지 봅니다.

## 메모

### 파일

- `app/apis/v1/auth_routers.py`
- `app/services/auth.py`
- `app/dependencies/security.py`

### 무엇을 하는가

- `auth_router`는 로그인, 회원가입, 관리자 인증, 소셜 로그인, 토큰 재발급, 이메일 찾기, 비밀번호 재설정의 입구입니다.
- 실제 계정 생성과 역할 검증은 `AuthService`가 맡고, 보호된 요청의 사용자 확인은 `get_request_user()`가 맡습니다.

### 어떻게 동작하는가

- 로그인 요청이 오면 `AuthService.authenticate()`가 이메일과 비밀번호를 확인합니다.
- 로그인 가능하면 `AuthService.login()`이 access token과 refresh token을 발급합니다.
- access token은 응답 바디로 내려가고, refresh token은 HttpOnly 쿠키로 저장됩니다.
- 소셜 로그인도 결국 사용자 조회 또는 생성 이후 같은 JWT 발급 흐름으로 합쳐집니다.
- 보호된 요청에서는 `get_request_user()`가 bearer access token을 검증하고 사용자 엔티티를 조회합니다.

### 문제점

- 인증 API, 관리자 인증, 소셜 로그인, 계정 복구, HTML 페이지 반환이 한 라우터에 함께 들어 있습니다.
- 인증 정책과 UI 진입 책임이 한 파일에 섞여 있습니다.
- refresh cookie 설정에 `SameSite`가 없습니다.

### 개선 방향

- 인증 API와 HTML 페이지 반환 책임을 나누는 방향을 검토합니다.
- refresh cookie 정책을 명시적으로 정리합니다.
- 역할 검증과 인증 정책을 문서로 먼저 정리한 뒤, 공통화할 수 있는 부분을 봅니다.

### 회고 한 줄

- 당시에는 인증 관련 기능을 빠르게 한곳에 모았지만, 지금 다시 보니 인증 정책과 UI 진입 책임이 함께 있어 구조 설명과 보안 점검이 쉽지 않습니다.

### 한마디로 정리하면

- 로그인과 회원가입의 입구는 `auth_router`이고, 실제 계정 생성과 역할 확인은 `AuthService`, 보호된 요청의 사용자 판별은 `get_request_user()`가 담당합니다.

### 내가 지금 이해한 흐름

1. 사용자가 로그인 요청을 보냅니다.
2. 라우터가 `AuthService.authenticate()`로 이메일/비밀번호를 확인합니다.
3. 로그인 가능하면 `AuthService.login()`이 access/refresh 토큰을 발급합니다.
4. access token은 응답 바디로 내려가고, refresh token은 쿠키로 저장됩니다.
5. 이후 보호된 API에서는 `get_request_user()`가 access token으로 사용자를 조회합니다.
6. 소셜 로그인도 결국 사용자 조회/생성 후 같은 JWT 발급 흐름으로 연결됩니다.

### 같이 봐야 하는 함수

- `AuthService.signup()`
- `AuthService.authenticate()`
- `AuthService.login()`
- `get_request_user()`

### 아직 헷갈리는 점

- 왜 access token은 바디로 내리고 refresh token만 쿠키로 저장했는지 의도 정리가 필요합니다.
- 관리자 로그인과 일반 로그인의 차이가 "선택 가능한 역할" 외에 더 있는지 확인이 필요합니다.
- 소셜 로그인 콜백의 `accept` 헤더 분기가 프론트와 어떻게 연결되는지 더 봐야 합니다.

### 지금 바로 보이는 문제

- API 라우터인데 HTML 페이지 반환까지 담당합니다.
- 인증 관련 기능이 너무 많이 한 파일에 모여 있습니다.
- refresh cookie 설정에 `SameSite`가 없습니다.

### 나중에 다시 확인할 포인트

- refresh cookie 보안 속성
- 역할 검증 공통화 가능성
- 소셜 로그인 흐름과 일반 로그인 흐름의 공통화 여부
