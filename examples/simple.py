import asyncio
import time

from quara.concurrency import AsyncioThread


with AsyncioThread() as thread:

    # This one runs in the event loop of the AsyncioThread
    future1 = thread.run_threadsafe(asyncio.sleep(1))

    # This one runs in an other thread managed by the ThreadPoolExecutor in AsyncioThread
    future2 = thread.run_in_executor_threadsafe(time.sleep, 1)

    async def short_lived() -> int:
        """Define a short live coroutine function."""
        await asyncio.sleep(1)
        return 1

    # Those two run in the event loop of the AsyncioThread
    # Result is result of first coroutine to finish
    future3 = thread.run_until_first_complete_threadsafe(
        asyncio.sleep(3600), short_lived()
    )

    # This one will run in the event loop of the AsyncioThread
    async def do_some_work():
        for i in range(2):
            print("Doing some work")
            await asyncio.sleep(1)

    # Create a task
    task = thread.create_task_threadsafe(do_some_work())

    # Let's wait for this task first
    thread.wait_threadsafe([task]).result()

    # Get future results
    future1.result()
    future2.result()
    done_task = future3.result()
