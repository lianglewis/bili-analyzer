"""配置管理 — env var > config.json > 默认值"""

import json
import os

# ── 配置文件路径 ──
_CONFIG_DIR = os.path.expanduser("~/.bili-analyzer")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")


def _load_file() -> dict:
    """从 ~/.bili-analyzer/config.json 读取持久化配置"""
    try:
        with open(_CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_file(data: dict) -> None:
    """写入配置文件，权限 0o600"""
    os.makedirs(_CONFIG_DIR, mode=0o700, exist_ok=True)
    with open(_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(_CONFIG_FILE, 0o600)


def _resolve(env_key: str, file_key: str, default: str) -> str:
    """优先级：env var > config.json > 默认值"""
    env_val = os.getenv(env_key)
    if env_val:
        return env_val
    return _file_cfg.get(file_key, "") or default


# ── 启动时加载一次文件配置 ──
_file_cfg = _load_file()

# 后端服务
HOST = "127.0.0.1"
PORT = int(os.getenv("BILI_PORT", "8765"))

# Claude API
CLAUDE_API_KEY = _resolve("CLAUDE_API_KEY", "claude_api_key", "")
CLAUDE_MODEL = _resolve("CLAUDE_MODEL", "claude_model", "claude-sonnet-4-20250514")
CLAUDE_API_URL = _resolve("CLAUDE_API_URL", "claude_api_url", "https://api.anthropic.com/v1/messages")

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")


def get_all() -> dict:
    """返回当前生效的配置（API Key 脱敏）"""
    key = CLAUDE_API_KEY
    masked = (key[:8] + "..." + key[-4:]) if len(key) > 12 else "***"
    return {
        "claude_api_key": masked,
        "claude_model": CLAUDE_MODEL,
        "claude_api_url": CLAUDE_API_URL,
    }


def update(new_cfg: dict) -> None:
    """更新配置：内存 + 写入文件"""
    global CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_API_URL, _file_cfg

    file_data = _load_file()

    if "claude_api_key" in new_cfg and new_cfg["claude_api_key"]:
        CLAUDE_API_KEY = new_cfg["claude_api_key"]
        file_data["claude_api_key"] = new_cfg["claude_api_key"]

    if "claude_model" in new_cfg and new_cfg["claude_model"]:
        CLAUDE_MODEL = new_cfg["claude_model"]
        file_data["claude_model"] = new_cfg["claude_model"]

    if "claude_api_url" in new_cfg and new_cfg["claude_api_url"]:
        CLAUDE_API_URL = new_cfg["claude_api_url"]
        file_data["claude_api_url"] = new_cfg["claude_api_url"]

    _file_cfg = file_data
    _save_file(file_data)
