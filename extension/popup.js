/**
 * popup.js — 主控制器
 * 渐进式卡片渲染：数据就绪时卡片逐个出现（默认折叠 + fade-in）
 * 结果持久化到 chrome.storage.local，popup 关闭重开不丢失
 */

const $ = (sel) => document.querySelector(sel);

let pollTimer = null;
let currentMarkdown = "";
let currentTitle = "";
let currentBvid = "";
let currentResult = null;
let currentAudio = null;

// 跟踪已渲染的卡片，避免重复创建
let renderedCards = {};

// ── 初始化 ───────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  const settings = await chrome.storage.sync.get(["transcriptSource", "whisperModel"]);
  if (settings.transcriptSource) {
    $("#source-select").value = settings.transcriptSource;
  }
  if (settings.whisperModel) {
    $("#model-select").value = settings.whisperModel;
  }
  toggleWhisperModelUI($("#source-select").value);

  const backendOk = await checkBackend();
  if (!backendOk) {
    showStatus("err", "后端未启动 — 请运行 python app.py");
  }

  const videoInfo = await getVideoInfo();
  if (videoInfo && videoInfo.bvid) {
    currentBvid = videoInfo.bvid;
    $("#video-title").textContent = videoInfo.title || videoInfo.bvid;
    $("#btn-analyze").disabled = !backendOk;

    const saved = await chrome.storage.local.get([
      "currentTaskId",
      `result_${currentBvid}`,
    ]);

    if (saved[`result_${currentBvid}`]) {
      showResult(saved[`result_${currentBvid}`]);
    } else if (saved.currentTaskId) {
      startPolling(saved.currentTaskId);
    }
  } else {
    $("#video-title").textContent = "请在 B 站视频页面使用此插件";
    $("#btn-analyze").disabled = true;
  }

  $("#btn-analyze").addEventListener("click", handleAnalyze);
  $("#btn-retry").addEventListener("click", handleRetry);
  $("#btn-copy").addEventListener("click", handleCopy);
  $("#btn-download").addEventListener("click", handleDownload);
  $("#btn-reanalyze").addEventListener("click", handleReanalyze);

  $("#term-modal-close").addEventListener("click", closeTermModal);
  $("#term-modal-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeTermModal();
  });

  $("#term-ask-btn").addEventListener("click", handleTermAsk);
  $("#term-ask-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleTermAsk();
  });

  $("#source-select").addEventListener("change", (e) => {
    chrome.storage.sync.set({ transcriptSource: e.target.value });
    toggleWhisperModelUI(e.target.value);
  });

  $("#model-select").addEventListener("change", (e) => {
    chrome.storage.sync.set({ whisperModel: e.target.value });
  });

  // 事件委托：统一处理 analysis-preview 内的点击
  setupCardContainer();
});

// ── 核心流程 ─────────────────────────────────────────

async function handleAnalyze() {
  const videoInfo = await getVideoInfo();
  if (!videoInfo || !videoInfo.bvid) {
    showError("无法识别视频信息，请刷新 B 站页面后重试");
    return;
  }

  currentTitle = videoInfo.title || videoInfo.bvid;
  currentBvid = videoInfo.bvid;

  const { sessdata } = (await sendBg({ action: "getSessdata" })) || {};

  const source = $("#source-select").value;
  const data = {
    url: videoInfo.url,
    transcript_source: source,
    bilibili_sessdata: sessdata || null,
  };
  if (source === "whisper_local") {
    data.whisper_model = $("#model-select").value;
  }

  showView("analysis");
  resetRenderedCards();
  updateProgress(
    5,
    sessdata ? "已获取登录信息，提交分析..." : "未登录B站，提交分析..."
  );

  const resp = await sendBg({ action: "startAnalysis", data });

  if (!resp || resp.error) {
    showError(resp ? resp.error : "扩展通信失败，请刷新页面后重试");
    return;
  }

  await chrome.storage.local.set({ currentTaskId: resp.task_id });
  startPolling(resp.task_id);
}

function startPolling(taskId) {
  showView("analysis");
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    const task = await sendBg({ action: "checkTask", taskId });
    if (!task || task.error) return;

    updateProgress(task.progress, task.message);

    if (task.result) {
      updateAnalysisView(task.result, task.message, false);
    }

    if (task.status === "done") {
      clearInterval(pollTimer);
      await chrome.storage.local.remove("currentTaskId");
      if (currentBvid) {
        await chrome.storage.local.set({
          [`result_${currentBvid}`]: task.result,
        });
      }
      updateAnalysisView(task.result, "", true);
    } else if (task.status === "error") {
      clearInterval(pollTimer);
      await chrome.storage.local.remove("currentTaskId");
      if (task.result) {
        if (currentBvid) {
          await chrome.storage.local.set({
            [`result_${currentBvid}`]: task.result,
          });
        }
        updateAnalysisView(task.result, "", true);
        showStatus("err", task.message);
      } else {
        showError(task.message);
      }
    }
  }, 2000);
}

