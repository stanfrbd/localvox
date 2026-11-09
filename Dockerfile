FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml requirements.lock LICENSE NOTICE.md README.md ./
RUN pip install --require-hashes -r requirements.lock
COPY localvox ./localvox
RUN pip install --no-deps . && useradd --uid 10001 --create-home localvox && mkdir -p /data/models && chown -R localvox:localvox /data
USER localvox
ENV LOCALVOX_MODEL_DIR=/data/models LOCALVOX_TEMP_DIR=/tmp/localvox LOCALVOX_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["localvox", "serve"]
