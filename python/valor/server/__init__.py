"""FastAPI server for Valor analysis workflow."""

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from valor.server.main import app as _app

        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
