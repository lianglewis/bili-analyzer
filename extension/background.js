/**
 * background.js — Service Worker
 * 职责：中转 popup/content ↔ Python 后端的通信
 */

const BACKEND = "http://127.0.0.1:8765";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  handleMessage(request).then(sendResponse);
  return true; // 保持 sendResponse 异步可用
});

async function handleMessage(request) {
  switch (request.action) {
    case "checkBackend":
      return checkBackend();
    case "startAnalysis":
      return startAnalysis(request.data);
    case "checkTask":
      return checkTask(request.taskId);
    case "getSessdata":
      return getSessdata();
    case "jumpToTime":
      return jumpToTime(request.time);
    case "askTerm":
      return askTerm(request.data);
    default:
      return { error: `未知 action: ${request.action}` };
  }
}

async function getSessdata() {
  try {
    // 用 getAll + domain 过滤，比 get() 更可靠
    // B站 Cookie 设在 .bilibili.com 域上
    const cookies = await chrome.cookies.getAll({
      domain: "bilibili.com",
      name: "SESSDATA",
    });
    if (cookies.length > 0) {
      return { sessdata: cookies[0].value };
    }
    return { sessdata: null };
  } catch (e) {
    console.error("获取 SESSDATA 失败:", e);
    return { sessdata: null };
  }
}

async function checkBackend() {
  try {
    const resp = await fetch(`${BACKEND}/api/health`);
    return { ok: resp.ok };
  } catch {
    return { ok: false };
  }
}

async function startAnalysis(data) {
  try {
    const resp = await fetch(`${BACKEND}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return await resp.json();
  } catch {
    return {
      error: "后端未启动。请先运行: cd backend && python app.py",
    };
  }
}

async function checkTask(taskId) {
  try {
    const resp = await fetch(`${BACKEND}/api/task/${taskId}`);
    return await resp.json();
  } catch {
    return { error: "无法连接后端" };
  }
}

async function askTerm(data) {
  try {
    const resp = await fetch(`${BACKEND}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return await resp.json();
  } catch {
    return { error: "无法连接后端" };
  }
}

async function jumpToTime(time) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      await chrome.tabs.sendMessage(tab.id, { action: "jumpToTime", time });
    }
    return { ok: true };
  } catch {
    return { ok: false };
  }
}
