"""Valor FastAPI application."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from valor.adapters.data.akshare_adapter import AkShareAdapter
from valor.adapters.data.baostock_adapter import BaoStockAdapter
from valor.adapters.data.router import DataRouter
from valor.server.routes.analysis import router as analysis_router
from valor.server.routes.auth import router as auth_router
from valor.server.routes.health import router as health_router
from valor.server.routes.models import router as models_router
from valor.server.routes.stock import router as stock_router
from valor.server.routes.stubs import router as stubs_router
from valor.server.routes.stream import router as stream_router
from valor.server.routes.system import router as system_router
from valor.server.routes.tasks import router as tasks_router
from valor.server.routes.user_profile import router as user_profile_router
from valor.server.routes.portfolio import router as portfolio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - load env, init DB + DataRouter on startup."""
    load_dotenv()
    from valor.server import db

    db.init_db()
    primary = AkShareAdapter()
    sources = {"baostock": BaoStockAdapter()}
    app.state.data_router = DataRouter(primary=primary, sources=sources)
    yield


app = FastAPI(
    title="Valor API",
    version="0.1.0",
    description="Personal financial assistant backend",
    lifespan=lifespan,
)

# CORS - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes - health at both root and /api/v1 for frontend compatibility
app.include_router(health_router)
app.include_router(health_router, prefix="/api/v1")
app.include_router(analysis_router)
app.include_router(stubs_router)
app.include_router(stream_router)
app.include_router(auth_router)
app.include_router(system_router)
app.include_router(tasks_router)
app.include_router(stock_router)
app.include_router(models_router)
app.include_router(user_profile_router)
app.include_router(portfolio_router)
