"""本地开发 Agent HTTP 服务入口（§1.2 / §6.3）。

提供 HTTP 接口直接调用 LangGraph 规划图，输出 WorkOrder。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from eduforge.agent.bootstrap import build_planner
from eduforge.agent.policy import Rejected
from eduforge.domain.contracts import ApiErrorResponse, PlannerRequest, WorkOrder

app = FastAPI(title="EduForge Local Agent")
_planner = None


def get_planner():
    global _planner
    if _planner is None:
        _planner = build_planner()
    return _planner


def set_planner(custom_planner):
    global _planner
    _planner = custom_planner


@app.post("/plan", response_model=WorkOrder, responses={400: {"model": ApiErrorResponse}})
async def plan_endpoint(request: PlannerRequest):
    p = get_planner()
    try:
        result = await p.ainvoke({"request": request})
        return result["work_order"]
    except Rejected as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
