"""Claude API 分析 — 两轮调用，先分类再分支"""

import asyncio
import json
import re
from typing import Dict, List

import httpx

import config
from models import (
    FlowNode,
    KeyTerm,
    PracticalValue,
    QASection,
    TermGroup,
    TextSegment,
    VideoCategory,
)
from transcript import format_transcript

# ── Claude API 封装 ───────────────────────────────────


async def _call_claude(system: str, user: str, max_tokens: int = 4096) -> str:
    """调用 Claude API，带重试（覆盖超时、断连、限流）"""
    if not config.CLAUDE_API_KEY:
        raise ValueError("未设置 CLAUDE_API_KEY，请在 App 设置 (Cmd+,) 中填写")

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
                        "max_tokens": max_tokens,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
                if resp.status_code == 401:
                    raise ValueError("Claude API Key 无效，请在 App 设置 (Cmd+,) 中检查")
                if resp.status_code == 429 and attempt < 3:
                    wait = 2 ** (attempt + 1)
                    print(f"[Claude] 限流，{wait}秒后重试...")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                # 遍历 content blocks，取第一个 text 块
                # （跳过 thinking / tool_use 等非文本块）
                for block in data.get("content", []):
                    if isinstance(block, dict) and "text" in block:
                        return block["text"]
                raise ValueError(
                    f"Claude API 返回无文本内容: {str(data)[:300]}"
                )
        except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            last_err = e
            if attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"[Claude] 连接异常 ({type(e).__name__})，{wait}秒后重试...")
                await asyncio.sleep(wait)
                continue
    raise ValueError(f"Claude API 连接失败（重试 4 次）: {last_err}")


def _fix_unescaped_quotes(s: str) -> str:
    """修复 JSON 字符串值中未转义的双引号。"""
    result = []
    i = 0
    n = len(s)
    in_string = False

    while i < n:
        c = s[i]

        if in_string and c == '\\' and i + 1 < n:
            result.append(c)
            result.append(s[i + 1])
            i += 2
            continue

        if c == '"':
            if not in_string:
                in_string = True
                result.append(c)
            else:
                rest = s[i + 1:].lstrip()
                if not rest or rest[0] in ',:}]':
                    in_string = False
                    result.append(c)
                else:
                    result.append('\\"')
            i += 1
            continue

        result.append(c)
        i += 1

    return ''.join(result)


def _parse_json(text: str) -> dict:
    """从 Claude 返回中提取 JSON（兼容各种 LLM 输出格式）"""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    candidate = m.group(1).strip() if m else text.strip()

    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1:
            candidate = candidate[start:end + 1]

    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    candidate = re.sub(r"//.*$", "", candidate, flags=re.MULTILINE)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    fixed = _fix_unescaped_quotes(candidate)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        print(f"[JSON解析失败] 错误: {e}")
        print(f"[JSON解析失败] 原始响应前500字符:\n{text[:500]}")
        raise ValueError(f"Claude 返回的 JSON 格式异常: {e}")


# ── 第一轮：分类 + 摘要 + 分组术语 + 概念脉络 ────────

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

3. 2-4 条"实用价值"：这个视频的信息对观众有什么用？可以用在哪里？

4. **概念脉络**（树状结构）：用 5-8 个节点串起视频的核心逻辑。
   - depth=0 表示主线节点，depth=1 表示对上一个主线的补充/子论点
   - timestamp 使用 | 后面的秒数值
   示例：
   [
     {{"label": "残差连接是10年标准", "timestamp": 30.0, "depth": 0}},
     {{"label": "存在两个核心缺陷", "timestamp": 85.0, "depth": 1}},
     {{"label": "类比RNN的解决思路", "timestamp": 150.0, "depth": 0}},
     {{"label": "注意力机制迁移到深度维度", "timestamp": 210.0, "depth": 0}},
     {{"label": "分块策略降低计算量", "timestamp": 305.0, "depth": 1}},
     {{"label": "实测多项SOTA提升", "timestamp": 420.0, "depth": 0}}
   ]

5. **分组关键术语**：将 5-15 个关键术语按领域分组。每个术语需要：
   - term：修正后的正确名称（修正 ASR 错误，如 "WESNET"→"ResNet"）
   - timestamp：首次出现的精确秒数
   - explanation：一句话解释这个术语在本视频语境下的含义（不是字典定义，而是在这个视频里它代表什么）

注意：
- 转录每一行格式为 [MM:SS | Ns]，其中 N 是精确秒数。timestamp **直接使用 | 后面的秒数值**，不要自行计算。
- 分组名要简短（2-4个字），如"基础架构"、"核心创新"、"实验评测"、"人物/团队"

视频标题：{title}

转录文本：
{transcript}

