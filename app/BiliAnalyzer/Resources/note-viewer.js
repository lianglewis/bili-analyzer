/**
 * note-viewer.js — 独立笔记渲染器（供 WKWebView 使用）
 * 从 popup.js 抽出纯渲染逻辑，剥离 chrome.* API
 * 入口：window.renderNote(jsonString)
 */

const $ = (sel) => document.querySelector(sel);

let currentResult = null;
let currentAudio = null;
let renderedCards = {};

// ── 主入口 ──────────────────────────────────────────

window.renderNote = function (jsonString) {
  const result = typeof jsonString === "string" ? JSON.parse(jsonString) : jsonString;
  currentResult = result;
  renderedCards = {};
  const container = $("#analysis-preview");
  if (container) container.innerHTML = "";
  updateAnalysisView(result);
};

// ── 渐进式渲染 ──────────────────────────────────────

function appendCard(key, title, body, collapsed) {
  if (renderedCards[key]) return;
  renderedCards[key] = true;

  const container = $("#analysis-preview");
  const card = document.createElement("div");
  card.className = "collapsible-card fade-in" + (collapsed ? " collapsed" : "");
  card.dataset.cardKey = key;
  card.innerHTML =
    `<div class="card-header"><span class="card-title">${title}</span>` +
    `<span class="card-tts" data-card-key="${key}" title="播放语音">▶</span>` +
    `<span class="card-arrow">›</span></div>` +
    `<div class="card-body">${body}</div>`;
  container.appendChild(card);
}

function updateAnalysisView(result) {
  const container = $("#analysis-preview");
  const videoUrl = result.video_url || "";

  // 头部
  if (!renderedCards._header && result.video_title) {
    renderedCards._header = true;
    const catMap = { entertainment: "娱乐", tutorial: "教程", knowledge: "知识讲解" };
    const hdr = document.createElement("div");
    hdr.className = "result-header fade-in";
    hdr.innerHTML =
      `<div class="result-title">${esc(result.video_title)}</div>` +
      `<span class="meta-cat">${catMap[result.category] || result.category || ""}</span>`;
    container.appendChild(hdr);
  }

  // 标题解读
  if (result.title_explanation && !renderedCards.title_explain) {
    const hookTitle = result.title_hook || "这个标题在说什么？";
    appendCard("title_explain", esc(hookTitle),
      `<p>${escBr(result.title_explanation)}</p>`, true);
  }

  // 摘要
  if (result.summary && !renderedCards.summary) {
    appendCard("summary", "摘要", `<p>${escBr(result.summary)}</p>`, true);
  }

  // 实用价值
  if (result.practical_values && result.practical_values.length && !renderedCards.pv) {
    let inner = "";
    for (const pv of result.practical_values) {
      inner += `<div class="pv-item">`;
      inner += `<div class="pv-point">${esc(pv.point)}</div>`;
      inner += `<div class="pv-detail">${escBr(pv.detail)}</div>`;
      inner += `</div>`;
    }
    appendCard("pv", "这个视频对你有什么用？", inner, true);
  }

  // 概念脉络
  if (result.concept_flow && !renderedCards.flow) {
    const flowHtml = buildFlowHtml(result.concept_flow, videoUrl);
    if (flowHtml) {
      appendCard("flow", "概念脉络", flowHtml, true);
    }
  }

  // 关键术语
  if (result.term_groups && result.term_groups.length && !renderedCards.terms) {
    appendCard("terms", "关键术语",
      buildTermGroupsHtml(result.term_groups, videoUrl), true);
  }

  // 深度解析
  if (result.qa_sections && result.qa_sections.length && !renderedCards.qa) {
    appendCard("qa", "深度解析",
      buildQaSectionsHtml(result.qa_sections, videoUrl), true);
  }
}

// ── HTML 构建器 ──────────────────────────────────────

function buildFlowHtml(flow, videoUrl) {
  if (typeof flow === "string") {
    return flow ? `<div class="flow-chain">${esc(flow)}</div>` : "";
  }
  if (!Array.isArray(flow) || !flow.length) return "";

  let h = `<div class="flow-tree">`;
  for (const node of flow) {
    const isChild = node.depth > 0;
    const ts = node.timestamp > 0 ? fmtTs(node.timestamp, videoUrl) : "";
    h += `<div class="flow-node${isChild ? " flow-child" : ""}">`;
    h += `<span class="flow-dot"></span>`;
    h += `<span class="flow-label">${esc(node.label)}</span>`;
    if (ts) h += ` <span class="flow-ts">${ts}</span>`;
    h += `</div>`;
  }
  h += `</div>`;
  return h;
}

function buildTermGroupsHtml(groups, videoUrl) {
  let h = "";
  for (const group of groups) {
    h += `<div class="term-group">`;
    h += `<div class="group-name">${esc(group.group_name)}</div>`;
    for (const t of group.terms) {
      h += `<div class="term-item">`;
      h += `<span class="clickable-term" data-term="${esc(t.term)}">${esc(t.term)}</span>`;
      h += ` <span class="term-ts">${fmtTs(t.timestamp, videoUrl)}</span>`;
      h += `<div class="term-explain">${esc(t.explanation)}</div>`;
      h += `</div>`;
    }
    h += `</div>`;
  }
  return h;
}

