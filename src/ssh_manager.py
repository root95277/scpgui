"""SSH/SFTP connection manager using paramiko."""

import json
import os
import stat
import paramiko
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable


@dataclass
class SSHConfig:
    """Represents an SSH connection configuration."""
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    key_file: str = ""
    label: str = ""  # display name from ssh config

    def display_name(self) -> str:
        if self.label:
            return self.label
        user_part = f"{self.username}@" if self.username else ""
        return f"{user_part}{self.host}:{self.port}"


@dataclass
class RemoteFileInfo:
    """Information about a remote file."""
    name: str
    is_dir: bool
    size: int
    mtime: float
    permissions: str = ""


def parse_ssh_config() -> list[SSHConfig]:
    """Parse ~/.ssh/config and return a list of SSHConfig entries."""
    config_path = Path.home() / ".ssh" / "config"
    if not config_path.exists():
        return []

    ssh_config = paramiko.SSHConfig()
    with open(config_path) as f:
        ssh_config.parse(f)

    configs = []
    for hostname in ssh_config.get_hostnames():
        if hostname == "*":
            continue
        info = ssh_config.lookup(hostname)
        host = info.get("hostname", hostname)
        port = int(info.get("port", 22))
        username = info.get("user", "")
        key_file = info.get("identityfile", [""])[0] if info.get("identityfile") else ""
        # Expand ~ in key_file
        if key_file:
            key_file = os.path.expanduser(key_file)

        configs.append(SSHConfig(
            host=host,
            port=port,
            username=username,
            key_file=key_file,
            label=hostname,
        ))

    return configs


SAVED_CONNECTIONS_FILE = Path.home() / ".scpgui" / "connections.json"


def load_saved_connections() -> list[SSHConfig]:
    """Load saved connections from ~/.scpgui/connections.json."""
    if not SAVED_CONNECTIONS_FILE.exists():
        return []
    try:
        data = json.loads(SAVED_CONNECTIONS_FILE.read_text(encoding="utf-8"))
        return [SSHConfig(**entry) for entry in data]
    except Exception:
        return []


def save_connection(config: SSHConfig) -> None:
    """Save a connection to history. Skips duplicates, never stores passwords."""
    connections = load_saved_connections()

    # Check for duplicate (same host + port + username)
    for existing in connections:
        if existing.host == config.host and existing.port == config.port \
                and existing.username == config.username:
            # Update key_file and label if changed
            existing.key_file = config.key_file
            existing.label = config.label
            _write_connections(connections)
            return

    # Add new (without password)
    saved = SSHConfig(
        host=config.host,
        port=config.port,
        username=config.username,
        key_file=config.key_file,
        label=config.label or config.display_name(),
    )
    connections.append(saved)
    _write_connections(connections)


def delete_saved_connection(config: SSHConfig) -> None:
    """Delete a saved connection."""
    connections = load_saved_connections()
    connections = [c for c in connections
                   if not (c.host == config.host and c.port == config.port
                           and c.username == config.username)]
    _write_connections(connections)


def _write_connections(connections: list[SSHConfig]) -> None:
    SAVED_CONNECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(c) for c in connections]
    # Never persist passwords
    for entry in data:
        entry.pop("password", None)
    SAVED_CONNECTIONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class SSHManager:
    """Manages SSH/SFTP connections."""

    def __init__(self):
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._config: Optional[SSHConfig] = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.get_transport() is not None \
            and self._client.get_transport().is_active()

    @property
    def config(self) -> Optional[SSHConfig]:
        return self._config

    @property
    def sftp(self) -> Optional[paramiko.SFTPClient]:
        return self._sftp

    def connect(self, config: SSHConfig) -> None:
        """Connect to a remote server."""
        self.disconnect()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": config.host,
            "port": config.port,
            "username": config.username,
            "timeout": 10,
        }

        if config.key_file and os.path.exists(config.key_file):
            connect_kwargs["key_filename"] = config.key_file
            if config.password:
                connect_kwargs["passphrase"] = config.password
        elif config.password:
            connect_kwargs["password"] = config.password
        else:
            # Try default keys
            connect_kwargs["look_for_keys"] = True

        client.connect(**connect_kwargs)
        self._client = client
        self._sftp = client.open_sftp()
        self._config = config

    def disconnect(self) -> None:
        """Disconnect from the remote server."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._config = None

    def list_dir(self, path: str) -> list[RemoteFileInfo]:
        """List files in a remote directory."""
        if not self._sftp:
            raise ConnectionError("Not connected")

        entries = []
        for attr in self._sftp.listdir_attr(path):
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
            entries.append(RemoteFileInfo(
                name=attr.filename,
                is_dir=is_dir,
                size=attr.st_size or 0,
                mtime=attr.st_mtime or 0,
                permissions=stat.filemode(attr.st_mode) if attr.st_mode else "",
            ))

        return entries

    def get_home_dir(self) -> str:
        """Get the remote user's home directory."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        return self._sftp.normalize(".")

    def download_file(self, remote_path: str, local_path: str,
                      callback: Optional[Callable[[int, int], None]] = None) -> None:
        """Download a single file."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        self._sftp.get(remote_path, local_path, callback=callback)

    def upload_file(self, local_path: str, remote_path: str,
                    callback: Optional[Callable[[int, int], None]] = None) -> None:
        """Upload a single file."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        self._sftp.put(local_path, remote_path, callback=callback)

    def mkdir(self, path: str) -> None:
        """Create a remote directory."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        self._sftp.mkdir(path)

    def rmdir(self, path: str) -> None:
        """Remove a remote directory (must be empty)."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        self._sftp.rmdir(path)

    def remove(self, path: str) -> None:
        """Remove a remote file."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        self._sftp.remove(path)

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename a remote file or directory."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        self._sftp.rename(old_path, new_path)

    def stat(self, path: str) -> paramiko.SFTPAttributes:
        """Get file attributes."""
        if not self._sftp:
            raise ConnectionError("Not connected")
        return self._sftp.stat(path)

    def is_dir(self, path: str) -> bool:
        """Check if a remote path is a directory."""
        try:
            attrs = self.stat(path)
            return stat.S_ISDIR(attrs.st_mode) if attrs.st_mode else False
        except Exception:
            return False

    def remove_recursive(self, path: str) -> None:
        """Recursively remove a remote directory."""
        if not self._sftp:
            raise ConnectionError("Not connected")

        for item in self.list_dir(path):
            item_path = f"{path}/{item.name}"
            if item.is_dir:
                self.remove_recursive(item_path)
            else:
                self._sftp.remove(item_path)
        self._sftp.rmdir(path)
