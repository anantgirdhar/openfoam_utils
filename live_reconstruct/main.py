#!/usr/bin/python3

import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Callable

from taskqueue import TaskQueue
from tasks import (DeleteReconstructedTask, DeleteSplitTask, ReconstructTask,
                   TarTask, tarring_successfully_completed,
                   timestamp_successfully_reconstructed)


def create_deletion_condition_function(
    keep_every: str,
) -> Callable[[str], bool]:
    def is_to_be_deleted(t: str) -> bool:
        if t == "0":
            return True
        # This timestamp is to be deleted if it is not a "multiple" of
        # keep_every
        # First convert it to a Decimal so that we don't have to deal with
        # floating point weirdnesses
        timestamp = Decimal(t)
        # The timestamp is a "multiple" of keep_every if the timestamp times
        # (1/keep_every) does not have a fractional part
        # But we also have to make sure to account for floating point
        # weirdnesses with (1/keep_every)
        factor = Decimal(int(round(1 / float(keep_every), 1)))
        if (timestamp * factor) % 1 > 0:
            return True
        else:
            return False

    return is_to_be_deleted


def initiate_incomplete_tasks_from_last_run(task_queue: TaskQueue) -> None:
    for path in Path(".").glob("[0-9]*"):
        if path.name.endswith(".tar"):
            # This is a finished tar
            # No need to do anything
            pass
        if path.name.endswith(".tar.inprogress"):
            # If there is a half constructed tar, just delete it and start over
            # We should be able to assume that the time dir still exists
            # because if it didn't, the tar would have been fully constructed
            subprocess.Popen(f"rm {path}", shell=True)
            timestamp = path.stem
            task_queue.add(TarTask(timestamp, post_cleanup=True))
        if path.is_dir():
            # Make sure that there are no half-deleted reconstructed folders
            # If the timestamp has been tarred, then delete it
            # TODO: Build out these cases
            timestamp = path.name
            if tarring_successfully_completed(timestamp):
                task_queue.add(DeleteReconstructedTask(timestamp))
            elif timestamp_successfully_reconstructed(timestamp):
                task_queue.add(TarTask(timestamp, post_cleanup=True))
            else:
                # If we get here, this timestamp needs to be reconstructed
                # But that should get started when we start looping through the
                # split timesteps so don't do anything here
                # task_queue.add(ReconstructTask(timestamp, post_cleanup=True))
                pass


def in_openfoam_root_case_dir() -> bool:
    # To check that we're in an OpenFOAM case dir, check to see if we have:
    # - a constant dir
    # - a system dir
    # - a processor0 dir
    if not Path("./constant").is_dir():
        return False
    if not Path("./system").is_dir():
        return False
    if not Path("./processor0").is_dir():
        return False
    return True


def find_and_add_tasks(
    task_queue: TaskQueue,
    processed_times: list[str],
    is_to_be_deleted: Callable[[str], bool],
) -> list[str]:
    times_found = sorted(
        [d.name for d in Path("processor0").glob("[0-9]*") if d.is_dir()],
        key=float,
    )
    for i, t in enumerate(times_found):
        if t in processed_times:
            continue
        print(f"\nIn find-and-add loop, processing {t}")
        print(task_queue)
        if i == len(times_found) - 1:
            # If it is the last time in the list, don't do anything else
            break
        if is_to_be_deleted(t):
            # If this time is to be deleted, then delete this
            task_queue.add(DeleteSplitTask(t))
        else:
            task_queue.add(ReconstructTask(t, post_cleanup=True))
        processed_times.append(t)
    return processed_times


def main(
    keep_every: str,
    sleep_time_per_update: int = 2,
    recheck_every_num_updates: int = 1,
) -> None:
    num_updates = 0
    if not in_openfoam_root_case_dir():
        raise Exception("This is not an OpenFOAM root case dir.")
    task_queue = TaskQueue()
    initiate_incomplete_tasks_from_last_run(task_queue)
    processed_times: list[str] = []
    is_to_be_deleted = create_deletion_condition_function(keep_every)
    processed_times = find_and_add_tasks(
        task_queue, processed_times, is_to_be_deleted
    )
    while len(task_queue) > 0 or recheck_every_num_updates > 0:
        num_updates += 1
        if len(task_queue) > 0:
            print("\nUpdating task queue")
            print(task_queue)
            task_queue.update()
        time.sleep(sleep_time_per_update)
        if recheck_every_num_updates <= 0 and len(task_queue) == 0:
            return
        if (
            recheck_every_num_updates > 0
            and num_updates % recheck_every_num_updates == 0
        ):
            processed_times = find_and_add_tasks(
                task_queue, processed_times, is_to_be_deleted
            )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]}"
            " keep_every"
            " sleep_time_per_update"
            " [recheck_every_num_updates]"
        )
        sys.exit(-1)
    keep_every = sys.argv[1]
    sleep_time_per_update = int(sys.argv[2])
    recheck_every_num_updates = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    main(keep_every, sleep_time_per_update, recheck_every_num_updates)
