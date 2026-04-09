"""核心数据模型 — 整个系统的数据结构定义"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


# ── 枚举 ──────────────────────────────────────────────

class TranscriptSource(str, Enum):
    BILIBILI_API = "bilibili_api"
    WHISPER_LOCAL = "whisper_local"
    CLOUD_API = "cloud_api"


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


# ── 分析结果子结构 ────────────────────────────────────

class KeyTerm(BaseModel):
    term: str
    timestamp: float
    context: str


class GoldenQuote(BaseModel):
    quote: str
    timestamp: float
    speaker: Optional[str] = None


class InstructionStep(BaseModel):
    step_number: int
    title: str
    description: str
    timestamp: float
    needs_visual: bool = False
    frame_path: Optional[str] = None
    gif_path: Optional[str] = None


class PracticalValue(BaseModel):
    """实用价值 — 这些信息对你有什么用"""
    point: str
    detail: str


class QASection(BaseModel):
    """问答板块 — 问题驱动的内容结构"""
    question: str
    answer: str
    timestamp: float
    quote: Optional[str] = None       # 值得单独展示的金句
    sub_points: Optional[List[str]] = None  # 分步或要点列表
    evidence: Optional[str] = None    # 数据/实验结果


# ── 分析结果 ──────────────────────────────────────────

class AnalysisResult(BaseModel):
    video_title: str
    video_url: str
    bvid: str
    category: VideoCategory
    summary: str
    practical_values: Optional[List[PracticalValue]] = None
    key_terms: List[KeyTerm]
    qa_sections: Optional[List[QASection]] = None
    markdown: str = ""


# ── 任务状态（轮询用） ────────────────────────────────

class TaskStatus(BaseModel):
    task_id: str
    status: str = "pending"   # pending | transcribing | analyzing | extracting_frames | done | error
    progress: int = 0         # 0-100
    message: str = "排队中"
    result: Optional[AnalysisResult] = None
