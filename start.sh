#!/usr/bin/env bash
# Valor 一键启动脚本
# 启动后端 FastAPI + 前端 Vite 开发服务器
set -euo pipefail

VALOR_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_DIR="$VALOR_DIR/python"
FRONTEND_DIR="$VALOR_DIR/frontend"

# ANSI colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step()  { echo -e "${CYAN}[STEP]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── 1. 环境检查 ────────────────────────────────────────────

check_prereqs() {
    local ok=true

    if ! command -v uv &>/dev/null; then
        log_error "未找到 uv — 请先安装: https://docs.astral.sh/uv/"
        ok=false
    else
        log_info "uv: $(uv --version)"
    fi

    if ! command -v bun &>/dev/null; then
        log_error "未找到 bun — 请先安装: https://bun.sh/"
        ok=false
    else
        log_info "bun: $(bun --version)"
    fi

    if ! command -v python3 &>/dev/null; then
        log_error "未找到 python3"
        ok=false
    fi

    $ok || exit 1
}

# ─── 2. 依赖安装 ────────────────────────────────────────────

install_deps() {
    log_step "安装后端依赖 (uv sync)..."
    uv sync --extra dev --directory "$PYTHON_DIR"

    log_step "安装前端依赖 (bun install)..."
    bun install --cwd "$FRONTEND_DIR"
}

# ─── 3. 环境文件检查 ────────────────────────────────────────

check_env() {
    if [ ! -f "$PYTHON_DIR/.env" ]; then
        if [ -f "$PYTHON_DIR/.env.example" ]; then
            cp "$PYTHON_DIR/.env.example" "$PYTHON_DIR/.env"
            log_warn "已从 .env.example 生成 .env，请编辑 $PYTHON_DIR/.env 填入 LLM 密钥"
        else
            log_warn "未找到 .env 文件，API 调用可能失败"
        fi
    fi
}

# ─── 4. 启动 ────────────────────────────────────────────────

BACKEND_PID=""
cleanup() {
    echo ""
    log_info "正在关闭服务..."
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null && wait "$BACKEND_PID" 2>/dev/null
    log_info "已停止"
}
trap cleanup EXIT INT TERM

start_backend() {
    log_step "启动后端 (uvicorn :8000)..."
    cd "$PYTHON_DIR"
    uv run uvicorn valor.server.main:app --reload --port 8000 --host 127.0.0.1 &
    BACKEND_PID=$!
    cd "$VALOR_DIR"
    # 等待后端就绪
    for i in $(seq 1 15); do
        if curl -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
            log_info "后端已就绪 http://127.0.0.1:8000"
            break
        fi
        if [ "$i" -eq 15 ]; then
            log_warn "后端启动超时，请检查日志"
        fi
        sleep 1
    done
}

start_frontend() {
    log_step "启动前端 (bun dev :1420)..."
    cd "$FRONTEND_DIR"
    bun dev
}

# ─── 5. Main ────────────────────────────────────────────────

main() {
    echo -e "${BOLD}╔══════════════════════════════╗${NC}"
    echo -e "${BOLD}║       Valor 启动脚本         ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════╝${NC}"
    echo ""

    case "${1:-all}" in
        backend)
            check_prereqs
            install_deps
            check_env
            start_backend
            # 保持后台进程运行
            wait
            ;;
        frontend)
            check_prereqs
            install_deps
            start_frontend
            ;;
        install)
            check_prereqs
            install_deps
            check_env
            log_info "依赖安装完成"
            ;;
        all|*)
            check_prereqs
            check_env
            install_deps
            start_backend
            start_frontend
            ;;
    esac
}

main "$@"
