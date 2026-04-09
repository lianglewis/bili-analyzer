# Bili Analyzer

AI 分析 B 站视频，自动生成结构化笔记。

## 架构

```
Chrome Extension (Manifest V3)  ←→  Python Backend (FastAPI, localhost:8765)
```

## 快速开始

### 1. 启动后端

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 设置 Claude API Key
export CLAUDE_API_KEY="sk-ant-..."

# 启动
python app.py
```

后端启动后访问 http://127.0.0.1:8765/api/health 验证。

### 2. 安装 Chrome 扩展

1. 打开 `chrome://extensions/`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `extension/` 目录

### 3. 使用

1. 打开一个 B 站视频页面
2. 点击扩展图标
3. 选择转录方式（推荐先试「B站字幕」）
4. 点击「分析视频」
5. 等待分析完成，下载 Markdown 笔记

## 转录方式

| 方式 | 说明 | 要求 |
|------|------|------|
| B站字幕 | 使用 B 站自动/手动字幕 | 部分视频需要登录（在设置页填 SESSDATA） |
| Whisper 本地 | 用 OpenAI Whisper 本地转录 | `pip install openai-whisper`，需要 FFmpeg |
| 云端 ASR | 调用云端语音识别 | 开发中 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CLAUDE_API_KEY` | Claude API Key | 必填 |
| `CLAUDE_MODEL` | Claude 模型 | `claude-sonnet-4-20250514` |
| `BILI_PORT` | 后端端口 | `8765` |
| `WHISPER_MODEL` | Whisper 模型大小 | `base` |

## 系统依赖

- Python 3.9+
- FFmpeg（教程类视频截图需要）：`brew install ffmpeg`
- yt-dlp（Whisper 模式下载音频需要）：`pip install yt-dlp`
