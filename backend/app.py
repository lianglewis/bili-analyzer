"""FastAPI 入口 — 核心端点 + 笔记管理"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import config
from db import init_db, list_notes, get_note, delete_note
from models import AnalyzeRequest, AskRequest
from pipeline import get_task, get_transcript, run_pipeline

app = FastAPI(title="Bili Analyzer")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome 扩展的 origin 格式不固定，用 * 即可（仅 localhost）
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/api/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    task_id = await run_pipeline(req)
    return {"task_id": task_id, "status": "pending"}


@app.get("/api/task/{task_id}")
async def task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"error": "task not found"}
    return task.model_dump()


@app.post("/api/ask")
async def ask_term(req: AskRequest):
    segments = get_transcript(req.bvid)
    if not segments:
        return {"error": "该视频的转录数据已过期，请重新分析"}

    # 从缓存的任务结果中获取视频标题
    title = req.bvid
    for task in _all_tasks():
        if task.result and task.result.bvid == req.bvid:
            title = task.result.video_title
            break

    from analyzer import ask_about_term
    answer = await ask_about_term(
        title=title,
        term=req.term,
        explanation=req.explanation,
        timestamp=req.timestamp,
        question=req.question,
        segments=segments,
    )
    return {"answer": answer}


@app.post("/api/tts")
async def text_to_speech(req: dict):
    text = req.get("text", "").strip()
    if not text:
        return {"error": "text is empty"}
    from tts import synthesize
    audio = await synthesize(text)
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/api/notes")
async def notes_list():
    return list_notes()


@app.get("/api/notes/{bvid}")
async def notes_detail(bvid: str):
    note = get_note(bvid)
    if not note:
        return {"error": "note not found"}
    return note


@app.delete("/api/notes/{bvid}")
async def notes_delete(bvid: str):
    ok = delete_note(bvid)
    return {"deleted": ok}


def _all_tasks():
    """遍历所有任务（辅助函数）"""
    from pipeline import _tasks
    return _tasks.values()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
