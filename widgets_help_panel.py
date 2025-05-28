# widgets_help_panel.py
import sys
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTextBrowser, QLabel,
                             QPushButton, QHBoxLayout, QSpacerItem, QSizePolicy, QMessageBox)
from PyQt5.QtCore import QIODevice, QFile, QTextStream, Qt, QUrl, QDateTime
from PyQt5.QtGui import QDesktopServices  # QIcon 不再需要


def local_resource_path(relative_path, project_root_fallback=None):
    try:
        base_path = sys._MEIPASS
    except Exception:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        elif project_root_fallback:
            base_path = project_root_fallback
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            # 根据实际结构调整 base_path = os.path.abspath(os.path.join(base_path, ".."))
    return os.path.join(base_path, relative_path)


def load_html_for_help_panel(project_root_dir, file_name):
    file_path = os.path.join(project_root_dir, "resources", file_name)
    content = (f"<h3>内容加载失败</h3><p>无法找到帮助文件: '{file_name}'.</p><p>路径: {file_path}</p>")
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file);
                stream.setCodec("UTF-8");
                content = stream.readAll();
                file.close()
            else:
                content = f"<h3>无法打开文件</h3><p>文件 '{file_path}' 存在但无法打开: {file.errorString()}</p>"
        except Exception as e:
            content = f"<h3>读取错误</h3><p>读取 '{file_path}' 时出错: {e}</p>"
    return content


