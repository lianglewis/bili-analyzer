"""FastAPI 入口 — 4 个端点，多一个都是过度设计"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from models import AnalyzeRequest
from pipeline import get_task, run_pipeline

app = FastAPI(title="Bili Analyzer")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
