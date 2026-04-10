"""Markdown 笔记生成"""

from typing import List

from models import AnalysisResult, VideoCategory


def _timestamp_link(seconds: float, video_url: str) -> str:
    """生成 B 站带时间戳的跳转链接"""
    t = int(seconds)
    mm, ss = divmod(t, 60)
    hh, mm = divmod(mm, 60)
    display = f"{hh:02d}:{mm:02d}:{ss:02d}" if hh else f"{mm:02d}:{ss:02d}"
    return f"[{display}]({video_url}?t={t})"


def generate_markdown(result: AnalysisResult) -> str:
    lines: List[str] = []

    # ── 标题 + 元信息 ──
    lines.append(f"# {result.video_title}")
    lines.append("")
    lines.append(f"> 来源: [{result.video_url}]({result.video_url})")
    cat_map = {
        VideoCategory.ENTERTAINMENT: "娱乐",
        VideoCategory.TUTORIAL: "教程",
        VideoCategory.KNOWLEDGE: "知识讲解",
    }
    lines.append(f"> 分类: {cat_map.get(result.category, str(result.category))}")
    lines.append("")

    # ── 标题解读 ──
    if result.title_explanation:
        hook = result.title_hook if result.title_hook else "这个标题在说什么？"
        lines.append(f"## {hook}")
        lines.append("")
        lines.append(result.title_explanation)
        lines.append("")

    # ── 摘要 ──
    lines.append("## 摘要")
    lines.append("")
    lines.append(result.summary)
    lines.append("")

    # ── 实用价值 ──
    if result.practical_values:
        lines.append("## 这个视频对你有什么用？")
        lines.append("")
        for pv in result.practical_values:
            lines.append(f"- **{pv.point}** — {pv.detail}")
        lines.append("")

    # ── 概念脉络 ──
    if result.concept_flow:
        lines.append("## 概念脉络")
        lines.append("")
        for node in result.concept_flow:
            ts = _timestamp_link(node.timestamp, result.video_url)
            indent = "  " if node.depth > 0 else ""
            lines.append(f"{indent}- {node.label} {ts}")
        lines.append("")

    # ── 分组关键术语 ──
    if result.term_groups:
        lines.append("## 关键术语")
        lines.append("")
        for group in result.term_groups:
            lines.append(f"### {group.group_name}")
            lines.append("")
            for term in group.terms:
                ts = _timestamp_link(term.timestamp, result.video_url)
                lines.append(
                    f"- **{term.term}** {ts} — {term.explanation}"
                )
            lines.append("")

    # ── Q&A 深度内容 ──
    if result.qa_sections:
        lines.append("## 深度解析")
        lines.append("")
        for qa in result.qa_sections:
            ts = _timestamp_link(qa.timestamp, result.video_url)
            lines.append(f"### {qa.question}")
            lines.append("")
            lines.append(f"{ts}")
            lines.append("")
            lines.append(qa.answer)
            if qa.quote:
                lines.append("")
                lines.append(f"> 💬 {qa.quote}")
            if qa.evidence:
                lines.append("")
                lines.append(f"> 📊 {qa.evidence}")
            if qa.sub_points:
                lines.append("")
                for pt in qa.sub_points:
                    lines.append(f"- {pt}")
            lines.append("")

    return "\n".join(lines)
