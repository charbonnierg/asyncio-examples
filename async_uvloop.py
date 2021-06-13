from __future__ import annotations

import asyncio
import threading
import warnings
from concurrent.futures import Future
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Awaitable, Callable, Coroutine, Generator, Generic, Iterable, List, Optional, TypeVar

T = TypeVar("T", bound=Any)


class NotReadyError(Exception):
    pass


@contextmanager
def Timer() -> Generator[Callable[[], float], None, None]:
    start = perf_counter()
    yield lambda: (perf_counter() - start) * 1000


class QueueProxy(Generic[T]):
    def __init__(self, **kwargs: Any) -> None:
        self._opts = kwargs
        self.__queue__: Optional[asyncio.Queue[T]] = None

    async def _create(self) -> None:
        self.__queue__ = asyncio.Queue(**self._opts)

    @property
    def _queue(self) -> asyncio.Queue:
        if q := self.__queue__:
            return q
        raise NotReadyError("Queue is not running yet")

    async def get(self) -> T:
        return await self._queue.get()

    def get_nowait(self) -> T:
        return self._queue.get_nowait()

    async def put(self, item: T) -> None:
        return await self._queue.put(item)

    def put_nowait(self, item: T) -> None:
        return self._queue.put_nowait(item)


class AsyncThread(threading.Thread):
    def __init__(self):
        """Create a new instance of asyncio thread."""
        super().__init__()
        self._loop = asyncio.new_event_loop()
        self._queues: List[QueueProxy[Any]] = []
        self._tasks: List[Callable[[], Awaitable[None]]] = []

    def task(self, coro_function: Callable[[], Awaitable[None]]):
        """Create a new asyncio task to run in thread."""
        # Append the coroutine function to the list of tasks
        self._tasks.append(coro_function)
        # Return the untouched function
        return coro_function

    async def _create_tasks(self, *coro_functions: Callable[[], Awaitable[None]]) -> List[asyncio.Task]:
        return [asyncio.create_task(coro()) for coro in coro_functions]

    def create_task(self, coro_function: Callable[[], Awaitable[None]]) -> asyncio.Task:
        """Create a single task to run in the AsyncThread."""
        return self.submit(self._create_tasks(coro_function)).result()[0]

    def create_tasks(self, *coro_functions: Callable[[], Awaitable[None]]) -> List[asyncio.Task]:
        """Create several tasks to run in the AsyncThread."""
        return self.submit(self._create_tasks(*coro_functions)).result()

    async def _run(self):
        """Asynchronous run wrapper."""
        for queue in self._queues:
            await queue._create()
        await self._create_tasks(*self._tasks)

    def run(self):
        """Synchronously run thread."""
        # First submit all tasks
        self._loop.run_until_complete(self._run())
        # Then run loop forever
        # This function exits gracefully when loop is stopped
        self._loop.run_forever()

    def submit(self, coro: Coroutine) -> Future:
        """Submit a coroutine to thread."""
        # Submit a coroutine to event loop from another thread.
        # If this function is called from the same thread where event loop is running
        # Process will be blocked and hang forever
        return asyncio.run_coroutine_threadsafe(coro, loop=self._loop)

    def cancel(self) -> None:
        # Iterate over all running tasks
        for task in asyncio.all_tasks(loop=self._loop):
            # Cancel the task
            task.cancel()

    async def stop(self) -> None:
        self.cancel()
        try:
            await asyncio.wait(asyncio.all_tasks(self._loop), return_when="ALL_COMPLETED")
        except asyncio.CancelledError:
            pass
        return self._loop.stop()

    def join(self):
        self.submit(self.stop())
        super().join()

    def __enter__(self):
        """Context manager to start/stop thread automatically."""
        self.start()
        return self

    def __exit__(self, *_: Any, **__: Any):
        """Context manager to start/stop thread automatically."""
        self.join()

    def create_queue(self, start: bool = False, **kwargs: Any) -> QueueProxy[Any]:
        q: QueueProxy[Any] = QueueProxy(**kwargs)
        is_loop_running = self._loop.is_running()
        if start:
            if not is_loop_running:
                raise NotReadyError("Event loop is not running yet")
            self.submit(q._create()).result()
        else:
            if is_loop_running:
                warnings.warn("Event loop is already running but queues has not been started")
            self._queues.append(q)
        return q

    def create_queues(self, n: int, /, start: bool = False, **kwargs: Any) -> Iterable[QueueProxy[Any]]:
        return [self.create_queue(start=start, **kwargs) for _ in range(n)]

    def put_from_thread(
        self, queue: asyncio.Queue[T], item: T, blocking: bool = True
    ) -> None:
        """Put an item into a queue running in AsyncThread from a different thread."""
        future = self.submit(queue.put(item))
        if blocking:
            future.result()

    def get_from_thread(self, queue: asyncio.Queue[T]) -> T:
        """Get an item from a queue running in AsyncThread from a different thread."""
        return self.submit(queue.get()).result()


t = AsyncThread()

# Queues could also be created individually
# In this case no need to declare type before assignment
q1: QueueProxy[List[int]]
q1_out: QueueProxy[List[int]]
q1, q1_out = t.create_queues(2)


@t.task
async def process1() -> None:
    while True:
        try:
            # Fetch from one queue
            v = await q1.get()
            # And put in another
            await q1_out.put(v)
        except asyncio.CancelledError as err:
            # You can catch cancellation here
            print("Cancelled process 1")
            raise err


# Start the thread, this will start the first task
t.start()


# Queues created after thread has been started must be manually started
q2: QueueProxy[List[int]] = t.create_queue(start=True)
q2_out: QueueProxy[List[int]] = t.create_queue(start=True)


# Note that both tasks could have been decorated and started with the thread
# This is just an example
async def process2() -> None:
    while True:
        try:
            # Fetch from one queue
            v = await q2.get()
            # And put in another
            await q2_out.put(v)
        except asyncio.CancelledError as err:
            print("Cancelled process 2")
            raise err
# Start the other start after thread is started
t.create_task(process2)


to_put = [i for i in range(2048)]


async def foo():
    """A dummy async function."""
    return to_put


def measure_perf():
    with Timer() as timer:
        # Submit coroutine and get future
        future = t.submit(foo())
        # Get result from future
        result = future.result()
        duration = timer()
        print(f"Got processed item: {len(result)}. Took {duration:.5f} ms")

    with Timer() as timer:
        # We cannot use put here !
        t.put_from_thread(q1, to_put)
        # We cannot use get neither
        result = t.get_from_thread(q1_out)
        duration = timer()
        print(f"Got processed item: {len(result)}. Took {duration:.5f} ms")

    with Timer() as timer:
        # We cannot use put here !
        t.put_from_thread(q2, to_put)
        # We cannot use get neither
        result = t.get_from_thread(q2_out)
        # Indicate that work is done
        duration = timer()
        print(f"Got processed item: {len(result)}. Took {duration:.5f} ms")
