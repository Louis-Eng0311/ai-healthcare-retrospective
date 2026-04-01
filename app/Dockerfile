FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 1. uv 설치 (공식 이미지에서 복사해오는 가장 깔끔한 방법)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 2. 의존성 패키지 관리 파일을 컨테이너 내부에 복사합니다.
COPY pyproject.toml uv.lock mkdocs.yml ./

# 3. FastAPI + 문서 빌드용 의존성을 설치합니다.
RUN uv sync --group app --group docs --no-dev --frozen

# 4. 문서 소스를 복사하고 정적 사이트를 생성합니다.
COPY ./docs ./docs
RUN uv run --no-sync mkdocs build

# 5. 프롬프트와 로컬 소스 코드를 컨테이너 내부로 복사합니다.
COPY ./app_worker ./app_worker
COPY ./prompts ./prompts
COPY ./app ./app