function handleRetry() {
  showView("main");
}

async function handleReanalyze() {
  if (currentBvid) {
    await chrome.storage.local.remove(`result_${currentBvid}`);
  }
  showView("main");
}

async function handleCopy() {
  await navigator.clipboard.writeText(currentMarkdown);
  $("#btn-copy").textContent = "已复制 ✓";
  setTimeout(() => {
    $("#btn-copy").textContent = "复制 Markdown";
  }, 2000);
}

function handleDownload() {
  const blob = new Blob([currentMarkdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${currentTitle || "笔记"}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── 渐进式渲染 ──────────────────────────────────────

function resetRenderedCards() {
  renderedCards = {};
  const preview = $("#analysis-preview");
  if (preview) preview.innerHTML = "";
  $("#analysis-progress").classList.remove("hidden");
  $("#analysis-actions").classList.add("hidden");
}

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

function updateAnalysisView(result, msg, isDone) {
  currentResult = result;
  if (result.markdown) currentMarkdown = result.markdown;
  if (result.video_title) currentTitle = result.video_title;

  const container = $("#analysis-preview");
  const videoUrl = result.video_url || "";

  // 头部（只渲染一次）
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

  // 标题解读（~25%）
  if (result.title_explanation && !renderedCards.title_explain) {
    const hookTitle = result.title_hook || "这个标题在说什么？";
    appendCard("title_explain", esc(hookTitle),
      `<p>${escBr(result.title_explanation)}</p>`, true);
  }

  // 摘要（~50%）
  if (result.summary && !renderedCards.summary) {
    appendCard("summary", "摘要", `<p>${escBr(result.summary)}</p>`, true);
  }

  // 实用价值（~50%）
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

  // 概念脉络（~50%）
  if (result.concept_flow && !renderedCards.flow) {
    const flowHtml = buildFlowHtml(result.concept_flow, videoUrl);
    if (flowHtml) {
      appendCard("flow", "概念脉络", flowHtml, true);
    }
  }

  // 关键术语（~50%）
  if (result.term_groups && result.term_groups.length && !renderedCards.terms) {
    appendCard("terms", "关键术语",
      buildTermGroupsHtml(result.term_groups, videoUrl), true);
  }

  // 深度解析（~90%）
  if (result.qa_sections && result.qa_sections.length && !renderedCards.qa) {
    appendCard("qa", "深度解析",
      buildQaSectionsHtml(result.qa_sections, videoUrl), true);
  }

  // 完成：隐藏进度条，显示操作按钮
  if (isDone) {
    $("#analysis-progress").classList.add("hidden");
    $("#analysis-actions").classList.remove("hidden");
  }
}

// 从缓存恢复时使用
async function showResult(result) {
  showView("analysis");
  resetRenderedCards();
  updateAnalysisView(result, "", true);
  await restoreExpandState();
}

function saveExpandState() {
  if (!currentBvid) return;
  const cards = [];
  document.querySelectorAll(".collapsible-card:not(.collapsed)").forEach((card) => {
    if (card.dataset.cardKey) cards.push(card.dataset.cardKey);
  });
  const qa = [];
  document.querySelectorAll(".qa-item:not(.collapsed)").forEach((item, i) => {
    qa.push(i);
  });
  chrome.storage.local.set({ [`expand_${currentBvid}`]: { cards, qa } });
}

async function restoreExpandState() {
  if (!currentBvid) return;
  const saved = await chrome.storage.local.get(`expand_${currentBvid}`);
  const state = saved[`expand_${currentBvid}`];
  if (!state) return;

  // 恢复卡片展开状态
  if (state.cards) {
    for (const key of state.cards) {
      const card = document.querySelector(`.collapsible-card[data-card-key="${key}"]`);
      if (card) card.classList.remove("collapsed");
    }
  }
  // 恢复 QA 子项展开状态
  if (state.qa) {
    const qaItems = document.querySelectorAll(".qa-item");
    for (const idx of state.qa) {
      if (qaItems[idx]) qaItems[idx].classList.remove("collapsed");
    }
  }
}

// ── HTML 构建器 ──────────────────────────────────────

function buildFlowHtml(flow, videoUrl) {
  // 向后兼容：旧缓存中 concept_flow 是字符串
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

function setupCardContainer() {
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

    // 时间戳跳转
    const tsLink = e.target.closest(".ts-link");
    if (tsLink) {
      e.preventDefault();
      sendBg({ action: "jumpToTime", time: parseInt(tsLink.dataset.time) });
      return;
    }

    // 术语点击
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

    // QA 子项 TTS 播放
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
      saveExpandState();
      return;
    }

    // 卡片一级折叠
    const cardHeader = e.target.closest(".card-header");
    if (cardHeader) {
      cardHeader.parentElement.classList.toggle("collapsed");
      saveExpandState();
      return;
    }
  });
}

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
  $("#term-ask-btn").disabled = true;
  $("#term-modal-suggestions").classList.add("hidden");

  const resp = await sendBg({
    action: "askTerm",
    data: { bvid: currentBvid, term, explanation, timestamp, question },
  });

  $("#term-ask-btn").disabled = false;

  if (resp && resp.answer) {
    answerEl.innerHTML = markdownToHtml(resp.answer);
  } else {
    answerEl.innerHTML =
      '<div class="ask-error">回答失败，请重试。转录数据可能已过期，尝试重新分析。</div>';
  }
}

