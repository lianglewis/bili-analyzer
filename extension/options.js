/**
 * options.js — 设置页
 */

document.addEventListener("DOMContentLoaded", async () => {
  const settings = await chrome.storage.sync.get([
    "claudeApiKey",
    "transcriptSource",
    "bilibiliSessdata",
  ]);

  if (settings.claudeApiKey) {
    document.getElementById("api-key").value = settings.claudeApiKey;
  }
  if (settings.transcriptSource) {
    document.getElementById("default-source").value = settings.transcriptSource;
  }
  if (settings.bilibiliSessdata) {
    document.getElementById("sessdata").value = settings.bilibiliSessdata;
  }

  document.getElementById("btn-save").addEventListener("click", async () => {
    await chrome.storage.sync.set({
      claudeApiKey: document.getElementById("api-key").value.trim(),
      transcriptSource: document.getElementById("default-source").value,
      bilibiliSessdata: document.getElementById("sessdata").value.trim(),
    });
    document.getElementById("msg").textContent = "已保存";
    setTimeout(() => {
      document.getElementById("msg").textContent = "";
    }, 2000);
  });
});
