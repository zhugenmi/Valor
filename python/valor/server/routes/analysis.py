"""Analysis workflow endpoints — trigger and poll stock analysis runs."""

import uuid
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from valor.agents.workflow import run_analysis
from valor.server.envelope import ok

router = APIRouter(prefix="/api/v1/analysis", tags=["Analysis"])

# ---------------------------------------------------------------------------
# In-memory run state (single-process only; lost on restart)
# ---------------------------------------------------------------------------
_executor = ThreadPoolExecutor(max_workers=3)
_runs: dict[str, dict] = {}


class RunStatus(BaseModel):
    run_id: str
    ticker: str
    status: str  # running | completed | error
    message: str
    submitted_at: datetime
    completed_at: Optional[datetime] = None


class AnalysisRequest(BaseModel):
    ticker: str = Field(..., description="A-share ticker, e.g. 600519")
    show_reasoning: bool = True
    num_of_news: int = Field(default=5, ge=1, le=100)
    initial_cash: float = 100000.0
    initial_stock: int = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/start")
async def start_analysis(req: AnalysisRequest):
    """Kick off a stock analysis in the background thread pool."""
    run_id = str(uuid.uuid4())
    _runs[run_id] = {
        "run_id": run_id,
        "ticker": req.ticker,
        "status": "running",
        "message": "分析任务已启动",
        "submitted_at": datetime.now(UTC),
        "completed_at": None,
    }

    def _run():
        try:
            result = run_analysis(
                ticker=req.ticker,
                start_date=req.start_date,
                end_date=req.end_date,
                show_reasoning=req.show_reasoning,
                num_of_news=req.num_of_news,
                portfolio={"cash": req.initial_cash, "stock": req.initial_stock},
            )
            _runs[run_id].update(
                status="completed",
                message="分析完成",
                completed_at=datetime.now(UTC),
                result=result,
            )
        except Exception as exc:
            _runs[run_id].update(
                status="error",
                message=str(exc),
                completed_at=datetime.now(UTC),
                error=str(exc),
            )

    _executor.submit(_run)
    return ok(RunStatus(**_runs[run_id]).model_dump(mode="json"))


@router.get("/{run_id}/status")
async def get_status(run_id: str):
    """Poll analysis task status."""
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return ok({"run_id": run_id, "status": run["status"], "message": run["message"]})


@router.get("/{run_id}/result")
async def get_result(run_id: str):
    """Retrieve completed analysis result."""
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    if run["status"] == "running":
        raise HTTPException(400, "分析尚未完成")
    if run["status"] == "error":
        raise HTTPException(500, run.get("error", "未知错误"))
    return ok(run.get("result"))
