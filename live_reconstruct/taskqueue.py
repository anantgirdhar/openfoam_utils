#!/usr/bin/python3

import itertools as it
from typing import Generic, Iterator, TypeVar

from tasks import Task

T = TypeVar("T")


class PriorityList(Generic[T]):
    """A bare-bones implementation of a Priority List

    This assumes that the priorities are integers and the items are sorted in
    order of increasing priority number (similar to a min heap). If two items
    have the same priority, the one added first will occur earlier in the
    array.
    """

    def __init__(self, num_priorities: int) -> None:
        self.__list: list[T] = []
        # Create a list where each element gives the next index to insert an
        # element with the same priority as the index of that element
        self.__priority_indices = [
            0,
        ] * num_priorities

    def add(self, item: T, priority: int = 0) -> None:
        index = self.__priority_indices[priority]
        self.__list.insert(index, item)
        for index in range(priority, len(self.__priority_indices)):
            self.__priority_indices[index] += 1

    def pop(self) -> T:
        if len(self) == 0:
            raise IndexError("pop from empty list")
        item = self.__list.pop(0)
        self.__priority_indices = [
            max(index - 1, 0) for index in self.__priority_indices
        ]
        return item

    def __iter__(self) -> Iterator[T]:
        return iter(self.__list)

    def __len__(self) -> int:
        return len(self.__list)

    def __str__(self) -> str:
        return str(self.__list)

    def __repr__(self) -> str:
        return repr(self.__list)


class TaskQueue:
    def __init__(
        self, num_simultaneous_tasks: int = 6, num_priorities: int = 3
    ) -> None:
        self.num_simultaneous_tasks = num_simultaneous_tasks
        self._running: list[Task] = []
        self._queue: PriorityList[Task] = PriorityList(num_priorities)

    def add(self, *tasks: Task) -> None:
        for task in tasks:
            self._queue.add(task, task.priority)
        self.run_next()

    def run_next(self) -> None:
        if len(self._running) >= self.num_simultaneous_tasks:
            return
        if self._queue:
            next_pending_task = self._queue.pop()
            self._running.append(next_pending_task)
            self._running[-1].run()

    def update(self) -> None:
        for task in self._running:
            if task.is_complete():
                self._running.remove(task)
                if task.was_successful():
                    # Only run the next tasks if the parent task was successful
                    self.add(*task.next_tasks)

    def __len__(self) -> int:
        return len(self._running) + len(self._queue)

    def __iter__(self):  # type: ignore
        return it.chain(self._running, self._queue)

    def __repr__(self) -> str:
        return (
            f"[Task Queue: {len(self._running)} running / {len(self)} tasks]"
        )

    def __str__(self) -> str:
        task_list_string = f"{len(self)} tasks in queue:\n"
        for task in self._running:
            task_list_string += "  * " + str(task) + "\n"
        for task in self._queue:
            task_list_string += "  - " + str(task) + "\n"
        return task_list_string
