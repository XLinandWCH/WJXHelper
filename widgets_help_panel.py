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

        self.ai_manual_browser = QTextBrowser();
        self.ai_manual_browser.setOpenExternalLinks(True)
        self.ai_manual_browser.setSearchPaths([os.path.join(search_path_base, 'resources')])
        self.ai_manual_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "ai_manual.html"))
        self.tab_widget.addTab(self.ai_manual_browser, "AI助手说明")

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

        main_layout.addWidget(self.tab_widget)
        self.tab_widget.setCurrentIndex(0)

    def _connect_signals(self):
        pass  # No signals to connect in this simplified version

    def refresh_all_html_content(self):
        if not self.project_root_dir: return
        search_path = os.path.join(self.project_root_dir, 'resources')
        
        if hasattr(self, 'manual_browser'):
            self.manual_browser.setSearchPaths([search_path])
            self.manual_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "manual.html"))
        
        if hasattr(self, 'ai_manual_browser'):
            self.ai_manual_browser.setSearchPaths([search_path])
            self.ai_manual_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "ai_manual.html"))
            
        if hasattr(self, 'disclaimer_browser'):
            self.disclaimer_browser.setSearchPaths([search_path])
            self.disclaimer_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "disclaimer.html"))
            
        if hasattr(self, 'contact_about_browser'):
            self.contact_about_browser.setSearchPaths([search_path])
            self.contact_about_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "contact.html"))