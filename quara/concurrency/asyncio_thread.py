from __future__ import annotations

import asyncio
import atexit
import threading
import warnings
from asyncio.tasks import Task, shield
import concurrent.futures
from functools import partial
from typing import (
    Any,
    Callable,
    Coroutine,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
)


from .errors import NotReadyError
from .queues import QueueProxy


T = TypeVar("T", bound=Any)

STOP = threading.Event()
THREADS: List[AsyncioThread] = []


@atexit.register
def on_exit():
    """Register function to be run on system exit.

    It is necessary to perform cleanup in background threads.
    """
    STOP.set()
    while THREADS:
        thread = THREADS.pop()
        if thread._stop_event.is_set():
            continue
        thread._stop_event.wait()


class AsyncioThread(threading.Thread):
    """A subclass of threading.Thread which runs an event loop forever.

    All tasks running in event loops are cancelled on system exit or when
    user calls `stop()` method.

    Be careful with this class, it's easy to forget which coroutine should
    run on which event loop and raise RuntimeError.
    """

    def __init__(self, *, max_workers: Optional[int] = None, **kwargs: Any):
        """Create a new instance of asyncio thread.

        Args:
            max_workers: Maximum number of threads in ThreadPoolExecutor attached to the thread
            **kwargs: Any argument accepeted by threading.Thread.__init__ method
        """
        kwargs = {**kwargs, "daemon": True}
        # It is mandatory to call the __init__ method of threading.Thread parent class
        super().__init__(**kwargs)
        # Let's make things quicker and use uvloop.
        # Note that it does not seem that much faster, but way more reproducible (stable)
        try:
            import uvloop
        except ModuleNotFoundError:
            pass
        else:
            uvloop.install()
        # Create a new event loop that will be started within the thread
        self._loop = asyncio.new_event_loop()
        # Create a list of QueueProxy (wrapper around asyncio.Queue) to communicate between threads
        self._queue_proxies: List[QueueProxy[Any]] = []
        # Create a list of coroutine functions which will be started as asyncio tasks within the thread
        self._tasks: List[Coroutine] = []
        # Create a thread pool executor which will be used when executing costly blocking code
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        )
        # Create a threading event to notify thread stop
        self._stop_event = threading.Event()
        # Append the thread to the global list of running threads
        # It is necessary to stop the thread on system exit
        THREADS.append(self)

    def cancel(self) -> None:
        """Cancel all tasks running in thread event loop"""
        # Iterate over all running tasks
        for task in asyncio.all_tasks(loop=self._loop):
            # Cancel the task
            task.cancel()

    async def stop(self) -> None:
        """Stop the thread.

        In order to stop the thread, all tasks running in the event loop are cancelled. Once
        all tasks are either completed or cancelled, the event loop is stopped and the ThreadPoolExecutor
        shutdowned.
        """
        self.cancel()
        try:
            await asyncio.wait(
                asyncio.all_tasks(self._loop), return_when=asyncio.ALL_COMPLETED
            )
        except asyncio.CancelledError:
            # We expect tasks to be cancelled
            pass
        self._loop.stop()
        self._thread_pool.shutdown()
        self._stop_event.set()

    def __enter__(self):
        """Context manager to start/stop thread automatically."""
        self.start()
        return self

    def __exit__(self, *_: Any, **__: Any):
        """Context manager to start/stop thread automatically."""
        self.stop_threadsafe()
        self.join()

    def task(self, coro_function: Callable[[], Coroutine[None, None, None]]):
        """A decorator to create new asyncio tasks to run within the AsyncioThread event loop."""
        # Append the coroutine to the list of tasks
        self._tasks.append(coro_function())
        # Return the untouched function
        return coro_function

    async def create_task(self, coro: Coroutine) -> asyncio.Task:
        """Create a task and submit it to the thread event loop.

        Warning: This async method must be called within the AsyncioThread instance.
        """
        return asyncio.create_task(coro)

    async def create_tasks(self, *coroutines: Coroutine) -> List[asyncio.Task]:
        """Create several tasks and submit them to the thread event loop.

        Warning: This async method must be called within the AsyncioThread instance.
        """
        return [asyncio.create_task(coro) for coro in coroutines]

    def create_task_threadsafe(self, coro: Coroutine) -> asyncio.Task:
        """Create a task and submit it to the thread event loop.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        return self.run_threadsafe(self.create_tasks(coro)).result()[0]

    def create_tasks_threadsafe(self, *coroutines: Coroutine) -> List[asyncio.Task]:
        """Create several tasks and submit them to the thread event loop.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        return self.run_threadsafe(self.create_tasks(*coroutines)).result()

    async def _signal_handler(self) -> None:
        """An asyncio task to grafecully shutdown event loop and thread on system exit."""
        while True:
            if STOP.is_set() or self._stop_event.is_set():
                break
            else:
                await asyncio.sleep(0.5)
        asyncio.create_task(self.stop())
        self._stop_event.set()

    async def _run(self):
        """Asynchronous run wrapper."""
        # First wrap the signal handler with shield to never cancel it
        async def _handler():
            await shield(self._signal_handler())

        # Start the signal handler task
        await self.create_tasks(_handler())
        # Create user queues
        for queue in self._queue_proxies:
            await queue._create()
        # Create user tasks
        await self.create_tasks(*self._tasks)

    def run(self):
        """Function run within thread.

        Once this function ends, thread is stopped.
        """
        # First submit all tasks
        self._loop.run_until_complete(self._run())
        # Then run loop forever (I.E, until loop is stopped)
        self._loop.run_forever()

    def stop_threadsafe(self) -> None:
        """Stop the loop from a different thread."""
        if not self._loop.is_running():
            raise NotReadyError("Event loop is not running yet")
        self.run_threadsafe(self.stop())

    def create_queue_threadsafe(
        self, start: bool = False, **kwargs: Any
    ) -> QueueProxy[Any]:
        """Create a single QueueProxy to use with the AsyncioThread instance.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        q: QueueProxy[Any] = QueueProxy(**kwargs)
        is_loop_running = self._loop.is_running()
        if start:
            if not is_loop_running:
                raise NotReadyError("Event loop is not running yet")
            self.run_threadsafe(q._create()).result()
        else:
            if is_loop_running:
                warnings.warn(
                    "Event loop is already running but queues has not been started"
                )
            self._queue_proxies.append(q)
        return q

    def create_queues_threadsafe(
        self, n: int, /, start: bool = False, **kwargs: Any
    ) -> Iterable[QueueProxy[Any]]:
        """Create an iterable of QueueProxy to use with the AsyncioThread instance.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        return [self.create_queue_threadsafe(start=start, **kwargs) for _ in range(n)]

    def put_threadsafe(
        self, queue: QueueProxy[T], item: T
    ) -> concurrent.futures.Future[None]:
        """Put an item into a queue running in AsyncThread from a different thread.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        if not self._loop.is_running():
            raise NotReadyError("Event loop is not running yet")
        # Use run_threadsafe method to execute QueueProxy.put() method within the AsyncioThread instance
        return self.run_threadsafe(queue.put(item))

    def get_threadsafe(self, queue: QueueProxy[T]) -> T:
        """Get an item from a queue running in AsyncThread from a different thread.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        if not self._loop.is_running():
            raise NotReadyError("Event loop is not running yet")
        # Use run_threadsafe to execute QueueProxy.get() method within the AsyncioThread instance
        # Note that this function always block
        return self.run_threadsafe(queue.get()).result()

    async def run_in_executor(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        """Run a blocking function to another thread to not block event loop.

        Warning: This async method must be called within the AsyncioThread instance.
        """
        if not self._loop.is_running():
            raise NotReadyError("Event loop is not running yet")
        # EventLoop.run_in_executor does not accept keyword arguments
        # A quick solution is to use functools.partial to create a new function without argument
        wrapper = partial(func, *args, **kwargs)
        # Run the function in the thread pool executor
        return await self._loop.run_in_executor(self._thread_pool, wrapper)

    def run_threadsafe(
        self, coro: Coroutine[None, None, T]
    ) -> concurrent.futures.Future[T]:
        """Run a coroutine in thread event loop.

        In order to wait for coroutine to finish and get the result, one must
        use the .result() method on the returned Future instance.

        Example:
            >>> import asyncio

            >>> with AsyncioThread() as thread:
            >>>     # Get a Future instance after submitting the coroutine
            >>>     future = thread.run_threadsafe(asyncio.sleep(1))
            >>>     # Wait for the Future result
            >>>     future.result()

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        if not self._loop.is_running():
            raise NotReadyError("Event loop is not running yet")
        # Submit a coroutine to event loop from another thread.
        # If this function is called from the same thread where event loop is running
        # Process will be blocked and hang forever
        return asyncio.run_coroutine_threadsafe(coro, loop=self._loop)

    def run_in_executor_threadsafe(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> concurrent.futures.Future[T]:
        """Run a function using the ThreadPoolExecutor attached to the thread instance.

        Example:
            >>> import time

            >>> with AsyncioThread() as thread:
            >>>     # Get a Future instance after submitting the coroutine
            >>>     future = thread.run_in_executor_threadsafe(time.sleep, 1)
            >>>     # Wait for the Future result
            >>>     future.result()

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        return self.run_threadsafe(self.run_in_executor(func, *args, **kwargs))

    async def run_until_first_complete(
        self, *coroutines: Coroutine[None, None, T]
    ) -> T:
        """Run coroutines until first complete and return its result.

        Warning: This async method must be called within the AsyncioThread instance.
        """
        tasks = await self.create_tasks(*coroutines)
        (done, pending) = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        [task.cancel() for task in pending]
        return next(task.result() for task in done)

    def run_until_first_complete_threadsafe(
        self, *coroutines: Coroutine[None, None, T]
    ) -> concurrent.futures.Future[T]:
        """Run coroutines until first complete and return its result.

        Warning: This async method must be called within the AsyncioThread instance.
        """
        return self.run_threadsafe(self.run_until_first_complete(*coroutines))

    async def wait(
        self, tasks: Iterable[Task], return_when: str = asyncio.ALL_COMPLETED
    ) -> Tuple[Iterable[Task], Iterable[Task]]:
        """Wait for asyncio tasks. This function returns when all tasks are completed or cancelled by default.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        return await asyncio.wait(tasks, return_when=return_when)

    def wait_threadsafe(
        self, tasks: Iterable[Task], return_when: str = asyncio.ALL_COMPLETED
    ) -> concurrent.futures.Future[Tuple[Iterable[Task], Iterable[Task]]]:
        """Wait for asyncio tasks. This function returns when all tasks are completed or cancelled by default.

        Warning: This method must be called outside the AsyncioThread instance, in the main thread for example.
        """
        return self.run_threadsafe(self.wait(tasks, return_when=return_when))
