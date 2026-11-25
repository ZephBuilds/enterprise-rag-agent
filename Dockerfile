FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY --chown=65532:65532 . .

USER 65532:65532

CMD ["sh", "-c", "python3 -m unittest discover -s tests -v && python3 -m compileall -q src tests && PYTHONPATH=src python3 -m enterprise_rag.cli verify"]
