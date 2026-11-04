import asyncio
import queue
import threading
from collections.abc import Iterator


def stream_in_one_thread(source: Iterator[str]):
    """Iterate a sync generator on one thread.

    Starlette's default threadpool may call next() from a different thread
    each time. A PostgreSQL connection must stay on the thread that opened it,
    so the export cursor lives entirely inside this worker.
    """
    chunks: queue.Queue = queue.Queue(maxsize=4)
    sentinel = object()
    cancel = threading.Event()

    def enqueue(chunk: str) -> bool:
        while not cancel.is_set():
            try:
                chunks.put(chunk, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def worker() -> None:
        try:
            for chunk in source:
                if not enqueue(chunk):
                    break
        except Exception as exc:
            chunks.put(exc)
        finally:
            chunks.put(sentinel)

    thread = threading.Thread(target=worker, name="certificate-export", daemon=True)
    thread.start()

    async def iterate():
        try:
            while True:
                item = await asyncio.to_thread(chunks.get)
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            cancel.set()
            await asyncio.to_thread(thread.join, 30)

    return iterate()
