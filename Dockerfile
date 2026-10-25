FROM python:3.12-slim
WORKDIR /app
COPY smoke_test.py ./
COPY vibespec ./vibespec
RUN useradd -m app && mkdir -p /app/.cache && chown app /app/.cache
USER app
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "vibespec"]
