"""This module illustrates how to inehrit the thread class and create a custom thread."""
from __future__ import annotations

from threading import Thread, Event
import time


class CustomThread(Thread):
    """A subclass of threading.Thread that runs a specific function within a thread."""

    def __init__(self, *args, **kwargs):
        """Create a new thread instance."""
        super().__init__(*args, **kwargs)
        self._should_stop = Event()

    def run(self) -> None:
        """Function to run within thread."""
        # Do not use an infinite loop
        while not self._should_stop.is_set():
            print("Doing some work")
            time.sleep(0.5)
        print("Bye bye")

    def stop(self) -> None:
        """Stop the thread.

        Once the run() method returns or raises an error, the thread instance is considered stopped.

        There is no built-in mechanism to stop a thread, so it must be done by hand.

        In our case, we can simply set a threading Event and next time event is checked within run
        method, thread will be effictively stopped.
        """
        self._should_stop.set()

    def __enter__(self) -> CustomThread:
        """Method called when entering context manager."""
        self.start()
        return self

    def __exit__(self, *_, **__) -> None:
        """Method called when exiting context manager."""
        self.stop()


if __name__ == "__main__":

    # Create a thread instance using a context manager
    with CustomThread() as thread:
        time.sleep(1)

    # This is the same as:

    thread = CustomThread()
    # Start the thread, this will run the CustomThread.run method within the thread
    thread.start()
    # Let the thread do some work
    time.sleep(1)
    # Stop the thread. Once the CustomThread.run methods returns or raises an error, thread is considered stopped
    thread.stop()
