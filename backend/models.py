"""核心数据模型 — 整个系统的数据结构定义"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


# ── 枚举 ──────────────────────────────────────────────

class TranscriptSource(str, Enum):
    BILIBILI_API = "bilibili_api"
    WHISPER_LOCAL = "whisper_local"


class VideoCategory(str, Enum):
    ENTERTAINMENT = "entertainment"
    TUTORIAL = "tutorial"
    KNOWLEDGE = "knowledge"


# ── 核心原子：带时间戳的文本段 ─────────────────────────

class TextSegment(BaseModel):
    start: float  # 秒
    end: float
    text: str


# ── 请求 ──────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    url: str
    transcript_source: TranscriptSource = TranscriptSource.BILIBILI_API
    bilibili_sessdata: Optional[str] = None
    whisper_model: Optional[str] = None


class AskRequest(BaseModel):
    bvid: str
    term: str
    explanation: str
    timestamp: float
    question: str


# ── 分析结果子结构 ────────────────────────────────────

class KeyTerm(BaseModel):
    term: str
    timestamp: float
    explanation: str  # AI 生成的一句话解释（替代 ASR 原文 context）


class TermGroup(BaseModel):
    group_name: str  # 领域分类名，如"基础架构"、"核心创新"
    terms: List[KeyTerm]


class FlowNode(BaseModel):
    """概念脉络节点 — 树状因果链的一个节点"""
    label: str
    timestamp: float
    depth: int = 0  # 0=主线, 1=子节点


class PracticalValue(BaseModel):
    """实用价值 — 这些信息对你有什么用"""
    point: str
    detail: str


class QASection(BaseModel):
    """问答板块 — 问题驱动的内容结构"""
    question: str
    answer: str
    timestamp: float
    quote: Optional[str] = None
    sub_points: Optional[List[str]] = None
    evidence: Optional[str] = None


# ── 分析结果 ──────────────────────────────────────────

class AnalysisResult(BaseModel):
    video_title: str
    video_url: str
    bvid: str
    cover_url: Optional[str] = None
    category: VideoCategory
    summary: str
    title_hook: str = ""  # 标题好奇心问题（如"为何说文言文硬控全网大模型？"）
    title_explanation: str = ""  # 标题解读答案
    practical_values: Optional[List[PracticalValue]] = None
    concept_flow: List[FlowNode] = []  # 概念脉络，树状因果链
    term_groups: Optional[List[TermGroup]] = None
    qa_sections: Optional[List[QASection]] = None
    markdown: str = ""


# ── 任务状态（轮询用） ────────────────────────────────

class TaskStatus(BaseModel):
    task_id: str
    status: str = "pending"
    progress: int = 0
    message: str = "排队中"
    result: Optional[AnalysisResult] = None