function buildQaSectionsHtml(sections, videoUrl) {
  let h = "";
  for (let i = 0; i < sections.length; i++) {
    const qa = sections[i];
    h += `<div class="qa-item collapsed">`;
    h += `<div class="qa-header">`;
    h += `<span class="qa-q">${esc(qa.question)}</span>`;
    h += `<span class="qa-meta">${fmtTs(qa.timestamp, videoUrl)}`;
    h += `<span class="qa-tts" data-qa-idx="${i}" title="播放语音">▶</span>`;
    h += `<span class="sub-arrow">›</span></span></div>`;
    h += `<div class="qa-body">`;
    h += `<div class="qa-a">${escBr(qa.answer)}</div>`;
    if (qa.quote) {
      h += `<blockquote class="qa-quote">${esc(qa.quote)}</blockquote>`;
    }
    if (qa.evidence) {
      h += `<div class="qa-evidence">${esc(qa.evidence)}</div>`;
    }
    if (qa.sub_points && qa.sub_points.length) {
      h += `<ul class="qa-points">`;
      for (const pt of qa.sub_points) h += `<li>${esc(pt)}</li>`;
      h += `</ul>`;
    }
    h += `</div></div>`;
  }
  return h;
}

// ── 事件委托 ─────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const preview = $("#analysis-preview");
  if (!preview) return;

  preview.addEventListener("click", (e) => {
    // TTS 播放
    const ttsBtn = e.target.closest(".card-tts");
    if (ttsBtn) {
      e.stopPropagation();
      handleTtsClick(ttsBtn);
      return;
    }

    // 时间戳跳转 → 通过 webkit message handler 通知 Swift
    const tsLink = e.target.closest(".ts-link");
    if (tsLink) {
      e.preventDefault();
      const seconds = parseInt(tsLink.dataset.time);
      if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.jumpToTime) {
        window.webkit.messageHandlers.jumpToTime.postMessage(seconds);
      }
      return;
    }

    // 术语点击 → 打开弹窗
    const termEl = e.target.closest(".clickable-term");
    if (termEl && currentResult && currentResult.term_groups) {
      const name = termEl.dataset.term;
      for (const group of currentResult.term_groups) {
        for (const t of group.terms) {
          if (t.term === name) {
            openTermModal(t.term, t.explanation, t.timestamp);
            return;
          }
        }
      }
      return;
    }

    // QA 子项 TTS
    const qaTts = e.target.closest(".qa-tts");
    if (qaTts) {
      e.stopPropagation();
      const idx = parseInt(qaTts.dataset.qaIdx);
      handleQaTtsClick(qaTts, idx);
      return;
    }

    // Q&A 二级折叠
    const qaHeader = e.target.closest(".qa-header");
    if (qaHeader) {
      qaHeader.parentElement.classList.toggle("collapsed");
      return;
    }

    // 卡片一级折叠
    const cardHeader = e.target.closest(".card-header");
    if (cardHeader) {
      cardHeader.parentElement.classList.toggle("collapsed");
      return;
    }
  });

  // 弹窗关闭
  const modalClose = $("#term-modal-close");
  if (modalClose) {
    modalClose.addEventListener("click", closeTermModal);
  }
  const overlay = $("#term-modal-overlay");
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeTermModal();
    });
  }

  const askBtn = $("#term-ask-btn");
  if (askBtn) {
    askBtn.addEventListener("click", handleTermAsk);
  }
  const askInput = $("#term-ask-input");
  if (askInput) {
    askInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleTermAsk();
    });
  }
});

// ── 术语弹窗 ─────────────────────────────────────────

function openTermModal(term, explanation, timestamp) {
  $("#term-modal-name").textContent = term;
  $("#term-modal-explanation").textContent = explanation;
  $("#term-modal-answer").innerHTML = "";
  $("#term-ask-input").value = "";
  $("#term-modal-overlay").classList.remove("hidden");

  const suggestions = $("#term-modal-suggestions");
  suggestions.innerHTML = "";
  suggestions.classList.remove("hidden");
  const quickQs = [
    `${term}是什么？能用大白话解释一下吗？`,
    `${term}在实际中怎么用？`,
    `${term}和视频里其他概念有什么关系？`,
  ];
  quickQs.forEach((q) => {
    const btn = document.createElement("button");
    btn.className = "suggestion-btn";
    btn.textContent = q;
    btn.addEventListener("click", () => {
      $("#term-ask-input").value = q;
      handleTermAsk();
    });
    suggestions.appendChild(btn);
  });
}

function closeTermModal() {
  $("#term-modal-overlay").classList.add("hidden");
}

let _askResolve = null;

window._onAskResult = function (jsonString) {
  if (_askResolve) _askResolve(jsonString);
  _askResolve = null;
};

