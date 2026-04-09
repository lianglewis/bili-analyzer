/**
 * popup.js — 主控制器
 * 结果持久化到 chrome.storage.local，popup 关闭重开不丢失
 */

const $ = (sel) => document.querySelector(sel);

let pollTimer = null;
let currentMarkdown = "";
let currentTitle = "";
let currentBvid = "";

// ── 初始化 ───────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  // 恢复用户设置
  const settings = await chrome.storage.sync.get(["transcriptSource"]);
  if (settings.transcriptSource) {
    $("#source-select").value = settings.transcriptSource;
  }

  // 检查后端
  const backendOk = await checkBackend();
  if (!backendOk) {
    showStatus("err", "后端未启动 — 请运行 python app.py");
  }

  // 检查当前页面
  const videoInfo = await getVideoInfo();
  if (videoInfo && videoInfo.bvid) {
    currentBvid = videoInfo.bvid;
    $("#video-title").textContent = videoInfo.title || videoInfo.bvid;
    $("#btn-analyze").disabled = !backendOk;

    // 尝试恢复该视频的已有结果
    const saved = await chrome.storage.local.get([
      "currentTaskId",
      `result_${currentBvid}`,
    ]);

    if (saved[`result_${currentBvid}`]) {
      // 有缓存结果，直接展示
      showResult(saved[`result_${currentBvid}`]);
    } else if (saved.currentTaskId) {
      // 有进行中的任务，继续轮询
      startPolling(saved.currentTaskId);
    }
  } else {
    $("#video-title").textContent = "请在 B 站视频页面使用此插件";
    $("#btn-analyze").disabled = true;
  }

  // 绑定事件
  $("#btn-analyze").addEventListener("click", handleAnalyze);
  $("#btn-retry").addEventListener("click", handleRetry);
  $("#btn-copy").addEventListener("click", handleCopy);
  $("#btn-download").addEventListener("click", handleDownload);
  $("#btn-reanalyze").addEventListener("click", handleReanalyze);

  // 保存转录方式选择
  $("#source-select").addEventListener("change", (e) => {
    chrome.storage.sync.set({ transcriptSource: e.target.value });
  });
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

  // 自动获取 B 站登录 Cookie
  const { sessdata } = await sendBg({ action: "getSessdata" }) || {};

  const data = {
    url: videoInfo.url,
    transcript_source: $("#source-select").value,
    bilibili_sessdata: sessdata || null,
  };

  showView("progress");
  updateProgress(5, sessdata ? "已获取登录信息，提交分析..." : "未登录B站，提交分析...");

  const resp = await sendBg({
    action: "startAnalysis",
    data,
  });

  if (!resp || resp.error) {
    showError(resp ? resp.error : "扩展通信失败，请刷新页面后重试");
    return;
  }

  await chrome.storage.local.set({ currentTaskId: resp.task_id });
  startPolling(resp.task_id);
}

function startPolling(taskId) {
  showView("progress");
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    const task = await sendBg({
      action: "checkTask",
      taskId,
    });

    if (!task || task.error) {
      return;
    }

    updateProgress(task.progress, task.message);

    // 有中间结果就实时渲染预览
    if (task.result && task.status !== "done") {
      showPartialResult(task.result, task.message);
    }

    if (task.status === "done") {
      clearInterval(pollTimer);
      await chrome.storage.local.remove("currentTaskId");
      if (currentBvid) {
        await chrome.storage.local.set({
          [`result_${currentBvid}`]: task.result,
        });
      }
      showResult(task.result);
    } else if (task.status === "error") {
      clearInterval(pollTimer);
      await chrome.storage.local.remove("currentTaskId");
      // 即使出错，如果有中间结果也保留
      if (task.result) {
        if (currentBvid) {
          await chrome.storage.local.set({
            [`result_${currentBvid}`]: task.result,
          });
        }
        showResult(task.result);
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
  // 清除缓存结果，重新分析
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

// ── 辅助函数 ─────────────────────────────────────────

async function sendBg(msg) {
  // 统一包装，防止 Service Worker 未就绪时炸
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
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (!tab || !tab.url || !tab.url.includes("bilibili.com/video/")) {
      return null;
    }
    return await chrome.tabs.sendMessage(tab.id, { action: "getVideoInfo" });
  } catch {
    return null;
  }
}

function showView(name) {
  ["main", "progress", "error", "result"].forEach((v) => {
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

function showPartialResult(result, statusMsg) {
  // 在进度条下方显示中间结果预览
  const container = $("#partial-preview");
  if (!container) return;
  container.classList.remove("hidden");
  container.innerHTML =
    `<div class="partial-status">${statusMsg}</div>` +
    markdownToHtml(result.markdown);
}

function showResult(result) {
  showView("result");
  currentMarkdown = result.markdown;
  currentTitle = result.video_title;

  const preview = $("#result-preview");
  preview.innerHTML = markdownToHtml(result.markdown);

  // 时间戳链接 → 跳转视频位置
  preview.querySelectorAll("a").forEach((a) => {
    const href = a.getAttribute("href") || "";
    const tMatch = href.match(/[?&]t=(\d+)/);
    if (tMatch && href.includes("bilibili.com")) {
      a.style.cursor = "pointer";
      a.addEventListener("click", (e) => {
        e.preventDefault();
        // 通过 background 跳转，不依赖 popup 保持打开
        sendBg({
          action: "jumpToTime",
          time: parseInt(tMatch[1]),
        });
      });
    }
  });
}

function markdownToHtml(md) {
  return md
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^# (.+)$/gm, "<h2>$1</h2>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/!\[(.+?)\]\((.+?)\)/g, '<img src="$2" alt="$1" style="max-width:100%;border-radius:4px;margin:4px 0">')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" style="color:#00a1d6">$1</a>')
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "<br><br>")
    .replace(/\n/g, "<br>");
}