class HelpPanel(QWidget):
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root_dir = project_root
        self.main_window_ref = parent
        self.setObjectName("HelpPanel")
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QVBoxLayout(self);
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_widget = QTabWidget();
        self.tab_widget.setDocumentMode(True);
        self.tab_widget.setObjectName("HelpTabWidget")
        search_path_base = self.project_root_dir if self.project_root_dir else os.path.dirname(
            os.path.abspath(__file__))

        self.manual_browser = QTextBrowser();
        self.manual_browser.setOpenExternalLinks(True)
        self.manual_browser.setSearchPaths([os.path.join(search_path_base, 'resources')])
        self.manual_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "manual.html"))
        self.tab_widget.addTab(self.manual_browser, "使用说明")

        self.disclaimer_browser = QTextBrowser();
        self.disclaimer_browser.setOpenExternalLinks(True)
        self.disclaimer_browser.setSearchPaths([os.path.join(search_path_base, 'resources')])
        self.disclaimer_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "disclaimer.html"))
        self.tab_widget.addTab(self.disclaimer_browser, "免责声明")

        self.contact_about_browser = QTextBrowser();
        self.contact_about_browser.setOpenExternalLinks(True)
        self.contact_about_browser.setSearchPaths([os.path.join(search_path_base, 'resources')])
        self.contact_about_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "contact.html"))
        self.tab_widget.addTab(self.contact_about_browser, "关于与支持")

        self.update_page_widget = QWidget()
        self._init_update_page_ui(self.update_page_widget)
        self.tab_widget.addTab(self.update_page_widget, "版本与更新")
        main_layout.addWidget(self.tab_widget)
        self.tab_widget.setCurrentIndex(0)

    def _init_update_page_ui(self, page_widget):
        layout = QVBoxLayout(page_widget);
        layout.setContentsMargins(20, 20, 20, 20);
        layout.setAlignment(Qt.AlignCenter)
        current_version = self.main_window_ref.CURRENT_APP_VERSION if self.main_window_ref and hasattr(
            self.main_window_ref, 'CURRENT_APP_VERSION') else "未知"
        info_layout = QVBoxLayout();
        info_layout.setAlignment(Qt.AlignCenter)
        title_label = QLabel("版本信息");
        title_label.setStyleSheet("font-size:16pt;font-weight:bold;margin-bottom:10px;");
        title_label.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(title_label)
        name_label = QLabel("软件名称：问卷星助手 (WJXHelper)");
        name_label.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(name_label)
        self.current_version_display_label = QLabel(f"当前版本：{current_version}");
        self.current_version_display_label.setAlignment(Qt.AlignCenter)
        self.current_version_display_label.setStyleSheet("margin-bottom:10px;")
        info_layout.addWidget(self.current_version_display_label)
        self.version_status_text_label = QLabel("点击下方按钮检查更新。");
        self.version_status_text_label.setAlignment(Qt.AlignCenter)
        self.version_status_text_label.setWordWrap(True);
        self.version_status_text_label.setStyleSheet("margin-bottom:20px;")
        info_layout.addWidget(self.version_status_text_label)
        layout.addLayout(info_layout)
        self.update_now_button = QPushButton("立即更新");
        self.update_now_button.setMinimumHeight(35)
        self.update_now_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        button_h_layout = QHBoxLayout();
        button_h_layout.addStretch();
        button_h_layout.addWidget(self.update_now_button);
        button_h_layout.addStretch()
        layout.addLayout(button_h_layout);
        layout.addStretch(1)

    def _connect_signals(self):
        if hasattr(self, 'update_now_button'):
            self.update_now_button.clicked.connect(self._trigger_update_process_from_help_panel)

    def _trigger_update_process_from_help_panel(self):
        if self.main_window_ref and hasattr(self.main_window_ref, 'manual_check_for_updates'):
            self.version_status_text_label.setText("版本状态：正在检查更新，请稍候...")
            self.main_window_ref.manual_check_for_updates(
                silent_if_no_update=False,
                update_help_panel_directly=False  # 结果由MainWindow弹窗显示，HelpPanel不再复杂更新
            )

    # --- 正确实现 display_update_info ---
    def display_update_info(self, is_latest, server_info=None, current_app_version_str=None):
        """
        由MainWindow调用，用于在HelpPanel的“版本与更新”页面更新状态文本。
        """
        if not hasattr(self, 'version_status_text_label'):  # 健壮性检查
            return

        if current_app_version_str is None:
            current_app_version_str = self.main_window_ref.CURRENT_APP_VERSION if self.main_window_ref else "未知"

        # 更新当前版本显示（如果它可能变化的话，虽然不太可能）
        if hasattr(self, 'current_version_display_label'):
            self.current_version_display_label.setText(f"当前版本：{current_app_version_str}")

        if server_info and server_info.get("status") == "checking":
            self.version_status_text_label.setText("版本状态：正在检查更新...")
            return

        if is_latest:
            self.version_status_text_label.setText("版本状态：已是最新版本。")
        else:
            if server_info and "error" not in server_info:
                latest_version = server_info.get("latest_version", "未知")
                # 根据您的要求，详细信息和下载按钮由MainWindow的弹窗处理
                # HelpPanel只显示一个简单的提示，引导用户点击“立即更新”按钮
                self.version_status_text_label.setText(
                    f"版本状态：可能存在新版本 (服务器最新: {latest_version})。请点击“立即更新”按钮获取详情。")
            elif server_info and "error" in server_info:
                self.version_status_text_label.setText(
                    f"<font color='red'>检查更新时出错：{server_info['error']}</font>")
            else:
                self.version_status_text_label.setText("<font color='red'>无法获取版本信息，请稍后重试。</font>")

    # --- END display_update_info ---

    def refresh_current_version_display(self):  # (保持不变)
        if hasattr(self, 'current_version_display_label') and self.main_window_ref and hasattr(self.main_window_ref,
                                                                                               'CURRENT_APP_VERSION'):
            self.current_version_display_label.setText(f"当前版本：{self.main_window_ref.CURRENT_APP_VERSION}")

    def refresh_all_html_content(self):  # (保持不变)
        if not self.project_root_dir: return
        if self.manual_browser: self.manual_browser.setSearchPaths(
            [os.path.join(self.project_root_dir, 'resources')]); self.manual_browser.setHtml(
            load_html_for_help_panel(self.project_root_dir, "manual.html"))
        if self.disclaimer_browser: self.disclaimer_browser.setSearchPaths(
            [os.path.join(self.project_root_dir, 'resources')]); self.disclaimer_browser.setHtml(
            load_html_for_help_panel(self.project_root_dir, "disclaimer.html"))
        if self.contact_about_browser: self.contact_about_browser.setSearchPaths(
            [os.path.join(self.project_root_dir, 'resources')]); self.contact_about_browser.setHtml(
            load_html_for_help_panel(self.project_root_dir, "contact.html"))
        self.refresh_current_version_display()