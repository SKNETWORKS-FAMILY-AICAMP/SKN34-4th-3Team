FROM python:3.13-slim

# 영수증 OCR: 기본 엔진 PP-OCRv5(paddle, OpenCV가 libgl1·libglib2.0-0·libgomp1을 쓴다)와
# paddle을 쓸 수 없을 때 대신 읽는 Tesseract + 한국어 학습 데이터.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor fonts-nanum ca-certificates curl \
       libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# hwp-cli renders HWPX templates to PDF. Pin and verify the release binary.
ARG TARGETARCH=amd64
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) hwp_arch=x86_64; hwp_sha=af288b2b9765bd698bff8a74ece19d0b9ff8873a9338a4f22e55fd76f6b2072a ;; \
      arm64) hwp_arch=aarch64; hwp_sha=27b9a4b6097eb99261f030d650d9c234772c0bc9f74779d2244e11811ad79c90 ;; \
      *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/STAIxBWLB/hwp-cli/releases/download/v0.19.1/hwp-v0.19.1-${hwp_arch}-unknown-linux-gnu.tar.gz" -o /tmp/hwp.tar.gz; \
    echo "${hwp_sha}  /tmp/hwp.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/hwp.tar.gz -C /usr/local/bin hwp; \
    chmod 755 /usr/local/bin/hwp; \
    rm /tmp/hwp.tar.gz

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Keep the container environment outside /app so the Compose bind mount does
# not hide it during local development.
ENV UV_PROJECT_ENVIRONMENT=/opt/llm-venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# PP-OCRv5 모델(검출 mobile · 한국어 인식 · 문서 방향 분류)을 이미지에 미리 받아 둔다.
# /root/.paddlex 는 Compose 의 /app 바인드 마운트 밖이라 가려지지 않는다.
# 모델 이름은 src/features/receipt_ocr.py 의 PADDLE_*_MODEL 과 같아야 한다.
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
RUN /opt/llm-venv/bin/python -c "from paddleocr import PaddleOCR; PaddleOCR(text_detection_model_name='PP-OCRv5_mobile_det', text_recognition_model_name='korean_PP-OCRv5_mobile_rec', use_doc_orientation_classify=True, use_doc_unwarping=False, use_textline_orientation=False)"

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8001

CMD ["uv", "run", "--frozen", "uvicorn", "src.serving.django_config.asgi:application", "--host", "0.0.0.0", "--port", "8001", "--lifespan", "off"]
