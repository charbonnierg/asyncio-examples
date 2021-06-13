from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from functools import wraps
from queue import Empty, Queue
from typing import Awaitable, Callable, Coroutine, Generator

import uvloop

from time import perf_counter
from contextlib import contextmanager


@contextmanager
def Timer() -> Generator[Callable[[], float], None, None]:
    start = perf_counter()
    yield lambda: (perf_counter() - start) * 1000


class AsyncThread(threading.Thread):
    def __init__(self):
        """Create a new instance of asyncio thread."""
        super().__init__()
        uvloop.install()
        self._loop = asyncio.new_event_loop()
        self._tasks = []

    def task(self, coro_function: Callable[[], Awaitable[None]]):
        """Create a new asyncio task to run in thread."""
        # A decorator to catch asyncio.CancelledError
        @wraps(coro_function)
        async def wrapper():
            try:
                await coro_function()
            except asyncio.CancelledError:
                print(f"Task cancelled: {coro_function}")

        # Append the coroutine function to the list of tasks
        self._tasks.append(wrapper)
        # Return the untouched function
        return coro_function

    async def arun(self):
        """Asynchronous run wrapper."""
        for task in self._tasks:
            # Submit coroutine to event loop
            asyncio.create_task(task())

    def run(self):
        """Synchronously run thread."""
        # First submit all tasks
        self._loop.run_until_complete(self.arun())
        # Then run loop forever
        # This function exits gracefully when loop is stopped
        self._loop.run_forever()

    def submit(self, coro: Coroutine) -> Future:
        """Submit a coroutine to thread."""
        # Submit a coroutine to event loop from another thread.
        # If this function is called from the same thread where event loop is running
        # Process will be blocked and hang forever
        return asyncio.run_coroutine_threadsafe(coro, loop=self._loop)

    def stop(self):
        """Stop all tasks, then event loop.

        Note that thread is not stopped with this method.
        """
        # Iterate over all running tasks
        for task in asyncio.all_tasks(loop=self._loop):
            # Cancel the task
            task.cancel()
        # Stop the event loop
        self._loop.stop()

    def join(self):
        """Stop thread."""
        self.stop()
        super().join()

    def __enter__(self):
        """Context manager to start/stop thread automatically."""
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        """Context manager to start/stop thread automatically."""
        self.join()


async def foo():
    return 1


t = AsyncThread()

q1: Queue[int] = Queue()
q1_out: Queue[int] = Queue()
q2: Queue[int] = Queue()
q2_out: Queue[int] = Queue()


@t.task
async def process1():
    while True:
        try:
            v = q1.get_nowait()
        except Empty:
            await asyncio.sleep(1e-4)
            continue
        else:
            q1_out.put(v)


@t.task
async def process2():
    while True:
        try:
            v = q2.get_nowait()
        except Empty:
            await asyncio.sleep(1e-4)
            continue
        else:
            q2_out.put(v)


t.start()


def measure_perf():
    with Timer() as timer:
        # Submit coroutine and get future
        future = t.submit(foo())
        # Get result from future
        result = future.result()
        print(f"Got result: {result}. Took {timer():.5f} ms")

    with Timer() as timer:
        q1.put(1)
        result = q1_out.get()
        print(f"Got processed item: {result}. Took {timer():.5f} ms")

    with Timer() as timer:
        q2.put(2)
        result = q2_out.get()
        print(f"Got processed item: {result}. Took {timer():.5f} ms")
