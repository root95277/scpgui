#!/usr/bin/env python3
"""SCP GUI - Graphical file transfer tool using SSH/SFTP."""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

from app import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SCP GUI")
    app.setStyle("Fusion")

    # Set dark theme stylesheet for a modern look
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
        }
        QWidget {
            background-color: #2b2b2b;
            color: #e0e0e0;
            font-size: 13px;
        }
        QTreeWidget {
            background-color: #1e1e1e;
            alternate-background-color: #252525;
            border: 1px solid #3a3a3a;
            color: #e0e0e0;
            selection-background-color: #264f78;
        }
        QTreeWidget::item {
            padding: 2px 4px;
            height: 24px;
        }
        QTreeWidget::item:hover {
            background-color: #333333;
        }
        QHeaderView::section {
            background-color: #333333;
            color: #e0e0e0;
            border: 1px solid #3a3a3a;
            padding: 4px;
            font-weight: bold;
        }
        QLineEdit {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            padding: 4px 8px;
            color: #e0e0e0;
        }
        QLineEdit:focus {
            border-color: #4a9eff;
        }
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #4a4a4a;
            border-radius: 3px;
            padding: 4px 12px;
            color: #e0e0e0;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
        }
        QPushButton:pressed {
            background-color: #2a2a2a;
        }
        QPushButton:checked {
            background-color: #264f78;
            border-color: #4a9eff;
        }
        QToolBar {
            background-color: #333333;
            border-bottom: 1px solid #3a3a3a;
            spacing: 4px;
            padding: 4px;
        }
        QToolBar QToolButton {
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 3px;
            padding: 4px 8px;
            color: #e0e0e0;
        }
        QToolBar QToolButton:hover {
            background-color: #4a4a4a;
            border-color: #4a4a4a;
        }
        QStatusBar {
            background-color: #333333;
            border-top: 1px solid #3a3a3a;
            color: #a0a0a0;
        }
        QProgressBar {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            text-align: center;
            color: #e0e0e0;
        }
        QProgressBar::chunk {
            background-color: #4a9eff;
            border-radius: 2px;
        }
        QSplitter::handle {
            background-color: #3a3a3a;
            width: 2px;
        }
        QMenu {
            background-color: #2b2b2b;
            border: 1px solid #3a3a3a;
            color: #e0e0e0;
        }
        QMenu::item:selected {
            background-color: #264f78;
        }
        QDialog {
            background-color: #2b2b2b;
        }
        QGroupBox {
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 8px;
        }
        QGroupBox::title {
            color: #4a9eff;
        }
        QListWidget {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            color: #e0e0e0;
            selection-background-color: #264f78;
        }
        QComboBox {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            padding: 4px 8px;
            color: #e0e0e0;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            color: #e0e0e0;
            selection-background-color: #264f78;
        }
        QSpinBox {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            padding: 4px 8px;
            color: #e0e0e0;
        }
        QMessageBox {
            background-color: #2b2b2b;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
