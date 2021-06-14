# quara-concurrency

## Introduction

This repository contains a python package as well as code examples that leverage [`asyncio`](https://docs.python.org/3.8/library/asyncio.html) python library. It is meant to learn about `asyncio` and is not meant to be used in production (not yet at least).

> Note: Readers that never heard about *"concurrency"* or *"asynchronous programming"* are encouraged to read this [really nice introcution to asynchronous code and concurrency](https://fastapi.tiangolo.com/async/#technical-details)from [FastAPI](https://fastapi.tiangolo.com) documentation.

## `asyncio`: The bright side

- `asyncio` is a library to write **concurrent** code using the **async**/**await** syntax.

- `asyncio` is used as a foundation for multiple Python asynchronous frameworks that provide high-performance network and web-servers, database connection libraries, distributed task queues, etc.

- `asyncio` is often a perfect fit for IO-bound and high-level structured network code. 

![asyncio schema](https://cdn2.hubspot.net/hubfs/424565/_02_Paxos_Engineering/Event-Loop.png)

## `asyncio`: The dark side

While `asyncio` can be used to bring concurrency and be extremely useful when developing web-servers or network related libraries, it also has several downsides.

- **`asyncio` is not friendly with Python REPL**: One of the nice things about python is that you can always fire up the interpreter and step through code easily. For asyncio code, you need to run your code using an event loop. `await` keyword cannot be used outside a function, and running a coroutine requires a running event loop. A trivial example such as sleeping is much more complicated with `asyncio`:

    ```python
    import asyncio

    # Define a coroutine function
    async def main():
        """We must define a function to use `await` keyword and execute asyncio.sleep coroutine"""
        # It does not block the thread, instead, it let other coroutines have a chance to run while sleeping
        await asyncio.sleep(1)

    # Run the main coroutine function (this will start the event loop in the main thread) - Python 3.7+ only
    asyncio.run(main())
    ```

    than without:

    ```python
    import time

    # Sleep 1 second. It blocks the main thread
    time.sleep(1)
    ```

- **`asyncio` is all or nothing** (at least without playing with threads!): If an event loop is running in the main thread, almost all code must be asynchronous in order not to block the event loop. Indeed, all code still runs in a single thread by default, and while waiting for a blocking function, coroutines cannot be given a chance to run. Consider the following code:

    > NOTE: This code is intended to be WRONG. Do not copy/paste in your application carelessly

    ```python
    import asyncio
    from queue import Queue

    # Create a queue (this is a synchronous Queue, not the asynchronous queue available in asyncio.Queue)
    queue = Queue()

    # Define a coroutine function
    async def some_task():
        # Start an infinite loop
        while True:
            print("Doing some work")
            # Sleep 0.1 seconds before reentering loop
            await asyncio.sleep(0.1)


    # Define main coroutine
    async def main():
        # Create the task
        asyncio.create_task(some_task())
        # Get a value from the queue
        try:
            queue.get()
        except KeyboardInterrupt:
            print("Exiting")


    if __name__ == "__main__":
        # Run the main coroutine function (this will start the event loop in the main thread) - Python 3.7+ only
        asyncio.run(main())
    ```

    `some_task()` coroutine function should run in the event loop and print "Doing some work" every 0.1 second. But since the coroutine is running in the main thread, and main thread is blocked by `queue.get()` statement, the task never has a chance to run. If you cancel the program using `Ctrl+C`, you will see the task being run once, I.E, after `queue.get()` is cancelled, and before `event_loop` is closed.

- **always thinking about the event loop is hard**: Are you **awaiting** the result of several **coroutines** and then performing some action on that data? If so, you should be using `asyncio.gather`. Or, perhaps you want to `asyncio.wait` on **task** completion? Maybe you want your **future** to `run_until_complete` or your **loop** to `run_forever`? Did you forget to put `async` in front of a function definition that uses `await`? That will throw an error. Did you forget to put `await` in front of an asynchronous function? That will return a coroutine that was never invoked, and intentionally not throw an error!

- **`asyncio` doesn’t play that nicely with threads**: If you’re using a library that depends on threading you’re going to have to come up with a workaround, same things goes with asynchronous queues.

- **everything is harder**: Libraries are often buggier and less used/documented (though hopefully that will change over time). You’re not going to find as many helpful error messages on Stack Overflow. Something as easy as writing asynchronous unit tests is non-trivial. There’s also more opportunities to mess up.

### Be prepared

When developping with `asyncio`, it is **MANDATORY** to rely on a linter such as `flake8`, a type checker such as `mypy` and run python with the `-X dev` flag to enable  the [**Python Development Mode**](https://docs.python.org/3/library/devmode.html).

Note that the development mode can also be enabled by setting the environment variable `PYTHON_DEV_MODE` to 1.

## About `quara-concurrency`

The `quara-concurrency` library exposes a single class: `AsyncioThread` which can be used to start a new thread, with a running event loop.

This thread can then be used to:
- schedule coroutines to the event loop from any other thread
- submit blocking functions to a thread pool executor from any other thread

It comes with a bunch of methods to avoid errors related to unsafe thread usage. Reading those methods is helpful to better understand `asyncio` concepts and tools.

### Example usage

1. Import `AsyncioThread` and create a new thread:

    ```python
    from quara.concurrency import AsyncioThread


    thread = AsyncioThread()
    ```
    > Note: At this point, only the `__init__()` method of `AsyncioThread` has been called.

2. Start and stop the thread manually:

    ```python
    thread.start()
    ```

    > Note: `AsyncioThread` inherits from `threading.Thread`. The method `AsyncioThread.start` comes directly from `threading.Thread.start`. The `AsyncioThread.run` method is called once thread is started. Thread will be alive until the `AsyncioThread.run` method raises an error or finishes successfully. The `Asyncio.run` method first create some tasks into an event loop, then run the event loop forever. It means that in order to stop this thread gracefully, event loop must be stopped.

    ```python
    thread.stop_threadsafe()
    ```

    > Note: We used `AsyncioThread.stop_threadsafe` method to stop the thread because an event loop must be stopped from within a coroutine. Since the event loop we want to stop is running within the `AsyncioThread` instance, we must use `run_threadsafe()` method to schedule a new task to stop it from another thread. The `Asyncio.stop_threadsafe` method submit the coroutine function `AsyncioThread.stop` into the thread event loop. When running code within the thread, it is possible to create an `asyncio` task that runs the `AsyncioThread.stop` coroutine function. Such an example can be found in `AsyncioThread._signal_handler` method.

3. Start and stop the thread using a context manager:

    ```python
    from quara.concurrency import AsyncioThread


    with AsyncioThread() as thread:
        # At this point thread is started
        pass
    # And now thread is stopped
    ```

    > Note: Take a look at `AsyncioThread.__enter__` and `AsyncioThread.__exit__` methods to see what's happening.

4. Run a coroutine within the `AsyncioThread` event loop:

    ```python
    import asyncio
    from quara.concurrency import AsyncioThread


    with AsyncioThread() as thread:
        # Submit the coroutine to the thread event loop
        future = thread.run_threadsafe(asyncio.sleep(1))
        # Wait for returned value and assign it to result variable
        result = future.result()
        # `asyncio.sleep` function returns None
        assert result is None
    ```

    > Note: `AsyncioThread.run_threadsafe` does not return the result of the submitted coroutine, but returns a `concurrent.futures.Future` instead. This `Future` instance can be used to wait for and fetch the coroutine returned value.

5. Start an `asyncio` task within the `AsyncioThread` event loop using a decorator

    ```python
    import asyncio
    import time
    from quara.concurrency import AsyncioThread


    thread = AsyncioThread()


    @thread.task
    async def some_task():
        """A dummy task that runs forever.

        This task will stop only when cancelled.
        A more realistic task would be to read a network socket, or wait for items in a queue then process them.
        """
        # Let's loop infinitely
        while True:
            # And simulate that we're doing something
            print("Doing some work")
            try:
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                print("Bye bye")
                # Do not forget to break else task will never end
                break

    # The task is started with the thread
    thread.start()
    # Let's wait a bit
    time.sleep(1)
    # The task is cancelled on thread stop
    thread.stop_threadsafe()
    ```

6. Start an `asyncio` task within an already running `AsyncioThread`

    ```python
    import asyncio
    import time
    from quara.concurrency import AsyncioThread


    async def some_task():
        """A dummy task that runs forever.

        This task will stop only when cancelled.
        A more realistic task would be to read a network socket, or wait for items in a queue then process them.
        """
        # Let's loop infinitely
        while True:
            # And simulate that we're doing something
            print("Doing some work")
            try:
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                print("Bye bye")
                # Do not forget to break else task will never end
                break

    with AsyncioThread() as thread:
        # Create the task using a coroutine
        thread.create_task_threadsafe(some_task())
        # Let's wait a bit
        time.sleep(1)

    ```

    > Note: This one is pretty useful ! You can run as many tasks concurrently as you want 😙

7. Execute a costly blocking function in a third thread managed by a `ThreadPoolExecutor` instance within a coroutine:

    ```python
    import time
    from quara.concurrency import AsyncioThread


    thread = AsyncioThread()


    def costly_function(x: int):
        time.sleep(x)
        print("Bye bye")            

    async def some_task():
        await thread.run_in_executor(costly_function, 1)

    # thread will be stopped once context manager exits
    with thread:
        thread.run_threadsafe(some_task())
    ```

    Event if `time.sleep()` is a blocking function, it does not block the `AsyncioThread`. It is often required to run costly functions in an executor in order not to block the event loop (not all functions can be really asynchronous, I.E, CPU-bound functions).

    > Note: concurrency is not the same as parallelism. Only one task can run at a time, but tasks can be paused and resumed when `await` keyword is encountered.

8. Execute a costly blocking function in a third thread managed by a `ThreadPoolExecutor` instance:

    ```python
    import time
    from quara.concurrency import AsyncioThread


    def costly_function(x: int):
        time.sleep(x)
        print("Bye bye")

    # You can specify maximum number of threads for the executor
    with AsyncioThread(max_workers=8) as thread:
        # Create the task using a coroutine
        future = thread.run_in_executor_threadsafe(costly_function, 1)
        # The context manager will wait for the future to finish before exiting
        # If you don't want to wait, then don't use a context manager
    ```

    In this case, the function is still executed in a third thread, but is submitted from the main thread instead of the `AsyncioThread` instance.

## References

* [The Python Standard Library -- asyncio -- Asynchronous I/O](https://docs.python.org/3.8/library/asyncio.html)
* [The Python Standard Library -- Development Tools -- Effects of the Python Development Mode](https://docs.python.org/3/library/devmode.html#effects-of-the-python-development-mode)
