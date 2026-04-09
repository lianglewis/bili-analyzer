/**
 * content.js — 注入 B 站视频页面
 * 职责：提取视频元信息 + 控制播放器跳转
 */

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getVideoInfo") {
    sendResponse(extractVideoInfo());
  }
  if (request.action === "jumpToTime") {
    jumpToTime(request.time);
    sendResponse({ ok: true });
  }
  return true;
});

function extractVideoInfo() {
  // 从 URL 提取 BV 号
  const match = window.location.pathname.match(/\/video\/(BV[\w]+)/);
  const bvid = match ? match[1] : null;

  // 标题：从 DOM 获取
  let title = "";
  const titleEl = document.querySelector("h1.video-title");
  if (titleEl) {
    title = titleEl.textContent.trim();
  } else {
    title = document.title.replace(/_哔哩哔哩_bilibili.*/, "").trim();
  }

  return {
    bvid,
    title,
    url: window.location.href.split("?")[0], // 去掉查询参数
  };
}

function jumpToTime(seconds) {
  const video = document.querySelector("video");
  if (video) {
    video.currentTime = seconds;
    video.play();
  }
}
