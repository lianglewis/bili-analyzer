"""处理流水线 — 每一步完成后更新中间结果，前端可实时展示"""

import asyncio
import uuid

from typing import Dict, Optional

from models import (
    AnalysisResult,
    AnalyzeRequest,
    TaskStatus,
    VideoCategory,
)

_tasks: Dict[str, TaskStatus] = {}


def get_task(task_id: str) -> Optional[TaskStatus]:
    return _tasks.get(task_id)


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


def _build_result(title, url, bvid, first_pass=None, qa_sections=None):
    """构建（可能不完整的）AnalysisResult"""
    from note import generate_markdown

    result = AnalysisResult(
        video_title=title,
        video_url=url,
        bvid=bvid,
        category=first_pass["category"] if first_pass else VideoCategory.KNOWLEDGE,
        summary=first_pass["summary"] if first_pass else "",
        practical_values=first_pass.get("practical_values") if first_pass else None,
        key_terms=first_pass["key_terms"] if first_pass else [],
        qa_sections=qa_sections,
    )
    result.markdown = generate_markdown(result)
    return result


async def _process(task_id: str, req: AnalyzeRequest):
    task = _tasks[task_id]
    title = ""
    first_pass = None
    qa_sections = None

    try:
        bvid = _extract_bvid(req.url)

        # ── Step 0: 视频标题 ──
        _update(task, "transcribing", 5, "获取视频信息...")
        from transcript import get_video_title
        title = await get_video_title(bvid)

        # ── Step 1: 转录 ──
        _update(task, "transcribing", 10, "获取转录文本...")
        from transcript import get_transcript
        segments = await get_transcript(req, bvid)
        _update(task, "transcribing", 20,
                f"转录完成，共 {len(segments)} 条字幕，开始 AI 分析...")

        # ── Step 2: 第一轮 — 分类 + 摘要 + 实用价值 + 关键术语 ──
        _update(task, "analyzing", 30, "AI 分类 + 提取关键术语中...")
        from analyzer import analyze_first_pass
        first_pass = await analyze_first_pass(segments, title)

        cat_cn = {
            VideoCategory.ENTERTAINMENT: "娱乐",
            VideoCategory.TUTORIAL: "教程",
            VideoCategory.KNOWLEDGE: "知识讲解",
        }.get(first_pass["category"], "未知")
        _update(task, "analyzing", 50,
                f"识别为「{cat_cn}」视频，深度提取中...")
        task.result = _build_result(title, req.url, bvid, first_pass)

        # ── Step 3: 第二轮 — Q&A 深度提取（统一三类）──
        from analyzer import extract_qa_sections
        _update(task, "analyzing", 55, "问答式深度提取中...")
        qa_sections = await extract_qa_sections(segments, first_pass["category"])
        task.result = _build_result(title, req.url, bvid, first_pass, qa_sections)
        _update(task, "analyzing", 90, "深度提取完成，生成笔记...")

        # ── Step 4: 最终结果 ──
        _update(task, "analyzing", 95, "生成最终笔记...")
        task.result = _build_result(title, req.url, bvid, first_pass, qa_sections)
        _update(task, "done", 100, "分析完成")

    except Exception as e:
        import traceback
        traceback.print_exc()
        if first_pass and not task.result:
            try:
                task.result = _build_result(title, req.url, bvid, first_pass, qa_sections)
            except Exception:
                pass
        _update(task, "error", task.progress, f"错误: {e}")