返回 JSON：
{{
  "category": "entertainment" 或 "tutorial" 或 "knowledge",
  "summary": "摘要",
  "practical_values": [
    {{"point": "用途", "detail": "展开说明"}}
  ],
  "concept_flow": [
    {{"label": "节点描述", "timestamp": 30.0, "depth": 0}},
    {{"label": "子节点", "timestamp": 60.0, "depth": 1}}
  ],
  "term_groups": [
    {{
      "group_name": "领域名",
      "terms": [
        {{"term": "术语名", "timestamp": 205.0, "explanation": "一句话解释"}}
      ]
    }}
  ]
}}"""


async def analyze_first_pass(
    segments: List[TextSegment], title: str
) -> Dict:
    transcript_text = format_transcript(segments)
    prompt = USER_FIRST_PASS.format(title=title, transcript=transcript_text)
    raw = await _call_claude(SYSTEM_FIRST_PASS, prompt)
    data = _parse_json(raw)

    cat_str = data["category"]
    if cat_str == "educational":
        cat_str = "tutorial"

    term_groups = []
    for g in data.get("term_groups", []):
        terms = [
            KeyTerm(
                term=t["term"],
                timestamp=float(t["timestamp"]),
                explanation=t["explanation"],
            )
            for t in g["terms"]
        ]
        term_groups.append(TermGroup(group_name=g["group_name"], terms=terms))

    # 解析概念脉络：优先树状数组，兼容旧版字符串
    raw_flow = data.get("concept_flow", [])
    if isinstance(raw_flow, list):
        concept_flow = [
            FlowNode(
                label=n.get("label", ""),
                timestamp=float(n.get("timestamp", 0)),
                depth=int(n.get("depth", 0)),
            )
            for n in raw_flow
            if isinstance(n, dict) and n.get("label")
        ]
    else:
        # Claude 返回了字符串，拆成单层节点
        concept_flow = [
            FlowNode(label=part.strip(), timestamp=0, depth=0)
            for part in str(raw_flow).split("→")
            if part.strip()
        ]

    return {
        "title": title,
        "category": VideoCategory(cat_str),
        "summary": data["summary"],
        "practical_values": [
            PracticalValue(point=p["point"], detail=p["detail"])
            for p in data.get("practical_values", [])
        ],
        "concept_flow": concept_flow,
        "term_groups": term_groups,
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
- sub_points 字段：需要列出要点/步骤时使用，没有则为 null
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


# ── 术语追问 ─────────────────────────────────────────

SYSTEM_ASK = (
    "你是一个知识讲解专家。用户正在看一个视频的分析笔记，"
    "对其中一个术语有疑问。请结合视频上下文给出清晰、有深度的回答。"
    "直接回答，不要使用 JSON 格式。用中文回答，可以用 Markdown 格式。"
)

USER_ASK = """用户正在看视频「{title}」的分析笔记。

术语：{term}
已有解释：{explanation}
该术语在视频中出现的位置附近的转录内容：
---
{context}
---

用户的追问：{question}

请结合视频上下文回答。如果用户的问题超出视频内容范围，可以适当补充外部知识，但要标明哪些是视频里说的、哪些是你补充的。"""


async def ask_about_term(
    title: str,
    term: str,
    explanation: str,
    timestamp: float,
    question: str,
    segments: List[TextSegment],
) -> str:
    """针对某个术语的追问，带视频上下文回答"""
    # 提取 timestamp ±60 秒范围内的转录作为上下文
    context_lines = []
    for seg in segments:
        if abs(seg.start - timestamp) <= 60:
            mm, ss = divmod(int(seg.start), 60)
            context_lines.append(f"[{mm:02d}:{ss:02d}] {seg.text}")
    context = "\n".join(context_lines) if context_lines else "（无相关上下文）"

    prompt = USER_ASK.format(
        title=title,
        term=term,
        explanation=explanation,
        context=context,
        question=question,
    )
    return await _call_claude(SYSTEM_ASK, prompt)


# ── 标题解读（快速调用，减少等待感）─────────────────

SYSTEM_TITLE = (
    "你是一个视频内容分析师。分析视频标题，找出观众最好奇的点，"
    "用一个问题概括这种好奇心，然后简要回答。只返回 JSON，不要输出其他内容。"
)

USER_TITLE = """视频标题：{title}

视频开头的转录内容（前2分钟）：
{transcript_head}

任务：找出标题中最让人好奇的点，变成一个问题，然后回答。

关键要求：
- 想清楚：**观众点进这个视频，最想得到答案的那个问题是什么？**
- 标题往往包含多个信息点（身份、数据、方法等），你要判断哪个才是视频真正要回答的核心问题
- 用标题里的关键词构造问题，简洁但不要为了短而丢掉关键信息

思考方式：
1. 标题里哪些词是"钩子"（引发好奇的）？哪些词是"答案方向"（视频要讲的）？
2. 钩子让人点进来，但 hook 问题应该指向视频要讲的那个核心内容

示例：
标题 "ICLR神作！文言文硬控全网大模型，100%越狱！" → "文言文怎么硬控大模型？"
  （"ICLR神作"是背景，"文言文硬控"才是视频要讲的核心方法）
标题 "高中生自媒体八个月变现六位数，他的工作流是怎样的？！" → "他的工作流是怎样的？"
  （"高中生""六位数"是钩子，但视频核心内容是讲工作流）
标题 "GPT-5来了！OpenAI这次赌上一切" → "OpenAI赌上了什么？"
标题 "月入3万的副业，普通人也能做" → "月入3万的副业是什么？"

返回 JSON：
{{"hook": "观众最想得到答案的那个问题", "answer": "2-3句话回答"}}"""


async def explain_title(segments: List[TextSegment], title: str) -> dict:
    """快速解读标题 — 返回 hook(好奇心问题) + answer(回答)"""
    head_lines = []
    for seg in segments:
        if seg.start > 120:
            break
        head_lines.append(seg.text)
    transcript_head = "\n".join(head_lines) if head_lines else "（无转录内容）"
    prompt = USER_TITLE.format(title=title, transcript_head=transcript_head)
    raw = await _call_claude(SYSTEM_TITLE, prompt, max_tokens=512)
    try:
        data = _parse_json(raw)
        return {"hook": data.get("hook", ""), "answer": data.get("answer", "")}
    except Exception:
        return {"hook": "", "answer": raw.strip()}
