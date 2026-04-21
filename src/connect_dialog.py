"""SSH connection dialog."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QPushButton,
    QFileDialog, QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QWidget, QMessageBox, QMenu,
)
from PySide6.QtCore import Qt
from typing import Optional

from ssh_manager import SSHConfig, parse_ssh_config, load_saved_connections, delete_saved_connection


class ConnectDialog(QDialog):
    """Dialog for SSH connection setup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SSH 连接")
        self.setMinimumWidth(480)
        self._ssh_configs = parse_ssh_config()
        self._saved_connections = load_saved_connections()
        self._result_config: Optional[SSHConfig] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Mode selector
        mode_layout = QHBoxLayout()
        self._btn_history = QPushButton("历史连接")
        self._btn_ssh_config = QPushButton("SSH 配置")
        self._btn_manual = QPushButton("手动输入")
        for btn in (self._btn_history, self._btn_ssh_config, self._btn_manual):
            btn.setCheckable(True)
        # Default to history tab if there are saved connections, otherwise manual
        if self._saved_connections:
            self._btn_history.setChecked(True)
        elif self._ssh_configs:
            self._btn_ssh_config.setChecked(True)
        else:
            self._btn_manual.setChecked(True)
        self._btn_history.clicked.connect(lambda: self._switch_mode(0))
        self._btn_ssh_config.clicked.connect(lambda: self._switch_mode(1))
        self._btn_manual.clicked.connect(lambda: self._switch_mode(2))
        mode_layout.addWidget(self._btn_history)
        mode_layout.addWidget(self._btn_ssh_config)
        mode_layout.addWidget(self._btn_manual)
        layout.addLayout(mode_layout)

        # Stacked widget for three modes
        self._stack = QStackedWidget()

        # Page 0: Saved connection history
        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.addWidget(QLabel("历史连接 (连接成功后自动保存):"))
        self._history_list = QListWidget()
        self._history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._history_list.customContextMenuRequested.connect(self._on_history_context_menu)
        for cfg in self._saved_connections:
            item = QListWidgetItem(cfg.display_name())
            item.setData(Qt.ItemDataRole.UserRole, cfg)
            self._history_list.addItem(item)
        self._history_list.itemDoubleClicked.connect(self._on_saved_double_click)
        history_layout.addWidget(self._history_list)
        # Password input for history
        hist_pass_layout = QFormLayout()
        self._history_password = QLineEdit()
        self._history_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._history_password.setPlaceholderText("输入密码或密钥口令")
        hist_pass_layout.addRow("密码:", self._history_password)
        history_layout.addLayout(hist_pass_layout)
        # Delete selected history item button
        hist_btn_layout = QHBoxLayout()
        hist_btn_layout.addStretch()
        self._btn_delete_history = QPushButton("删除选中")
        self._btn_delete_history.clicked.connect(self._on_delete_history_clicked)
        hist_btn_layout.addWidget(self._btn_delete_history)
        history_layout.addLayout(hist_btn_layout)
        if not self._saved_connections:
            no_history = QLabel("暂无历史连接，手动连接成功后会自动保存")
            no_history.setStyleSheet("color: gray; padding: 20px;")
            no_history.setAlignment(Qt.AlignmentFlag.AlignCenter)
            history_layout.addWidget(no_history)
        self._stack.addWidget(history_page)

        # Page 1: SSH config connections
        config_page = QWidget()
        config_layout = QVBoxLayout(config_page)
        config_layout.addWidget(QLabel("从 ~/.ssh/config 选择:"))
        self._config_list = QListWidget()
        for cfg in self._ssh_configs:
            item = QListWidgetItem(cfg.display_name())
            item.setData(Qt.ItemDataRole.UserRole, cfg)
            self._config_list.addItem(item)
        self._config_list.itemDoubleClicked.connect(self._on_saved_double_click)
        config_layout.addWidget(self._config_list)
        pass_layout = QFormLayout()
        self._saved_password = QLineEdit()
        self._saved_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._saved_password.setPlaceholderText("如果密钥需要密码则填写")
        pass_layout.addRow("密码/密钥口令:", self._saved_password)
        config_layout.addLayout(pass_layout)
        self._stack.addWidget(config_page)

        # Page 2: Manual input
        manual_page = QWidget()
        manual_layout = QFormLayout(manual_page)
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("例如: 192.168.1.100")
        manual_layout.addRow("主机:", self._host_input)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        manual_layout.addRow("端口:", self._port_input)

        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("例如: root")
        manual_layout.addRow("用户名:", self._user_input)

        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["密码", "密钥文件"])
        self._auth_combo.currentIndexChanged.connect(self._on_auth_changed)
        manual_layout.addRow("认证方式:", self._auth_combo)

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        manual_layout.addRow("密码:", self._password_input)

        key_layout = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("选择私钥文件路径")
        self._key_input.setEnabled(False)
        self._key_browse_btn = QPushButton("浏览...")
        self._key_browse_btn.setEnabled(False)
        self._key_browse_btn.clicked.connect(self._browse_key)
        key_layout.addWidget(self._key_input)
        key_layout.addWidget(self._key_browse_btn)
        manual_layout.addRow("密钥文件:", key_layout)

        self._stack.addWidget(manual_page)

        layout.addWidget(self._stack)

        # Set default page
        if self._saved_connections:
            self._stack.setCurrentIndex(0)
        elif self._ssh_configs:
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(2)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        connect_btn = QPushButton("连接")
        connect_btn.setDefault(True)
        connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(connect_btn)
        layout.addLayout(btn_layout)

    def _switch_mode(self, index: int):
        self._stack.setCurrentIndex(index)
        self._btn_history.setChecked(index == 0)
        self._btn_ssh_config.setChecked(index == 1)
        self._btn_manual.setChecked(index == 2)

    def _on_auth_changed(self, index: int):
        is_key = index == 1
        self._password_input.setEnabled(not is_key)
        self._key_input.setEnabled(is_key)
        self._key_browse_btn.setEnabled(is_key)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择私钥文件",
            str(__import__("pathlib").Path.home() / ".ssh"),
        )
        if path:
            self._key_input.setText(path)

    def _on_saved_double_click(self, item: QListWidgetItem):
        self._on_connect()

    def _on_delete_history_clicked(self):
        item = self._history_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一条历史链接")
            return
        self._delete_history_item(item)

    def _on_history_context_menu(self, pos):
        item = self._history_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.addAction("删除此连接", lambda: self._delete_history_item(item))
        menu.exec(self._history_list.viewport().mapToGlobal(pos))

    def _delete_history_item(self, item: QListWidgetItem):
        config: SSHConfig = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除保存的连接 \"{config.display_name()}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_saved_connection(config)
            self._history_list.takeItem(self._history_list.row(item))

    def _on_connect(self):
        page = self._stack.currentIndex()

        if page == 0:
            # History connection
            item = self._history_list.currentItem()
            if not item:
                QMessageBox.warning(self, "提示", "请选择一个连接")
                return
            config: SSHConfig = item.data(Qt.ItemDataRole.UserRole)
            password = self._history_password.text().strip()
            if password:
                config.password = password
            self._result_config = config
        elif page == 1:
            # SSH config connection
            item = self._config_list.currentItem()
            if not item:
                QMessageBox.warning(self, "提示", "请选择一个连接")
                return
            config: SSHConfig = item.data(Qt.ItemDataRole.UserRole)
            password = self._saved_password.text().strip()
            if password:
                config.password = password
            self._result_config = config
        else:
            # Manual input
            host = self._host_input.text().strip()
            if not host:
                QMessageBox.warning(self, "提示", "请输入主机地址")
                return
            username = self._user_input.text().strip()
            if not username:
                QMessageBox.warning(self, "提示", "请输入用户名")
                return

            config = SSHConfig(
                host=host,
                port=self._port_input.value(),
                username=username,
            )
            if self._auth_combo.currentIndex() == 0:
                config.password = self._password_input.text()
            else:
                config.key_file = self._key_input.text().strip()
                config.password = self._password_input.text()  # passphrase

            self._result_config = config

        self.accept()

    def get_config(self) -> Optional[SSHConfig]:
        """Return the SSH config if dialog was accepted."""
        return self._result_config
