FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

COPY requirements.txt .
RUN uv pip install --no-cache -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["python", "main.py"]

