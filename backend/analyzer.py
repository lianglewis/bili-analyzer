"""Claude API 分析 — 两轮调用，先分类再分支"""

import asyncio
import json
import re
from typing import Dict, List

import httpx

import config
from models import (
    KeyTerm,
    PracticalValue,
    QASection,
    TextSegment,
    VideoCategory,
)
from transcript import format_transcript

# ── Claude API 封装 ───────────────────────────────────


async def _call_claude(system: str, user: str) -> str:
    """调用 Claude API，带重试（覆盖超时、断连、限流）"""
    if not config.CLAUDE_API_KEY:
        raise ValueError("未设置 CLAUDE_API_KEY 环境变量")

    last_err = None
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    config.CLAUDE_API_URL,
                    headers={
                        "x-api-key": config.CLAUDE_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": config.CLAUDE_MODEL,
                        "max_tokens": 4096,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
                if resp.status_code == 401:
                    raise ValueError("Claude API Key 无效，请检查 CLAUDE_API_KEY 环境变量")
                if resp.status_code == 429 and attempt < 3:
                    wait = 2 ** (attempt + 1)
                    print(f"[Claude] 限流，{wait}秒后重试...")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["content"][0]["text"]
        except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            last_err = e
            if attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"[Claude] 连接异常 ({type(e).__name__})，{wait}秒后重试...")
                await asyncio.sleep(wait)
                continue
    raise ValueError(f"Claude API 连接失败（重试 4 次）: {last_err}")


def _fix_unescaped_quotes(s: str) -> str:
    """修复 JSON 字符串值中未转义的双引号。

    LLM 经常在 JSON 值里放 "引号" 但不转义。
    策略：用状态机遍历，在字符串内部遇到 " 时，
    看后面是不是 JSON 结构符（, : } ]），如果不是就转义它。
    """
    result = []
    i = 0
    n = len(s)
    in_string = False

    while i < n:
        c = s[i]

        # 处理转义序列
        if in_string and c == '\\' and i + 1 < n:
            result.append(c)
            result.append(s[i + 1])
            i += 2
            continue

        if c == '"':
            if not in_string:
                # 进入字符串
                in_string = True
                result.append(c)
            else:
                # 判断这个 " 是字符串结束还是内容里的引号
                # 往后看：跳过空白后，如果是 , : } ] 或到末尾 → 是结束引号
                rest = s[i + 1:].lstrip()
                if not rest or rest[0] in ',:}]':
                    in_string = False
                    result.append(c)
                else:
                    # 内容里的引号，转义掉
                    result.append('\\"')
            i += 1
            continue

        result.append(c)
        i += 1

    return ''.join(result)


def _parse_json(text: str) -> dict:
    """从 Claude 返回中提取 JSON（兼容各种 LLM 输出格式）"""
    # 1. 尝试提取 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    candidate = m.group(1).strip() if m else text.strip()

    # 2. 如果不是以 { 开头，定位到 JSON 主体
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1:
            candidate = candidate[start:end + 1]

    # 3. 清理常见的 LLM JSON 问题
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)  # 尾随逗号
    candidate = re.sub(r"//.*$", "", candidate, flags=re.MULTILINE)  # 注释

    # 4. 尝试解析
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 5. 修复未转义的引号后重试
    fixed = _fix_unescaped_quotes(candidate)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        print(f"[JSON解析失败] 错误: {e}")
        print(f"[JSON解析失败] 原始响应前500字符:\n{text[:500]}")
        raise ValueError(f"Claude 返回的 JSON 格式异常: {e}")


# ── 第一轮：分类 + 摘要 + 关键术语 ───────────────────

SYSTEM_FIRST_PASS = (
    "你是一个视频内容分析专家。分析视频转录文本，返回 JSON 格式结果。"
    "不要输出 JSON 以外的任何内容。"
)

USER_FIRST_PASS = """分析以下视频转录文本：

1. 视频分类（三选一）：
   - entertainment：娱乐/访谈/搞笑/vlog/脱口秀/生活分享
   - tutorial：动手教程/操作指南/编程教学/手工制作/烹饪教学（有明确的分步操作）
   - knowledge：知识讲解/论文解读/科普/分析评论/历史讲述/技术原理（重在讲解而非动手）

2. 100 字以内的中文摘要

3. 2-4 条"实用价值"：这个视频的信息对观众有什么用？可以用在哪里？帮助用户快速判断是否值得深看。

4. 5-15 个关键术语/名词

注意：
- 转录每一行格式为 [MM:SS | Ns]，其中 N 是精确秒数。返回 timestamp 时，**直接使用该行 | 后面的秒数值**（如 205.0），不要自行从 MM:SS 计算。
- 转录来自语音识别，可能有错字。术语 term 字段请根据上下文**修正为正确拼写**（如 "WESNET"→"ResNet"，"attend race"→"Attention Residual"）。context 保留原文不改。

视频标题：{title}

转录文本：
{transcript}

返回 JSON：
{{
  "category": "entertainment" 或 "tutorial" 或 "knowledge",
  "summary": "摘要",
  "practical_values": [
    {{"point": "一句话说明用途", "detail": "展开说明怎么用、用在哪"}}
  ],
  "key_terms": [
    {{"term": "修正后的术语", "timestamp": 205.0, "context": "该术语所在的那一行转录原文（保留原文）"}}
  ]
}}"""


