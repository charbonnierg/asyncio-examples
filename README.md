# quara-concurrency

## Introduction

This repository contains a python package as well as code examples that leverage [`asyncio`](https://docs.python.org/3.8/library/asyncio.html) python library. It is meant to learn about `asyncio` and is not meant to be used in production (not yet at least).

## Some words about `asyncio`

`asyncio` is a library to write **concurrent** code using the **async**/**await** syntax.

`asyncio` is used as a foundation for multiple Python asynchronous frameworks that provide high-performance network and web-servers, database connection libraries, distributed task queues, etc.

`asyncio` is often a perfect fit for IO-bound and high-level structured network code.

> Note: [FastAPI](https://fastapi.tiangolo.com) provides a [really nice introcution to asynchronous code and concurrency](https://fastapi.tiangolo.com/async/#technical-details)

![asyncio schema](https://cdn2.hubspot.net/hubfs/424565/_02_Paxos_Engineering/Event-Loop.png)

While `asyncio` can be used to bring concurrency and be extremely useful when developing web-servers or network related libraries, it also has several downsides.

### `asyncio` is not friendly with Python REPL

One of the nice things about python is that you can always fire up the interpreter and step through code easily. For asyncio code, you need to run your code using an event loop. `await` keyword cannot be used outside a function, and running a coroutine requires a running event loop.

A trivial example such as sleeping is much more complicated with `asyncio`:

```python
import asyncio

async def main():
    """We must define a function to use `await` keyword and execute asyncio.sleep coroutine"""
    await asyncio.sleep(1)

asyncio.run(main())
```

The same example could be written as follow without concurrency:

```python
import time

time.sleep(1)
```

### `asyncio` is all or nothing (at least without playing with threads!)

If an event loop is running in the main thread, almost all code must be asynchronous in order not to block the event loop.
Indeed, all code still runs in a single thread by default, and while waiting for a blocking function, coroutines cannot be given a chance to run.

### Always thinking about the event loop is hard

Are you **awaiting** the result of several **coroutines** and then performing some action on that data? If so, you should be using `asyncio.gather`. Or, perhaps you want to `asyncio.wait` on **task** completion? Maybe you want your **future** to `run_until_complete` or your **loop** to `run_forever`?

Did you forget to put `async` in front of a function definition that uses `await`? That will throw an error. Did you forget to put `await` in front of an asynchronous function? That will return a coroutine that was never invoked, and intentionally not throw an error!

`asyncio` doesn’t play that nicely with threads, so if you’re using a library that depends on threading you’re going to have to come up with a workaround, same things goes with asynchronous queues.

### Everything is harder

Libraries are often buggier and less used/documented (though hopefully that will change over time). You’re not going to find as many helpful error messages on Stack Overflow. Something as easy as writing asynchronous unit tests is non-trivial.
There’s also more opportunities to mess up.

### Be prepared

When developping with `asyncio`, it is **MANDATORY** to rely on a linter such as `flake8`, a type checker such as `mypy` and run python with the `-X dev` flag to enable  the [**Python Development Mode**](https://docs.python.org/3/library/devmode.html).

Note that the development mode can also be enabled by setting the environment variable `PYTHON_DEV_MODE` to 1.

## Using `quara-concurrency` to better understand `asyncio`

The `quara-concurrency` library exposes a single class: `AsyncioThread` which can be used to start a new thread, with a running event loop.

This thread can then be used to schedule coroutines or to submit blocking functions to a thread pool executor. It comes with a bunch of methods to avoid errors related to unsafe threads usage. Reading those methods is helpful to understand `asyncio` concepts and tools. 

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

> Note: `AsyncioThread` inherits from `threading.Thread`. The method `AsyncioThread.start` comes directly from `threading.Thread.start`. The `AsyncioThread.run` method is called once thread is started, and once the method raises an error and finishes successfully, thread is stopped. It means that in order to stop this thread, `AsyncioThread.run` must be terminated.

```python
thread.stop_threadsafe()
```

> Note: We used `AsyncioThread.stop_threadsafe` method to stop the thread from a different thread because it is executed within the main thread and not within the `AsyncioThread` instance. This method submit the coroutine function `AsyncioThread.stop` into the thread event loop. f we wanted to stop the thread from within itself, we could create an `asyncio` task using the `AsyncioThread.stop` coroutine function. This is done in `AsyncioThread._signal_handler` method.

3. Start and stop the thread using a context manager:

```python
with AsyncioThread() as thread:
    # At this point thread is started
    pass
# And now thread is stopped
```

> Note: Take a look at `AsyncioThread.__enter__` and `AsyncioThread.__exit__` methods to see what's happening.

4. Run a coroutine within the `AsyncioThread` event loop:

```python
import asyncio


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

5. Start an `asyncio` task within an already running `AsyncioThread`

```python
import asyncio
import time

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


## References

* [The Python Standard Library -- asyncio -- Asynchronous I/O](https://docs.python.org/3.8/library/asyncio.html)
* [The Python Standard Library -- Development Tools -- Effects of the Python Development Mode](https://docs.python.org/3/library/devmode.html#effects-of-the-python-development-mode)
