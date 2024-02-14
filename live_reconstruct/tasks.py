#!/usr/bin/python3

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

RECONSTRUCTION_DONE_MARKER_FILENAME = ".__reconstruction_done"


def reconstructed_timestamp_successfully_deleted(timestamp: str) -> bool:
    if Path(f"{timestamp}").is_dir():
        return False
    return True


def split_timestamp_successfully_deleted(timestamp: str) -> bool:
    # The split timestamp is successfully deleted if it does not exist in any
    # of the processor directories
    for processor_directory in Path(".").glob("processor*"):
        if (processor_directory / timestamp).is_dir():
            return False
    return True


def timestamp_successfully_reconstructed(timestamp: str) -> bool:
    reconstruction_done_marker_filepath = (
        Path(timestamp) / RECONSTRUCTION_DONE_MARKER_FILENAME
    )
    return reconstruction_done_marker_filepath.is_file()


def tarring_successfully_completed(timestamp: str) -> bool:
    if Path(f"{timestamp}.tar").is_file():
        return True
    else:
        return False


class Task(ABC):
    def __init__(self) -> None:
        super().__init__()
        self._process: Optional[subprocess.Popen] = None  # type: ignore
        self.next_tasks: list[Task] = []
        self.priority: int = 0

    @property
    @abstractmethod
    def command(self) -> str:
        pass

    def run(self) -> None:
        """Run the task"""
        if self.is_complete():
            return
        command = self.command  # + ' >/dev/null'
        self._process = subprocess.Popen(
            command, shell=True, stdout=subprocess.DEVNULL
        )

    def is_complete(self) -> bool:
        if self._process is None:
            return False
        return_value = self._process.poll()
        if return_value is None:
            return False
        return True

    def was_successful(self) -> Optional[bool]:
        if not self.is_complete():
            return None
        if self._process:
            return_value = self._process.poll()
            if return_value == 0:
                return True
            else:
                return False
        # If there is no process instance, but the task is complete, then we
        # were successful
        return True

    def __repr__(self) -> str:
        if num_next_tasks := len(self.next_tasks):
            return f"[Task: {self.command} + {num_next_tasks} others]"
        else:
            return f"[Task: {self.command}]"


class ReconstructTask(Task):
    def __init__(self, timestamp: str, post_cleanup: bool = True) -> None:
        super().__init__()
        self.timestamp = timestamp
        self.priority = 2
        if post_cleanup:
            self.create_followup_tasks()

    def create_followup_tasks(self) -> None:
        delete_split_task = DeleteSplitTask(self.timestamp)
        self.next_tasks.append(delete_split_task)
        tar_task = TarTask(self.timestamp, post_cleanup=True)
        self.next_tasks.append(tar_task)

    def is_complete(self) -> bool:
        if super().is_complete():
            return True
        return timestamp_successfully_reconstructed(self.timestamp)

    @property
    def command(self) -> str:
        reconstruction_done_marker_filepath = (
            Path(self.timestamp) / RECONSTRUCTION_DONE_MARKER_FILENAME
        )
        return " && ".join(
            [
                f"reconstructPar -time {self.timestamp}",
                f"touch {reconstruction_done_marker_filepath}",
            ]
        )


class DeleteReconstructedTask(Task):
    def __init__(self, timestamp: str) -> None:
        super().__init__()
        self.timestamp = timestamp
        self.priority = 0

    @property
    def command(self) -> str:
        return f"rm -rf {self.timestamp}"


class DeleteSplitTask(Task):
    def __init__(self, timestamp: str) -> None:
        super().__init__()
        self.timestamp = timestamp
        self.priority = 0

    @property
    def command(self) -> str:
        return f"rm -rf processor*/{self.timestamp}"


class TarTask(Task):
    def __init__(self, timestamp: str, post_cleanup: bool = True) -> None:
        super().__init__()
        self.timestamp = timestamp
        self.priority = 1
        if post_cleanup:
            self.create_followup_tasks()

    def create_followup_tasks(self) -> None:
        delete_reconstructed_task = DeleteReconstructedTask(self.timestamp)
        self.next_tasks.append(delete_reconstructed_task)

    def is_complete(self) -> bool:
        if super().is_complete():
            return True
        return tarring_successfully_completed(self.timestamp)

    @property
    def command(self) -> str:
        reconstruction_done_marker_filepath = (
            Path(self.timestamp) / RECONSTRUCTION_DONE_MARKER_FILENAME
        )
        tar_command = (
            f"tar --exclude {reconstruction_done_marker_filepath} "
            + f"-cvf {self.timestamp}.tar.inprogress {self.timestamp}"
        )
        return " && ".join(
            [
                tar_command,
                f"mv {self.timestamp}.tar.inprogress {self.timestamp}.tar",
            ]
        )