async function handleTermAsk() {
  const question = $("#term-ask-input").value.trim();
  if (!question) return;

  const term = $("#term-modal-name").textContent;
  const explanation = $("#term-modal-explanation").textContent;
  const answerEl = $("#term-modal-answer");

  let timestamp = 0;
  if (currentResult && currentResult.term_groups) {
    for (const group of currentResult.term_groups) {
      for (const t of group.terms) {
        if (t.term === term) {
          timestamp = t.timestamp;
          break;
        }
      }
    }
  }

  answerEl.innerHTML = '<div class="asking">思考中...</div>';
  const askBtn = $("#term-ask-btn");
  if (askBtn) askBtn.disabled = true;
  $("#term-modal-suggestions").classList.add("hidden");

  try {
    const payload = JSON.stringify({
      bvid: currentResult.bvid,
      term, explanation, timestamp, question,
    });
    let data;
    const handler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.termAsk;
    if (handler) {
      const result = await new Promise((resolve) => {
        _askResolve = resolve;
        handler.postMessage(payload);
      });
      data = JSON.parse(result);
    } else {
      const resp = await fetch("http://127.0.0.1:8765/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      });
      data = await resp.json();
    }
    if (askBtn) askBtn.disabled = false;
    if (data && data.answer) {
      answerEl.innerHTML = markdownToHtml(data.answer);
    } else {
      answerEl.innerHTML = '<div class="ask-error">回答失败，请重试</div>';
    }
  } catch {
    if (askBtn) askBtn.disabled = false;
    answerEl.innerHTML = '<div class="ask-error">网络错误，请检查后端是否运行</div>';
  }
}

// ── TTS 播放 ──────────────────────────────────────────

function getCardText(key) {
  const r = currentResult;
  if (!r) return "";
  if (key === "title_explain") return (r.title_hook || "") + "\n" + (r.title_explanation || "");
  if (key === "summary") return r.summary || "";
  if (key === "pv" && r.practical_values) {
    return r.practical_values.map((pv) => pv.point + "：" + pv.detail).join("\n");
  }
  if (key === "flow" && r.concept_flow) {
    if (typeof r.concept_flow === "string") return r.concept_flow;
    if (Array.isArray(r.concept_flow)) return r.concept_flow.map((n) => n.label).join("，");
  }
  if (key === "terms" && r.term_groups) {
    return r.term_groups.map((g) =>
      g.group_name + "：" + g.terms.map((t) => t.term + "，" + t.explanation).join("；")
    ).join("\n");
  }
  if (key === "qa" && r.qa_sections) {
    return r.qa_sections.map((qa) => "问：" + qa.question + "\n答：" + qa.answer).join("\n");
  }
  return "";
}

function stopCurrentAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  document.querySelectorAll(".card-tts, .qa-tts").forEach((b) => (b.textContent = "\u25B6"));
}

let _ttsResolve = null;

window._onTtsResult = function (base64Audio) {
  if (_ttsResolve) _ttsResolve(base64Audio);
  _ttsResolve = null;
};

async function playTts(btn, text) {
  if (!text) return;
  if (currentAudio && btn.textContent === "\u23F9") {
    stopCurrentAudio();
    return;
  }
  stopCurrentAudio();
  btn.textContent = "\u23F3";
  try {
    const handler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.playTTS;
    let audioUrl;
    if (handler) {
      const b64 = await new Promise((resolve) => {
        _ttsResolve = resolve;
        handler.postMessage(text);
      });
      if (!b64) throw new Error("TTS failed");
      audioUrl = "data:audio/mp3;base64," + b64;
    } else {
      const resp = await fetch("http://127.0.0.1:8765/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!resp.ok) throw new Error("TTS failed");
      const blob = await resp.blob();
      audioUrl = URL.createObjectURL(blob);
    }
    const audio = new Audio(audioUrl);
    audio.addEventListener("ended", () => { btn.textContent = "\u25B6"; currentAudio = null; });
    audio.addEventListener("error", () => { btn.textContent = "\u25B6"; currentAudio = null; });
    currentAudio = audio;
    btn.textContent = "\u23F9";
    await audio.play();
  } catch {
    btn.textContent = "\u25B6";
    currentAudio = null;
  }
}

function handleQaTtsClick(btn, idx) {
  if (!currentResult || !currentResult.qa_sections) return;
  const qa = currentResult.qa_sections[idx];
  if (!qa) return;
  playTts(btn, "问：" + qa.question + "\n答：" + qa.answer);
}

function handleTtsClick(btn) {
  playTts(btn, getCardText(btn.dataset.cardKey));
}

// ── 渲染辅助 ─────────────────────────────────────────

function esc(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escBr(str) {
  return esc(str).replace(/\n/g, "<br>");
}

function fmtTs(seconds, videoUrl) {
  const t = Math.round(seconds);
  const totalMm = Math.floor(t / 60);
  const ss = t % 60;
  const hh = Math.floor(totalMm / 60);
  const mm = totalMm % 60;
  const display = hh
    ? `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return `<a class="ts-link" data-time="${t}" href="${esc(videoUrl)}?t=${t}">${display}</a>`;
}

function markdownToHtml(md) {
  return md
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^# (.+)$/gm, "<h2>$1</h2>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" style="color:#00a1d6">$1</a>')
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "<br><br>")
    .replace(/\n/g, "<br>");
}
