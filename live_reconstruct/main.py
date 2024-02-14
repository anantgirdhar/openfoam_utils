#!/usr/bin/python3

import subprocess
import time
from decimal import Decimal
from pathlib import Path

from taskqueue import TaskQueue
from tasks import (DeleteReconstructedTask, DeleteSplitTask, ReconstructTask,
                   TarTask, tarring_successfully_completed,
                   timestamp_successfully_reconstructed)


def is_to_be_deleted(t: str) -> bool:
    if t == "0":
        return True
    # This timestamp is to be deleted if it is not a "multiple" of 1e-5
    # First convert it to a Decimal so that we don't have to deal with floating
    # point weirdnesses
    timestamp = Decimal(t)
    # The timestamp is a "multiple" of 1e-5 if the timestamp times 1e5 does not
    # have a fractional part
    if (timestamp * int(1e5)) % 1 > 0:
        return True
    else:
        return False


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


def main() -> None:
    if not in_openfoam_root_case_dir():
        raise Exception("This is not an OpenFOAM root case dir.")
    task_queue = TaskQueue()
    initiate_incomplete_tasks_from_last_run(task_queue)
    times = sorted(
        [d.name for d in Path("processor0").glob("[0-9]*") if d.is_dir()],
        key=float,
    )
    for i, t in enumerate(times):
        print(f"\nIn processing loop, processing {t}")
        print(task_queue)
        if i == len(times) - 1:
            # If it is the last time in the list, don't do anything else
            continue
        if is_to_be_deleted(t):
            # If this time is to be deleted, then delete this
            task_queue.add(DeleteSplitTask(t))
        else:
            task_queue.add(ReconstructTask(t, post_cleanup=True))
    while task_queue:
        print("\nIn update loop")
        print(task_queue)
        task_queue.update()
        time.sleep(3)


if __name__ == "__main__":
    main()
