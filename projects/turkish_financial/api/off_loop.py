"""Run long collection pipelines off the server's event loop.

The API runs one uvicorn worker. Several scrapers (yt_dlp, youtube-transcript-api,
plain `requests`) do blocking I/O inside `async def` code, so awaiting them on the
main loop freezes every other request, /health included, until the run ends —
the readiness probe then fails and the pod drops out of the Service.

`run_off_loop` runs the pipeline on a fresh event loop in a worker thread: its
blocking calls stall only that thread, and the caller still gets the result.
"""
import asyncio
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar("T")


async def run_off_loop(make_coro: Callable[[], Coroutine[Any, Any, T]]) -> T:
    return await asyncio.to_thread(lambda: asyncio.run(make_coro()))
