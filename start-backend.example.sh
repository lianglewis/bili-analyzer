#!/bin/bash
cd /Users/liangliwei/bili-analyzer
export CLAUDE_API_KEY=your-api-key-here
export CLAUDE_MODEL=claude-sonnet-4-5-20250929
export CLAUDE_API_URL=https://api.anthropic.com/v1/messages
exec venv/bin/python backend/app.py
