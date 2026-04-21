"""Claude API 分析 — 单轮调用，分类+深度提取一次完成"""

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


# ── 单轮完整分析：分类 + 摘要 + 术语 + 脉络 + QA ────

SYSTEM_FULL = (
    "你是一个视频内容分析专家。深度分析视频转录文本，一次性完成分类、结构提取和问答深度分析。"
    "只返回 JSON，不要输出任何其他内容。"
)

USER_FULL = """深度分析以下视频转录文本，一次性完成全部任务。

## 任务一：分类 + 摘要 + 结构提取

1. 视频分类（三选一）：
   - entertainment：娱乐/访谈/搞笑/vlog/脱口秀/生活分享
   - tutorial：动手教程/操作指南/编程教学/手工制作/烹饪教学（有明确的分步操作）
   - knowledge：知识讲解/论文解读/科普/分析评论/历史讲述/技术原理（重在讲解而非动手）

2. 100 字以内的中文摘要

3. 2-4 条"实用价值"：这个视频的信息对观众有什么用？

4. **概念脉络**（树状结构）：用 5-8 个节点串起视频的核心逻辑。
   - depth=0 表示主线节点，depth=1 表示子论点
   - timestamp 使用 | 后面的秒数值
   示例：
   [
     {{"label": "残差连接是10年标准", "timestamp": 30.0, "depth": 0}},
     {{"label": "存在两个核心缺陷", "timestamp": 85.0, "depth": 1}},
     {{"label": "类比RNN的解决思路", "timestamp": 150.0, "depth": 0}}
   ]

5. **分组关键术语**：将 5-15 个关键术语按领域分组。
   - term：修正 ASR 错误后的正确名称
   - timestamp：首次出现的精确秒数
   - explanation：一句话解释该术语在本视频语境下的含义
   - 分组名简短（2-4字）

## 任务二：问答式深度提取（4-8 个问题）

根据你的分类结果，选择对应风格：

**entertainment：** 他们在聊什么？最颠覆认知的观点？最精彩的一句话？有争议吗？
→ 金句放 quote 字段

**tutorial：** 最终效果？需要准备什么？核心操作步骤？容易踩的坑？
→ 步骤/清单用 sub_points 字段

**knowledge：** 要解决什么问题？核心方法/原理？有什么证据？优势？局限性？
→ 实验数据放 evidence 字段

## 通用规则
- 转录格式 [MM:SS | Ns]，timestamp **直接用 | 后面的秒数**
- 问题要像好奇的观众会问的，自然、口语化
- 回答完整准确，2-4 句话讲清楚
- **修正明显的 ASR 错误**，保持原意

视频标题：{title}

转录文本：
{transcript}

返回 JSON（严格遵循此结构）：
{{
  "category": "entertainment 或 tutorial 或 knowledge",
  "summary": "100字摘要",
  "practical_values": [
    {{"point": "用途", "detail": "展开说明"}}
  ],
  "concept_flow": [
    {{"label": "节点描述", "timestamp": 30.0, "depth": 0}}
  ],
  "term_groups": [
    {{
      "group_name": "领域名",
      "terms": [
        {{"term": "术语名", "timestamp": 205.0, "explanation": "一句话解释"}}
      ]
    }}
  ],
  "qa_sections": [
    {{
      "question": "观众会问的问题？",
      "answer": "完整的回答",
      "timestamp": 120.0,
      "quote": "值得展示的原话 或 null",
      "sub_points": ["要点1", "要点2"],
      "evidence": "实验数据 或 null"
    }}
  ]
}}"""


async def analyze_full(
    segments: List[TextSegment], title: str
) -> Dict:
    """单次 Claude 调用完成全部分析（分类+摘要+术语+脉络+QA）"""
    transcript_text = format_transcript(segments)
    prompt = USER_FULL.format(title=title, transcript=transcript_text)
    raw = await _call_claude(SYSTEM_FULL, prompt, max_tokens=8192)
    data = _parse_json(raw)

    cat_str = data["category"]
    if cat_str == "educational":
        cat_str = "tutorial"

    # 解析术语分组
    term_groups = []
    for g in data.get("term_groups", []):
        terms = [
            KeyTerm(
                term=t["term"],
                timestamp=float(t["timestamp"]),
                explanation=t["explanation"],
            )
            for t in g.get("terms", [])
        ]
        term_groups.append(TermGroup(group_name=g["group_name"], terms=terms))

    # 解析概念脉络
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
        concept_flow = [
            FlowNode(label=part.strip(), timestamp=0, depth=0)
            for part in str(raw_flow).split("→")
            if part.strip()
        ]

    # 解析 QA
    qa_sections = [
        QASection(
            question=q["question"],
            answer=q["answer"],
            timestamp=float(q["timestamp"]),
            quote=q.get("quote"),
            sub_points=q.get("sub_points"),
            evidence=q.get("evidence"),
        )
        for q in data.get("qa_sections", [])
    ]

    return {
        "category": VideoCategory(cat_str),
        "summary": data["summary"],
        "practical_values": [
            PracticalValue(point=p["point"], detail=p["detail"])
            for p in data.get("practical_values", [])
        ],
        "concept_flow": concept_flow,
        "term_groups": term_groups,
        "qa_sections": qa_sections,
    }


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
