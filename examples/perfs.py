import asyncio
import time

from loguru import logger
from quara.concurrency import AsyncioThread
from quara.concurrency.utils import Timer

if __name__ == "__main__":
    with Timer() as timer:
        logger.debug(f"{timer():.5f} ms -- Timer initialized")

        with AsyncioThread() as thread:

            logger.debug(f"{timer():.5f} ms -- Thread ready")
            # This one runs in the event loop of the AsyncioThread
            future1 = thread.run_threadsafe(asyncio.sleep(1))
            # This one runs in an other thread managed by the ThreadPoolExecutor in AsyncioThread
            future2 = thread.run_in_executor_threadsafe(time.sleep, 1)

            async def short_lived() -> int:
                await asyncio.sleep(1)
                return 1

            # Those two run in the event loop of the AsyncioThread
            future3 = thread.run_until_first_complete_threadsafe(
                asyncio.sleep(3600), short_lived()
            )

            # This one will run in the event loop of the AsyncioThread
            async def do_some_work():
                with Timer(False) as timer:
                    while timer() < 1000:
                        await asyncio.sleep(0.5)
                        logger.debug("Doing some work...")

            task = thread.create_task_threadsafe(do_some_work())
            # At this points all tasks have been started
            logger.debug(f"{timer():.5f} ms -- All tasks started")
            # Let's wait for this task first
            thread.wait_threadsafe([task]).result()
            logger.debug(f"{timer():.5f} ms -- First task ended")
            future1.result()
            future2.result()
            logger.debug(f"{timer():.5f} ms -- Second and third tasks ended")
            done_task = future3.result()
            logger.debug(
                f"{timer():.5f} ms -- Last task ended with result: {done_task}"
            )
