"""File transfer worker using background threads."""

import os
from dataclasses import dataclass
from enum import Enum
from PySide6.QtCore import QThread, Signal

from ssh_manager import SSHManager


class TransferDirection(Enum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


@dataclass
class TransferItem:
    """A single file/directory to transfer."""
    local_path: str
    remote_path: str
    direction: TransferDirection
    is_dir: bool = False


class TransferWorker(QThread):
    """Background worker for file transfers."""

    # Signals
    progress = Signal(str, int, int)  # filename, bytes_transferred, total_bytes
    file_started = Signal(str)  # filename
    file_finished = Signal(str)  # filename
    transfer_complete = Signal()
    error = Signal(str)  # error message

    def __init__(self, ssh_manager: SSHManager, items: list[TransferItem], parent=None):
        super().__init__(parent)
        self._ssh = ssh_manager
        self._items = items
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            for item in self._items:
                if self._cancelled:
                    break
                if item.direction == TransferDirection.UPLOAD:
                    self._do_upload(item)
                else:
                    self._do_download(item)
            self.transfer_complete.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _do_upload(self, item: TransferItem):
        """Upload a file or directory."""
        if item.is_dir:
            self._upload_dir(item.local_path, item.remote_path)
        else:
            self._upload_file(item.local_path, item.remote_path)

    def _do_download(self, item: TransferItem):
        """Download a file or directory."""
        if item.is_dir:
            self._download_dir(item.remote_path, item.local_path)
        else:
            self._download_file(item.remote_path, item.local_path)

    def _upload_file(self, local_path: str, remote_path: str):
        if self._cancelled:
            return
        filename = os.path.basename(local_path)
        self.file_started.emit(filename)

        def callback(transferred, total):
            self.progress.emit(filename, transferred, total)

        self._ssh.upload_file(local_path, remote_path, callback=callback)
        self.file_finished.emit(filename)

    def _upload_dir(self, local_path: str, remote_path: str):
        if self._cancelled:
            return
        # Create remote directory
        try:
            self._ssh.mkdir(remote_path)
        except IOError:
            pass  # directory may already exist

        for entry in os.listdir(local_path):
            if self._cancelled:
                return
            local_entry = os.path.join(local_path, entry)
            remote_entry = f"{remote_path}/{entry}"
            if os.path.isdir(local_entry):
                self._upload_dir(local_entry, remote_entry)
            else:
                self._upload_file(local_entry, remote_entry)

    def _download_file(self, remote_path: str, local_path: str):
        if self._cancelled:
            return
        filename = os.path.basename(remote_path)
        self.file_started.emit(filename)

        # Ensure local parent directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        def callback(transferred, total):
            self.progress.emit(filename, transferred, total)

        self._ssh.download_file(remote_path, local_path, callback=callback)
        self.file_finished.emit(filename)

    def _download_dir(self, remote_path: str, local_path: str):
        if self._cancelled:
            return
        os.makedirs(local_path, exist_ok=True)

        for item in self._ssh.list_dir(remote_path):
            if self._cancelled:
                return
            remote_entry = f"{remote_path}/{item.name}"
            local_entry = os.path.join(local_path, item.name)
            if item.is_dir:
                self._download_dir(remote_entry, local_entry)
            else:
                self._download_file(remote_entry, local_entry)
