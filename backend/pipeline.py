"""处理流水线 — 每一步完成后更新中间结果，前端可实时展示"""

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


def _build_result(title, url, bvid, first_pass=None, qa_sections=None,
                   title_hook="", title_explanation="", cover_url=""):
    """构建（可能不完整的）AnalysisResult"""
    from note import generate_markdown

    result = AnalysisResult(
        video_title=title,
        video_url=url,
        bvid=bvid,
        cover_url=cover_url or None,
        category=first_pass["category"] if first_pass else VideoCategory.KNOWLEDGE,
        summary=first_pass["summary"] if first_pass else "",
        title_hook=title_hook,
        title_explanation=title_explanation,
        practical_values=first_pass.get("practical_values") if first_pass else None,
        concept_flow=first_pass.get("concept_flow", []) if first_pass else [],
        term_groups=first_pass.get("term_groups") if first_pass else None,
        qa_sections=qa_sections,
    )
    result.markdown = generate_markdown(result)
    return result


async def _process(task_id: str, req: AnalyzeRequest):
    task = _tasks[task_id]
    title = ""
    cover_url = ""
    title_hook = ""
    title_explanation = ""
    first_pass = None
    qa_sections = None

    try:
        bvid = _extract_bvid(req.url)

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

        # 缓存转录，用于后续术语追问
        _transcripts[bvid] = segments

        _update(task, "transcribing", 20,
                f"转录完成，共 {len(segments)} 条字幕")

        # ── Step 1.5: 快速标题解读（让用户早点看到内容）──
        _update(task, "analyzing", 22, "解读标题中...")
        from analyzer import explain_title
        title_info = await explain_title(segments, title)
        title_hook = title_info.get("hook", "")
        title_explanation = title_info.get("answer", "")
        task.result = _build_result(
            title, req.url, bvid,
            title_hook=title_hook, title_explanation=title_explanation,
            cover_url=cover_url
        )
        _update(task, "analyzing", 28, "标题解读完成，AI 深度分析中...")

        # ── Step 2: 第一轮 — 分类 + 摘要 + 分组术语 + 概念脉络 ──
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
        task.result = _build_result(
            title, req.url, bvid, first_pass,
            title_hook=title_hook, title_explanation=title_explanation,
            cover_url=cover_url
        )

        # ── Step 3: 第二轮 — Q&A 深度提取 ──
        from analyzer import extract_qa_sections
        _update(task, "analyzing", 55, "问答式深度提取中...")
        qa_sections = await extract_qa_sections(segments, first_pass["category"])
        task.result = _build_result(
            title, req.url, bvid, first_pass, qa_sections,
            title_hook=title_hook, title_explanation=title_explanation,
            cover_url=cover_url
        )
        _update(task, "analyzing", 90, "深度提取完成，生成笔记...")

        # ── Step 4: 最终结果 + 持久化 ──
        _update(task, "analyzing", 95, "生成最终笔记...")
        task.result = _build_result(
            title, req.url, bvid, first_pass, qa_sections,
            title_hook=title_hook, title_explanation=title_explanation,
            cover_url=cover_url
        )

        # 写入 SQLite
        from db import save_note
        try:
            save_note(task.result.model_dump())
        except Exception:
            pass  # 持久化失败不影响主流程

        _update(task, "done", 100, "分析完成")

    except Exception as e:
        import traceback
        traceback.print_exc()
        if first_pass and not task.result:
            try:
                task.result = _build_result(
                    title, req.url, bvid, first_pass, qa_sections,
                    title_explanation=title_explanation, cover_url=cover_url
                )
            except Exception:
                pass
        _update(task, "error", task.progress, f"错误: {e}")
