"""File panel widget for browsing local and remote files."""

import os
import stat
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QMenu, QInputDialog, QMessageBox, QHeaderView,
    QLabel, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDrag, QIcon

from ssh_manager import SSHManager, RemoteFileInfo

# Custom data role for storing raw numeric values used in sorting
SORT_VALUE_ROLE = Qt.ItemDataRole.UserRole + 2


class SortableTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem that supports numeric sorting via stored sort values."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn()
        # Check if both items have a numeric sort value for this column
        self_val = self.data(column, SORT_VALUE_ROLE)
        other_val = other.data(column, SORT_VALUE_ROLE)
        if self_val is not None and other_val is not None:
            return self_val < other_val
        # Fall back to default string comparison
        return super().__lt__(other)


def format_size(size: int) -> str:
    """Format file size in human-readable format."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def format_time(timestamp: float) -> str:
    """Format timestamp to human-readable string."""
    if timestamp == 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError):
        return ""


class FileTreeWidget(QTreeWidget):
    """Custom tree widget with drag and drop support."""

    files_dropped = Signal(list, str)  # list of paths, target directory

    def __init__(self, panel: "FilePanel", parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        """Create mime data for dragged items."""
        mime = QMimeData()
        paths = []
        for item in items:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                paths.append(path)

        # Store source panel type and paths
        is_remote = self._panel.is_remote
        mime.setData("application/x-scpgui-source",
                     b"remote" if is_remote else b"local")
        mime.setData("application/x-scpgui-paths",
                     "\n".join(paths).encode("utf-8"))
        return mime

    def dragEnterEvent(self, event: QDragEnterEvent):
        mime = event.mimeData()
        if mime.hasFormat("application/x-scpgui-source"):
            source = bytes(mime.data("application/x-scpgui-source")).decode()
            # Accept drops from the OTHER panel only
            if (source == "remote") != self._panel.is_remote:
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-scpgui-source"):
            source = bytes(mime.data("application/x-scpgui-source")).decode()
            if (source == "remote") != self._panel.is_remote:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        mime = event.mimeData()
        if not mime.hasFormat("application/x-scpgui-paths"):
            event.ignore()
            return

        paths_data = bytes(mime.data("application/x-scpgui-paths")).decode("utf-8")
        paths = paths_data.split("\n")
        target_dir = self._panel.current_path

        self.files_dropped.emit(paths, target_dir)
        event.acceptProposedAction()


class FilePanel(QWidget):
    """A panel showing a file listing (local or remote)."""

    transfer_requested = Signal(list, str, bool)  # source_paths, target_dir, is_upload

    def __init__(self, is_remote: bool = False, ssh_manager: SSHManager = None, parent=None):
        super().__init__(parent)
        self._is_remote = is_remote
        self._ssh = ssh_manager
        self._current_path = ""
        self._show_hidden = False
        self._setup_ui()

    @property
    def is_remote(self) -> bool:
        return self._is_remote

    @property
    def current_path(self) -> str:
        return self._current_path

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # Header
        header = QHBoxLayout()
        title = QLabel("远程服务器" if self._is_remote else "本地文件")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        header.addWidget(title)
        header.addStretch()

        self._hidden_btn = QPushButton("显示隐藏文件")
        self._hidden_btn.setCheckable(True)
        self._hidden_btn.setMaximumHeight(24)
        self._hidden_btn.toggled.connect(self._toggle_hidden)
        header.addWidget(self._hidden_btn)
        layout.addLayout(header)

        # Path bar
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.returnPressed.connect(self._on_path_entered)
        path_layout.addWidget(self._path_edit)

        up_btn = QPushButton("↑")
        up_btn.setMaximumWidth(30)
        up_btn.clicked.connect(self._go_up)
        path_layout.addWidget(up_btn)

        # Transfer button: remote panel → download (→), local panel → upload (←)
        if self._is_remote:
            self._transfer_btn = QPushButton("→")
            self._transfer_btn.setToolTip("下载到本地")
        else:
            self._transfer_btn = QPushButton("←")
            self._transfer_btn.setToolTip("上传到服务器")
        self._transfer_btn.setMaximumWidth(30)
        self._transfer_btn.clicked.connect(self._on_transfer_btn)
        path_layout.addWidget(self._transfer_btn)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setMaximumWidth(30)
        refresh_btn.clicked.connect(self.refresh)
        path_layout.addWidget(refresh_btn)

        layout.addLayout(path_layout)

        # File tree
        self._tree = FileTreeWidget(self)
        self._tree.setHeaderLabels(["名称", "大小", "修改时间"])
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.files_dropped.connect(self._on_files_dropped)

        # Column widths
        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._tree)

        # Status bar
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._status)

    def navigate_to(self, path: str):
        """Navigate to a specific path."""
        self._current_path = path
        self._path_edit.setText(path)
        self.refresh()

    def refresh(self):
        """Refresh the current directory listing."""
        self._tree.clear()

        if self._is_remote:
            if not self._ssh or not self._ssh.is_connected:
                self._status.setText("未连接")
                return
            self._load_remote()
        else:
            self._load_local()

    def _load_remote(self):
        try:
            entries = self._ssh.list_dir(self._current_path)
        except Exception as e:
            self._status.setText(f"错误: {e}")
            return

        # Add parent directory entry
        if self._current_path != "/":
            parent_item = QTreeWidgetItem(["📁 ..", "", ""])
            parent_item.setData(0, Qt.ItemDataRole.UserRole, "__parent__")
            self._tree.addTopLevelItem(parent_item)

        dirs = []
        files = []
        for entry in entries:
            if not self._show_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir:
                dirs.append(entry)
            else:
                files.append(entry)

        # Sort: directories first, then files
        dirs.sort(key=lambda x: x.name.lower())
        files.sort(key=lambda x: x.name.lower())

        for entry in dirs:
            full_path = f"{self._current_path.rstrip('/')}/{entry.name}"
            item = SortableTreeWidgetItem([
                f"📁 {entry.name}",
                "",
                format_time(entry.mtime),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            item.setData(1, Qt.ItemDataRole.UserRole, True)  # is_dir flag
            item.setData(1, SORT_VALUE_ROLE, -1)  # dirs sort before files
            self._tree.addTopLevelItem(item)

        for entry in files:
            full_path = f"{self._current_path.rstrip('/')}/{entry.name}"
            item = SortableTreeWidgetItem([
                f"📄 {entry.name}",
                format_size(entry.size),
                format_time(entry.mtime),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            item.setData(1, Qt.ItemDataRole.UserRole, False)  # is_dir flag
            item.setData(1, SORT_VALUE_ROLE, entry.size)  # raw size for sorting
            self._tree.addTopLevelItem(item)

        count = len(dirs) + len(files)
        self._status.setText(f"{count} 个项目")

    def _load_local(self):
        try:
            entries = os.listdir(self._current_path)
        except PermissionError:
            self._status.setText("权限不足")
            return
        except Exception as e:
            self._status.setText(f"错误: {e}")
            return

        # Parent directory
        parent = str(Path(self._current_path).parent)
        if parent != self._current_path:
            parent_item = QTreeWidgetItem(["📁 ..", "", ""])
            parent_item.setData(0, Qt.ItemDataRole.UserRole, "__parent__")
            self._tree.addTopLevelItem(parent_item)

        dirs = []
        files = []

        for name in entries:
            if not self._show_hidden and name.startswith("."):
                continue
            full_path = os.path.join(self._current_path, name)
            try:
                st = os.stat(full_path)
                is_dir = stat.S_ISDIR(st.st_mode)
                size = st.st_size
                mtime = st.st_mtime
            except (OSError, PermissionError):
                continue

            if is_dir:
                dirs.append((name, full_path, size, mtime))
            else:
                files.append((name, full_path, size, mtime))

        dirs.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())

        for name, full_path, size, mtime in dirs:
            item = SortableTreeWidgetItem([
                f"📁 {name}",
                "",
                format_time(mtime),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            item.setData(1, Qt.ItemDataRole.UserRole, True)
            item.setData(1, SORT_VALUE_ROLE, -1)  # dirs sort before files
            self._tree.addTopLevelItem(item)

        for name, full_path, size, mtime in files:
            item = SortableTreeWidgetItem([
                f"📄 {name}",
                format_size(size),
                format_time(mtime),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            item.setData(1, Qt.ItemDataRole.UserRole, False)
            item.setData(1, SORT_VALUE_ROLE, size)  # raw size for sorting
            self._tree.addTopLevelItem(item)

        count = len(dirs) + len(files)
        self._status.setText(f"{count} 个项目")

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path == "__parent__":
            self._go_up()
            return

        is_dir = item.data(1, Qt.ItemDataRole.UserRole)
        if is_dir:
            self.navigate_to(path)

    def _go_up(self):
        if self._is_remote:
            parts = self._current_path.rstrip("/").rsplit("/", 1)
            parent = parts[0] if parts[0] else "/"
        else:
            parent = str(Path(self._current_path).parent)

        self.navigate_to(parent)

    def _on_path_entered(self):
        path = self._path_edit.text().strip()
        if path:
            self.navigate_to(path)

    def _toggle_hidden(self, checked: bool):
        self._show_hidden = checked
        self._hidden_btn.setText("隐藏隐藏文件" if checked else "显示隐藏文件")
        self.refresh()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("新建文件夹", self._create_folder)
        menu.addAction("刷新", self.refresh)

        item = self._tree.itemAt(pos)
        if item and item.data(0, Qt.ItemDataRole.UserRole) != "__parent__":
            menu.addSeparator()
            menu.addAction("重命名", lambda: self._rename_item(item))
            menu.addAction("删除", lambda: self._delete_item(item))

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _create_folder(self):
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:")
        if not ok or not name:
            return

        if self._is_remote:
            try:
                new_path = f"{self._current_path.rstrip('/')}/{name}"
                self._ssh.mkdir(new_path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"创建文件夹失败: {e}")
                return
        else:
            try:
                os.makedirs(os.path.join(self._current_path, name))
            except Exception as e:
                QMessageBox.critical(self, "错误", f"创建文件夹失败: {e}")
                return

        self.refresh()

    def _rename_item(self, item: QTreeWidgetItem):
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        old_name = os.path.basename(old_path)
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return

        if self._is_remote:
            try:
                parent = old_path.rsplit("/", 1)[0]
                new_path = f"{parent}/{new_name}"
                self._ssh.rename(old_path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"重命名失败: {e}")
                return
        else:
            try:
                parent = str(Path(old_path).parent)
                new_path = os.path.join(parent, new_name)
                os.rename(old_path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"重命名失败: {e}")
                return

        self.refresh()

    def _delete_item(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = item.data(1, Qt.ItemDataRole.UserRole)
        name = os.path.basename(path)

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {'目录' if is_dir else '文件'} \"{name}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._is_remote:
            try:
                if is_dir:
                    self._ssh.remove_recursive(path)
                else:
                    self._ssh.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")
                return
        else:
            try:
                if is_dir:
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")
                return

        self.refresh()

    def _on_transfer_btn(self):
        """Handle transfer button click: download (remote) or upload (local)."""
        selected = self.get_selected_paths()
        if not selected:
            return
        source_paths = [p for p, _ in selected]
        # For remote panel: download (is_upload=False), for local panel: upload (is_upload=True)
        is_upload = not self._is_remote
        # Pass empty target_dir - app.py will resolve it to the other panel's path
        self.transfer_requested.emit(source_paths, "", is_upload)

    def _on_files_dropped(self, paths: list[str], target_dir: str):
        """Handle files dropped from the other panel."""
        # Determine if this is upload or download based on this panel's type
        # If files are dropped ON this panel, we're receiving files here
        is_upload = self._is_remote  # dropping onto remote = upload
        self.transfer_requested.emit(paths, target_dir, is_upload)

    def get_selected_paths(self) -> list[tuple[str, bool]]:
        """Return list of (path, is_dir) for selected items."""
        result = []
        for item in self._tree.selectedItems():
            path = item.data(0, Qt.ItemDataRole.UserRole)
            is_dir = item.data(1, Qt.ItemDataRole.UserRole)
            if path and path != "__parent__":
                result.append((path, is_dir))
        return result
