"""处理流水线 — 缓存命中秒开，否则并行调用 Claude"""

import asyncio
import uuid

from typing import Dict, List, Optional

from models import (
    AnalysisResult,
    AnalyzeRequest,
    TaskStatus,
    TextSegment,
    VideoCategory,
)

_tasks: Dict[str, TaskStatus] = {}

# 转录缓存：bvid → segments，用于术语追问时提供上下文
_transcripts: Dict[str, List[TextSegment]] = {}


def get_task(task_id: str) -> Optional[TaskStatus]:
    return _tasks.get(task_id)


def get_transcript(bvid: str) -> Optional[List[TextSegment]]:
    return _transcripts.get(bvid)


async def run_pipeline(req: AnalyzeRequest) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = TaskStatus(task_id=task_id)
    asyncio.create_task(_process(task_id, req))
    return task_id


def _update(task: TaskStatus, status: str, progress: int, message: str):
    task.status = status
    task.progress = progress
    task.message = message


def _extract_bvid(url: str) -> str:
    import re
    m = re.search(r"(BV[\w]+)", url)
    if not m:
        raise ValueError(f"无法从 URL 提取 BV 号: {url}")
    return m.group(1)


def _build_result(title, url, bvid, full=None, title_hook="",
                   title_explanation="", cover_url=""):
    """构建 AnalysisResult，full 是 analyze_full 的返回 dict"""
    from note import generate_markdown

    result = AnalysisResult(
        video_title=title,
        video_url=url,
        bvid=bvid,
        cover_url=cover_url or None,
        category=full["category"] if full else VideoCategory.KNOWLEDGE,
        summary=full["summary"] if full else "",
        title_hook=title_hook,
        title_explanation=title_explanation,
        practical_values=full.get("practical_values") if full else None,
        concept_flow=full.get("concept_flow", []) if full else [],
        term_groups=full.get("term_groups") if full else None,
        qa_sections=full.get("qa_sections") if full else None,
    )
    result.markdown = generate_markdown(result)
    return result


async def _process(task_id: str, req: AnalyzeRequest):
    task = _tasks[task_id]
    title = ""
    cover_url = ""

    try:
        bvid = _extract_bvid(req.url)

        # ── 缓存命中 → 秒开 ──
        if not req.force:
            from db import get_note
            cached = get_note(bvid)
            if cached:
                task.result = AnalysisResult(**cached)
                _update(task, "done", 100, "分析完成（缓存）")
                return

        # ── Step 0: 视频标题 + 封面 ──
        _update(task, "transcribing", 5, "获取视频信息...")
        from transcript import get_video_info
        info = await get_video_info(bvid)
        title = info["title"]
        cover_url = info["pic"]

        # ── Step 1: 转录 ──
        _update(task, "transcribing", 10, "获取转录文本...")
        from transcript import get_transcript
        segments = await get_transcript(req, bvid)
        _transcripts[bvid] = segments
        _update(task, "transcribing", 20,
                f"转录完成，共 {len(segments)} 条字幕")

        # ── Step 2: 并行 — 标题解读 + 完整分析 ──
        _update(task, "analyzing", 22, "AI 分析中...")
        from analyzer import explain_title, analyze_full

        title_task = asyncio.create_task(explain_title(segments, title))
        full_task = asyncio.create_task(analyze_full(segments, title))

        # 标题解读先完成（小 prompt），让用户早点看到内容
        try:
            title_info = await title_task
            title_hook = title_info.get("hook", "")
            title_explanation = title_info.get("answer", "")
        except Exception:
            title_hook = ""
            title_explanation = ""

        task.result = _build_result(
            title, req.url, bvid,
            title_hook=title_hook, title_explanation=title_explanation,
            cover_url=cover_url
        )
        _update(task, "analyzing", 30, "标题解读完成，深度分析中...")

        # 完整分析完成 — 包含分类+摘要+术语+脉络+QA
        full = await full_task
        task.result = _build_result(
            title, req.url, bvid, full,
            title_hook=title_hook, title_explanation=title_explanation,
            cover_url=cover_url
        )
        _update(task, "analyzing", 95, "生成最终笔记...")

        # ── Step 3: 持久化 ──
        from db import save_note
        try:
            save_note(task.result.model_dump())
        except Exception:
            pass  # 持久化失败不影响主流程

        _update(task, "done", 100, "分析完成")

    except Exception as e:
        import traceback
        traceback.print_exc()
        _update(task, "error", task.progress, f"错误: {e}")
