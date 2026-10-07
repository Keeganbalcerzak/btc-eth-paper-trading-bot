from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from threading import Thread

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from bot.config import SUPPORTED_SYMBOLS, get_settings
from bot.factory import build_bot
from bot.storage import InMemoryState


def create_app(state: InMemoryState | None = None) -> FastAPI:
    settings = get_settings()
    store = state or InMemoryState()
    worker_thread: Thread | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal worker_thread
        trading_bot = None
        if settings.bot_autostart:
            trading_bot = build_bot(state=store, settings=settings)
            worker_thread = Thread(target=trading_bot.run_forever, daemon=True)
            worker_thread.start()
        yield
        if trading_bot is not None:
            trading_bot.stop()
        if worker_thread is not None:
            worker_thread.join(timeout=5)

    app = FastAPI(title="BTC/ETH Paper Bot", version="0.1.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return """
        <!doctype html>
        <html>
          <head>
            <title>BTC/ETH Paper Bot</title>
            <style>
              body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 980px; }
              code, pre { background: #f5f5f5; padding: 0.2rem 0.35rem; border-radius: 4px; }
              .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
              .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; }
            </style>
          </head>
          <body>
            <h1>BTC/ETH Paper Bot</h1>
            <p>Paper-only deterministic bot. Live-money execution is disabled in v1.</p>
            <div class="grid">
              <div class="card"><strong>Health</strong><br><code>GET /health</code></div>
              <div class="card"><strong>Metrics</strong><br><code>GET /metrics</code></div>
              <div class="card"><strong>Signals</strong><br><code>GET /signals</code></div>
              <div class="card"><strong>Decisions</strong><br><code>GET /decisions</code></div>
            </div>
          </body>
        </html>
        """

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "paper_trading": settings.alpaca_paper,
            "symbols": SUPPORTED_SYMBOLS,
            "autostart": settings.bot_autostart,
            "time": datetime.now(UTC),
        }

    @app.get("/metrics")
    def metrics() -> dict[str, object]:
        return store.snapshot()["metrics"]

    @app.get("/signals")
    def signals() -> dict[str, object]:
        return store.snapshot()["signals"]

    @app.get("/positions")
    def positions() -> dict[str, object]:
        return store.snapshot()["positions"]

    @app.get("/decisions")
    def decisions() -> list[object]:
        return store.snapshot()["decisions"]

    app.state.store = store
    return app
