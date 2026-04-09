"""帧提取 — FFmpeg 截图 + GIF 生成"""

import os
import subprocess
from typing import List

import config
from models import InstructionStep


def _check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True
        )
    except FileNotFoundError:
        raise RuntimeError("FFmpeg 未安装。macOS: brew install ffmpeg")


def _download_video(url: str, bvid: str) -> str:
    """用 yt-dlp 下载视频（720p，截图够用）"""
    video_path = os.path.join(config.OUTPUT_DIR, f"{bvid}.mp4")
    if os.path.exists(video_path):
        return video_path

    proc = subprocess.run(
        [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "-o", video_path,
            "--no-playlist",
            "--merge-output-format", "mp4",
            url,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp 下载视频失败: {proc.stderr[:500]}")
    return video_path


def extract_frame(video_path: str, timestamp: float, output_path: str):
    """从视频中提取单帧截图"""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ],
        capture_output=True,
        check=True,
    )


def extract_gif(
    video_path: str, start: float, duration: float, output_path: str
):
    """FFmpeg 两步 palette 法生成高质量 GIF"""
    palette = output_path + ".palette.png"

    # Pass 1: 调色板
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", video_path,
            "-vf", "fps=10,scale=480:-1:flags=lanczos,palettegen",
            palette,
        ],
        capture_output=True,
        check=True,
    )

    # Pass 2: 生成 GIF
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", video_path,
            "-i", palette,
            "-lavfi", "fps=10,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse",
            output_path,
        ],
        capture_output=True,
        check=True,
    )

    # 清理临时调色板
    if os.path.exists(palette):
        os.remove(palette)


async def extract_frames_for_steps(
    url: str, bvid: str, steps: List[InstructionStep]
) -> List[InstructionStep]:
    """为需要配图的步骤提取截图和 GIF"""
    _check_ffmpeg()
    video_path = _download_video(url, bvid)

    for step in steps:
        if not step.needs_visual:
            continue

        t = step.timestamp

        # 截图
        frame_name = f"{bvid}_step{step.step_number}.jpg"
        frame_path = os.path.join(config.OUTPUT_DIR, frame_name)
        try:
            extract_frame(video_path, t, frame_path)
            step.frame_path = f"/api/output/{frame_name}"
        except subprocess.CalledProcessError:
            pass  # 截图失败不致命，继续

        # GIF: 从时间戳前1秒到后4秒，共5秒
        gif_name = f"{bvid}_step{step.step_number}.gif"
        gif_path = os.path.join(config.OUTPUT_DIR, gif_name)
        try:
            extract_gif(video_path, max(0, t - 1), 5.0, gif_path)
            step.gif_path = f"/api/output/{gif_name}"
        except subprocess.CalledProcessError:
            pass  # GIF 失败不致命

    return steps
