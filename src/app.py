"""Main application window."""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QToolBar, QStatusBar, QProgressBar, QLabel,
    QMessageBox, QSplitter, QApplication,
)
from PySide6.QtCore import Qt, QTimer
from typing import Optional
from PySide6.QtGui import QAction

from ssh_manager import SSHManager, save_connection
from file_panel import FilePanel
from connect_dialog import ConnectDialog
from transfer import TransferWorker, TransferItem, TransferDirection


class MainWindow(QMainWindow):
    """Main application window with dual-pane file manager."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SCP GUI - 文件传输工具")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        self._ssh = SSHManager()
        self._transfer_worker: Optional[TransferWorker] = None

        self._setup_toolbar()
        self._setup_panels()
        self._setup_statusbar()

        # Initialize local panel to default downloads directory
        default_local = Path("/Users/jack/Downloads")
        if not default_local.is_dir():
            default_local = Path.home()
        self._local_panel.navigate_to(str(default_local))

    def _setup_toolbar(self):
        toolbar = QToolBar("工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._connect_action = QAction("🔗 连接", self)
        self._connect_action.triggered.connect(self._on_connect)
        toolbar.addAction(self._connect_action)

        self._disconnect_action = QAction("🔌 断开", self)
        self._disconnect_action.triggered.connect(self._on_disconnect)
        self._disconnect_action.setEnabled(False)
        toolbar.addAction(self._disconnect_action)

        toolbar.addSeparator()

        refresh_action = QAction("🔄 刷新", self)
        refresh_action.triggered.connect(self._refresh_all)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        upload_action = QAction("⬆ 上传", self)
        upload_action.setToolTip("上传选中的本地文件到远程服务器")
        upload_action.triggered.connect(self._on_upload_btn)
        toolbar.addAction(upload_action)

        download_action = QAction("⬇ 下载", self)
        download_action.setToolTip("下载选中的远程文件到本地")
        download_action.triggered.connect(self._on_download_btn)
        toolbar.addAction(download_action)

    def _setup_panels(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Remote panel
        self._remote_panel = FilePanel(is_remote=True, ssh_manager=self._ssh)
        self._remote_panel.transfer_requested.connect(self._on_transfer_requested)
        splitter.addWidget(self._remote_panel)

        # Right: Local panel
        self._local_panel = FilePanel(is_remote=False)
        self._local_panel.transfer_requested.connect(self._on_transfer_requested)
        splitter.addWidget(self._local_panel)

        splitter.setSizes([500, 500])
        layout.addWidget(splitter)

    def _setup_statusbar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self._conn_label = QLabel("未连接")
        status_bar.addWidget(self._conn_label)

        status_bar.addWidget(QWidget(), 1)  # spacer

        self._transfer_label = QLabel("")
        status_bar.addWidget(self._transfer_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setVisible(False)
        status_bar.addWidget(self._progress_bar)

    def _on_connect(self):
        dialog = ConnectDialog(self)
        if dialog.exec() != ConnectDialog.DialogCode.Accepted:
            return

        config = dialog.get_config()
        if not config:
            return

        self._conn_label.setText(f"连接中 {config.display_name()}...")
        QApplication.processEvents()

        try:
            self._ssh.connect(config)
        except Exception as e:
            QMessageBox.critical(self, "连接失败", f"无法连接到服务器:\n{e}")
            self._conn_label.setText("未连接")
            return

        self._conn_label.setText(f"已连接: {config.display_name()}")
        self._connect_action.setEnabled(False)
        self._disconnect_action.setEnabled(True)

        # Auto-save connection to history
        save_connection(config)

        # Navigate to remote home directory
        try:
            home = self._ssh.get_home_dir()
        except Exception:
            home = "/"
        self._remote_panel.navigate_to(home)

    def _on_disconnect(self):
        self._ssh.disconnect()
        self._conn_label.setText("未连接")
        self._connect_action.setEnabled(True)
        self._disconnect_action.setEnabled(False)
        self._remote_panel.refresh()

    def _refresh_all(self):
        self._remote_panel.refresh()
        self._local_panel.refresh()

    def _on_upload_btn(self):
        """Upload selected local files to remote."""
        if not self._ssh.is_connected:
            QMessageBox.warning(self, "提示", "请先连接到远程服务器")
            return

        selected = self._local_panel.get_selected_paths()
        if not selected:
            QMessageBox.warning(self, "提示", "请在右侧本地面板中选择要上传的文件")
            return

        source_paths = [p for p, _ in selected]
        target_dir = self._remote_panel.current_path
        self._start_transfer(source_paths, target_dir, is_upload=True)

    def _on_download_btn(self):
        """Download selected remote files to local."""
        if not self._ssh.is_connected:
            QMessageBox.warning(self, "提示", "请先连接到远程服务器")
            return

        selected = self._remote_panel.get_selected_paths()
        if not selected:
            QMessageBox.warning(self, "提示", "请在左侧远程面板中选择要下载的文件")
            return

        source_paths = [p for p, _ in selected]
        target_dir = self._local_panel.current_path
        self._start_transfer(source_paths, target_dir, is_upload=False)

    def _on_transfer_requested(self, source_paths: list[str], target_dir: str, is_upload: bool):
        """Handle transfer request from drag-and-drop or panel transfer button."""
        if not self._ssh.is_connected:
            QMessageBox.warning(self, "提示", "请先连接到远程服务器")
            return
        if not target_dir:
            # Resolve target to the other panel's current path
            target_dir = self._remote_panel.current_path if is_upload else self._local_panel.current_path
        self._start_transfer(source_paths, target_dir, is_upload)

    def _start_transfer(self, source_paths: list[str], target_dir: str, is_upload: bool):
        """Start file transfer in background thread."""
        if self._transfer_worker and self._transfer_worker.isRunning():
            QMessageBox.warning(self, "提示", "已有传输任务正在进行中")
            return

        items = []
        for src in source_paths:
            name = os.path.basename(src)
            if is_upload:
                remote_path = f"{target_dir.rstrip('/')}/{name}"
                is_dir = os.path.isdir(src)
                items.append(TransferItem(
                    local_path=src,
                    remote_path=remote_path,
                    direction=TransferDirection.UPLOAD,
                    is_dir=is_dir,
                ))
            else:
                local_path = os.path.join(target_dir, name)
                is_dir = self._ssh.is_dir(src)
                items.append(TransferItem(
                    local_path=local_path,
                    remote_path=src,
                    direction=TransferDirection.DOWNLOAD,
                    is_dir=is_dir,
                ))

        self._transfer_worker = TransferWorker(self._ssh, items)
        self._transfer_worker.file_started.connect(self._on_file_started)
        self._transfer_worker.progress.connect(self._on_progress)
        self._transfer_worker.file_finished.connect(self._on_file_finished)
        self._transfer_worker.transfer_complete.connect(self._on_transfer_complete)
        self._transfer_worker.error.connect(self._on_transfer_error)

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._transfer_worker.start()

    def _on_file_started(self, filename: str):
        self._transfer_label.setText(f"正在传输: {filename}")

    def _on_progress(self, filename: str, transferred: int, total: int):
        if total > 0:
            percent = int(transferred * 100 / total)
            self._progress_bar.setValue(percent)

    def _on_file_finished(self, filename: str):
        pass

    def _on_transfer_complete(self):
        self._progress_bar.setVisible(False)
        self._transfer_label.setText("传输完成")
        self._refresh_all()
        # Clear status after 3 seconds
        QTimer.singleShot(3000, lambda: self._transfer_label.setText(""))

    def _on_transfer_error(self, error: str):
        self._progress_bar.setVisible(False)
        self._transfer_label.setText("")
        QMessageBox.critical(self, "传输错误", f"文件传输失败:\n{error}")

    def closeEvent(self, event):
        if self._transfer_worker and self._transfer_worker.isRunning():
            reply = QMessageBox.question(
                self, "确认退出",
                "文件传输正在进行中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._transfer_worker.cancel()
            self._transfer_worker.wait(3000)

        self._ssh.disconnect()
        event.accept()