// ── 辅助函数 ─────────────────────────────────────────

async function sendBg(msg) {
  try {
    return await chrome.runtime.sendMessage(msg);
  } catch {
    return null;
  }
}

async function checkBackend() {
  const resp = await sendBg({ action: "checkBackend" });
  return resp && resp.ok;
}

async function getVideoInfo() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || !tab.url.includes("bilibili.com/video/")) return null;
    return await chrome.tabs.sendMessage(tab.id, { action: "getVideoInfo" });
  } catch {
    return null;
  }
}

function showView(name) {
  ["main", "analysis", "error"].forEach((v) => {
    $(`#${v}-view`).classList.toggle("hidden", v !== name);
  });
}

function showStatus(type, text) {
  const bar = $("#status-bar");
  bar.classList.remove("hidden", "ok", "err");
  bar.classList.add(type);
  $("#status-text").textContent = text;
}

function showError(msg) {
  showView("error");
  $("#error-text").textContent = msg;
}

function updateProgress(percent, text) {
  $("#progress-fill").style.width = `${percent}%`;
  $("#progress-text").textContent = text;
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

function toggleWhisperModelUI(source) {
  const group = $("#whisper-model-group");
  if (source === "whisper_local") {
    group.classList.remove("hidden");
  } else {
    group.classList.add("hidden");
  }
}

// ── TTS 播放 ──────────────────────────────────────────

function getCardText(key) {
  const r = currentResult;
  if (!r) return "";

  if (key === "title_explain") {
    return (r.title_hook || "") + "\n" + (r.title_explanation || "");
  }
  if (key === "summary") {
    return r.summary || "";
  }
  if (key === "pv" && r.practical_values) {
    return r.practical_values.map((pv) => pv.point + "：" + pv.detail).join("\n");
  }
  if (key === "flow" && r.concept_flow) {
    if (typeof r.concept_flow === "string") return r.concept_flow;
    if (Array.isArray(r.concept_flow)) {
      return r.concept_flow.map((n) => n.label).join("，");
    }
  }
  if (key === "terms" && r.term_groups) {
    return r.term_groups
      .map((g) =>
        g.group_name +
        "：" +
        g.terms.map((t) => t.term + "，" + t.explanation).join("；")
      )
      .join("\n");
  }
  if (key === "qa" && r.qa_sections) {
    return r.qa_sections
      .map((qa) => "问：" + qa.question + "\n答：" + qa.answer)
      .join("\n");
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

async function playTts(btn, text) {
  if (!text) return;

  // 正在播放时点击 = 停止
  if (currentAudio && btn.textContent === "\u23F9") {
    stopCurrentAudio();
    return;
  }

  stopCurrentAudio();
  btn.textContent = "\u23F3";

  try {
    const resp = await fetch("http://127.0.0.1:8765/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) throw new Error("TTS failed");

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);

    audio.addEventListener("ended", () => {
      btn.textContent = "\u25B6";
      currentAudio = null;
      URL.revokeObjectURL(url);
    });
    audio.addEventListener("error", () => {
      btn.textContent = "\u25B6";
      currentAudio = null;
      URL.revokeObjectURL(url);
    });

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
  const text = "问：" + qa.question + "\n答：" + qa.answer;
  playTts(btn, text);
}

function handleTtsClick(btn) {
  const text = getCardText(btn.dataset.cardKey);
  playTts(btn, text);
}

function markdownToHtml(md) {
  return md
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^# (.+)$/gm, "<h2>$1</h2>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(
      /!\[(.+?)\]\((.+?)\)/g,
      '<img src="$2" alt="$1" style="max-width:100%;border-radius:4px;margin:4px 0">'
    )
    .replace(
      /\[(.+?)\]\((.+?)\)/g,
      '<a href="$2" style="color:#00a1d6">$1</a>'
    )
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "<br><br>")
    .replace(/\n/g, "<br>");
}
