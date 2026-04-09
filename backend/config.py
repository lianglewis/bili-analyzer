"""配置管理 — 环境变量 + 默认值"""

import os

# 后端服务
HOST = "127.0.0.1"
PORT = int(os.getenv("BILI_PORT", "8765"))

# Claude API
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_API_URL = os.getenv("CLAUDE_API_URL", "https://api.anthropic.com/v1/messages")

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
