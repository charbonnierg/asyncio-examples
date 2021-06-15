from contextlib import contextmanager
from time import perf_counter
from typing import Callable, Iterator

from loguru import logger


@contextmanager
def Timer(print_time: bool = True, *, name: str = "") -> Iterator[Callable[[], float]]:
    """A context manager to measure time."""
    start = perf_counter()

    def timer_milliseconds() -> float:
        return (perf_counter() - start) * 1000

    yield timer_milliseconds

    if print_time:
        logger.debug(
            f"{timer_milliseconds():.5f} ms -- Timer{' (' + name + ')' if name else name} exited"
        )
