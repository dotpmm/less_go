FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

COPY requirements.txt .
RUN uv add --no-cache -r requirements.txt

COPY . .

CMD ["uv", "run", "main.py"]
