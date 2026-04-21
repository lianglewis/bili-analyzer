"""转录获取 — 三种方式统一为 list[TextSegment]"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional

import httpx

from models import AnalyzeRequest, TextSegment, TranscriptSource

BILIBILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}


async def get_transcript(
    req: AnalyzeRequest, bvid: str
) -> List[TextSegment]:
    # 无论用户选什么，先尝试 B站字幕API（快且稳定）
    try:
        segments = await _get_bilibili_subtitle(bvid, req.bilibili_sessdata)
        if segments:
            return segments
    except Exception:
        pass  # 没字幕就走用户选的方式

    if req.transcript_source == TranscriptSource.BILIBILI_API:
        # 用户明确选了 Bilibili API 但没字幕，给明确提示
        raise ValueError("该视频没有字幕。请尝试切换到 Whisper 本地转录。")
    elif req.transcript_source == TranscriptSource.WHISPER_LOCAL:
        return await _get_whisper_local(req.url, bvid, req.bilibili_sessdata, req.whisper_model)
    raise ValueError(f"未知转录方式: {req.transcript_source}")


# ── 方式一：B 站字幕 API ──────────────────────────────

async def _get_bilibili_subtitle(
    bvid: str, sessdata: Optional[str] = None
) -> List[TextSegment]:
    """
    流程: bvid → cid → 字幕列表 → 下载字幕 JSON
    字幕 JSON body 格式: [{"from": 0.5, "to": 3.2, "content": "..."}]
    """
    cookies = {}
    if sessdata:
        cookies["SESSDATA"] = sessdata

    async with httpx.AsyncClient(
        headers=BILIBILI_HEADERS, cookies=cookies, follow_redirects=True
    ) as client:
        # 1. 获取 cid
        resp = await client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"获取视频信息失败: {data.get('message', '未知错误')}")
        cid = data["data"]["pages"][0]["cid"]

        # 2. 获取字幕列表
        resp = await client.get(
            "https://api.bilibili.com/x/player/wbi/v2",
            params={"bvid": bvid, "cid": cid},
        )
        resp.raise_for_status()
        subtitle_data = resp.json()
        subtitles = (
            subtitle_data.get("data", {})
            .get("subtitle", {})
            .get("subtitles", [])
        )

        if not subtitles:
            raise ValueError(
                "该视频没有字幕。请尝试切换到 Whisper 本地转录。"
            )

        # 优先选中文字幕
        subtitle = subtitles[0]
        for s in subtitles:
            if "zh" in s.get("lan", ""):
                subtitle = s
                break

        # 3. 下载字幕内容
        sub_url = subtitle["subtitle_url"]
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url

        resp = await client.get(sub_url)
        resp.raise_for_status()
        body = resp.json().get("body", [])

        if not body:
            raise ValueError("字幕内容为空")

        return [
            TextSegment(start=item["from"], end=item["to"], text=item["content"])
            for item in body
        ]


# ── 方式二：本地 Whisper ──────────────────────────────

async def _get_whisper_local(
    url: str,
    bvid: str,
    sessdata: Optional[str] = None,
    whisper_model: Optional[str] = None,
) -> List[TextSegment]:
    import config

    # 0. 检测 yt-dlp 是否可用
    if not shutil.which("yt-dlp"):
        raise RuntimeError(
            "yt-dlp 未安装。请运行: brew install yt-dlp"
        )

    audio_path = f"{config.OUTPUT_DIR}/{bvid}.m4a"
    cookie_file = None

    try:
        # 1. 构建 yt-dlp 命令
        cmd = [
            "yt-dlp",
            "-f", "bestaudio",
            "-o", audio_path,
            "--no-playlist",
            "--no-overwrites",
            "--no-check-certificates",
            url,
        ]

        # SESSDATA → Netscape cookies 文件给 yt-dlp
        if sessdata:
            cookie_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            )
            cookie_file.write(
                "# Netscape HTTP Cookie File\n"
                f".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\t{sessdata}\n"
            )
            cookie_file.close()
            cmd[1:1] = ["--cookies", cookie_file.name]

        # 异步执行 yt-dlp，不阻塞事件循环
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp 下载音频失败: {proc.stderr[:500]}")

        # 2. Whisper 转录
        try:
            import whisper
        except ImportError:
            raise RuntimeError(
                "Whisper 未安装。请运行: pip3 install openai-whisper"
            )

        model_name = whisper_model or config.WHISPER_MODEL
        model = await asyncio.to_thread(whisper.load_model, model_name)
        result = await asyncio.to_thread(
            model.transcribe, audio_path, language="zh"
        )

        return [
            TextSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
            )
            for seg in result["segments"]
            if seg["text"].strip()
        ]
    finally:
        # 清理临时 cookie 文件
        if cookie_file and os.path.exists(cookie_file.name):
            os.remove(cookie_file.name)
        # 清理下载的音频文件
        if os.path.exists(audio_path):
            os.remove(audio_path)


# ── 视频信息 ──────────────────────────────────────────


async def get_video_info(bvid: str) -> dict:
    """获取视频标题和封面，返回 {"title": str, "pic": str}"""
    async with httpx.AsyncClient(headers=BILIBILI_HEADERS) as client:
        resp = await client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            return {"title": "", "pic": ""}
        d = data["data"]
        return {"title": d.get("title", ""), "pic": d.get("pic", "")}


async def get_video_title(bvid: str) -> str:
    """获取视频标题（向后兼容 wrapper）"""
    info = await get_video_info(bvid)
    return info["title"]


# ── 工具函数 ──────────────────────────────────────────

def format_transcript(segments: List[TextSegment]) -> str:
    """把 segments 格式化为 [MM:SS | Ns] text 格式，给 Claude 看。
    同时提供人类可读时间和精确秒数，避免 LLM 做 MM:SS→秒 的心算。
    """
    lines = []
    for seg in segments:
        t = seg.start
        mm, ss = divmod(int(t), 60)
        lines.append(f"[{mm:02d}:{ss:02d} | {t:.1f}s] {seg.text}")
    return "\n".join(lines)
