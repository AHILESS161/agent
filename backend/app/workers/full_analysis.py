"""CLI отдельного worker-а полного анализа.

Запуск из каталога backend::

    python -m app.workers.full_analysis
"""

from __future__ import annotations

import asyncio
import signal

from app.api.dependencies import close_llm_provider
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.database.session import check_schema, close_db
from app.services.full_analysis_jobs import FullAnalysisWorker

logger = get_logger(__name__)


async def main() -> None:
    configure_logging(settings.LOG_LEVEL)
    schema_ok, schema_error = await check_schema()
    if not schema_ok:
        raise RuntimeError(schema_error or "Схема БД не готова")

    worker = FullAnalysisWorker()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        asyncio.create_task(worker.stop())

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            # Proactor loop Windows не поддерживает add_signal_handler, но
            # обычный обработчик SIGINT может безопасно разбудить event loop.
            signal.signal(
                sig,
                lambda _signum, _frame: loop.call_soon_threadsafe(request_stop),
            )

    try:
        await worker.run()
    finally:
        await close_llm_provider()
        await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker остановлен пользователем")
