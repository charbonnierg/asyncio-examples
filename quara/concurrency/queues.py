import asyncio
from typing import Any, Generic, Optional, TypeVar

from .errors import NotReadyError


T = TypeVar("T", bound=Any)


class QueueProxy(Generic[T]):
    """A simple proxy wrapper around asyncio.Queue class."""

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
