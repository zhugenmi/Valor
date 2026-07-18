# Valor Python Backend

Personal professional financial assistant - Python backend.

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Configure environment
cp .env.example .env
# Edit .env to set VALOR_OPENAI_API_KEY or other LLM credentials

# Run CLI
uv run python -m valor.cli.main --ticker 600519
```

## Environment Variables

See `.env.example` for all configuration options. Key variables:

- `VALOR_LLM_PROVIDER`: LLM provider priority (`openai_compat`, `gemini`, `ollama`)
- `VALOR_OPENAI_API_KEY` / `VALOR_OPENAI_BASE_URL` / `VALOR_OPENAI_MODEL`: OpenAI-compatible config
- `TUSHARE_TOKEN`: Tushare data source (optional, for fields AkShare lacks)
- `VALOR_CACHE_DIR`: SQLite cache directory (default `.cache`)