async def analyze_first_pass(
    segments: List[TextSegment], title: str
) -> Dict:
    transcript_text = format_transcript(segments)
    prompt = USER_FIRST_PASS.format(title=title, transcript=transcript_text)
    raw = await _call_claude(SYSTEM_FIRST_PASS, prompt)
    data = _parse_json(raw)

    # 兼容旧的 educational 分类 → 映射到 knowledge
    cat_str = data["category"]
    if cat_str == "educational":
        cat_str = "tutorial"

    return {
        "title": title,
        "category": VideoCategory(cat_str),
        "summary": data["summary"],
        "practical_values": [
            PracticalValue(point=p["point"], detail=p["detail"])
            for p in data.get("practical_values", [])
        ],
        "key_terms": [
            KeyTerm(
                term=t["term"],
                timestamp=float(t["timestamp"]),
                context=t["context"],
            )
            for t in data["key_terms"]
        ],
    }


# ── 第二轮：问答式深度提取（统一三类）──────────────

SYSTEM_QA = (
    "你是一个视频内容深度分析专家。用问答结构提炼视频核心内容。"
    "返回 JSON 格式，不要输出其他内容。"
)

_QA_GUIDE = {
    "entertainment": """这是一个娱乐/访谈/脱口秀类视频。请用 4-8 个问题梳理内容。
问题风格参考（不必全用，根据内容选择）：
- "他们在聊什么？"（主题概述）
- "最颠覆认知的观点是什么？"
- "最精彩的一句话是什么？"（quote 字段放原话）
- "有什么争议或分歧？"
- "结论是什么？"

每个回答里如果有值得单独展示的金句，放到 quote 字段。""",

    "tutorial": """这是一个动手教程类视频。请用 4-8 个问题梳理内容。
问题风格参考（不必全用，根据内容选择）：
- "最终要实现什么效果？"
- "需要准备什么工具/材料？"（sub_points 列出清单）
- "核心操作步骤是什么？"（sub_points 列出分步）
- "有什么容易踩的坑？"
- "怎么验证做对了？"

操作步骤类的回答用 sub_points 列出分步要点。""",

    "knowledge": """这是一个知识讲解/论文解读/科普类视频。请用 4-8 个问题梳理内容。
问题风格参考（不必全用，根据内容选择）：
- "这个研究/话题要解决什么问题？"
- "核心方法/原理是什么？"
- "有什么证据或实验数据支撑？"（evidence 字段放数据）
- "和现有方案相比优势在哪？"
- "有什么局限性？"
- "这意味着什么？对未来有什么影响？"

有实验数据的放到 evidence 字段。""",
}

USER_QA = """以下是一个视频的转录文本，请用**问答结构**提炼核心内容。

{category_guide}

规则：
- 问题要像一个好奇的观众会问的，自然、口语化、有吸引力
- 回答要完整、准确，2-4 句话把这个点讲清楚
- 转录来自语音识别，回答中请**修正明显的 ASR 错误**（错别字、专有名词），但保持原意
- 转录每一行格式为 [MM:SS | Ns]，N 是精确秒数。timestamp **直接使用 | 后面的秒数值**，不要自行计算
- quote 字段：该问答中最值得单独展示的一句原话（修正 ASR 错误后），没有则为 null
- sub_points 字段：需要列出要点/步骤时使用（如工具清单、操作步骤），没有则为 null
- evidence 字段：有具体数据/实验结果时使用，没有则为 null

转录文本：
{transcript}

返回 JSON：
{{
  "qa_sections": [
    {{
      "question": "观众会问的问题？",
      "answer": "完整的回答",
      "timestamp": 120.0,
      "quote": "值得展示的原话（或 null）",
      "sub_points": ["要点1", "要点2"] 或 null,
      "evidence": "实验数据（或 null）"
    }}
  ]
}}"""


async def extract_qa_sections(
    segments: List[TextSegment],
    category: VideoCategory,
) -> List[QASection]:
    transcript_text = format_transcript(segments)
    guide = _QA_GUIDE.get(category.value, _QA_GUIDE["knowledge"])
    prompt = USER_QA.format(
        category_guide=guide,
        transcript=transcript_text,
    )
    raw = await _call_claude(SYSTEM_QA, prompt)
    data = _parse_json(raw)

    return [
        QASection(
            question=q["question"],
            answer=q["answer"],
            timestamp=float(q["timestamp"]),
            quote=q.get("quote"),
            sub_points=q.get("sub_points"),
            evidence=q.get("evidence"),
        )
        for q in data["qa_sections"]
    ]
