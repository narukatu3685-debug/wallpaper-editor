# syntax=docker/dockerfile:1
#
# Claude Code を --dangerously-skip-permissions で動かすためのサンドボックス。
# GUI（tkinter）と実際の壁紙適用（Windows API）はホスト専用のため含めない。
# ここでは Claude Code CLI の実行環境と、pytest によるユニットテスト実行環境のみを用意する。
FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /workspace

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements-dev.txt

COPY . .

CMD ["claude", "--dangerously-skip-permissions"]
