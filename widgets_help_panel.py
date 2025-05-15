# widgets_help_panel.py
import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QTextBrowser, QLabel
from PyQt5.QtCore import QIODevice, QFile, QTextStream, Qt, QUrl
from PyQt5.QtGui import QDesktopServices

# 不再需要 get_project_root() 函数在这里，因为 project_root 会被传入

# load_html_for_help_panel 现在需要知道项目根目录以便正确构建路径
def load_html_for_help_panel(project_root_dir, file_name): # 增加 project_root_dir 参数
    """
    从项目的 'resources' 目录下加载HTML文件内容。
    project_root_dir: 项目的根目录绝对路径。
    file_name: HTML文件名 (例如 "manual.html")。
    """
    file_path = os.path.join(project_root_dir, "resources", file_name) # 使用传入的根目录

    content = (f"<h3>内容加载失败</h3>"
               f"<p>无法找到或读取帮助文件: '<code>{file_name}</code>'。</p>"
               f"<p>请确认它位于项目的 '<code>resources</code>' 文件夹下。</p>"
               f"<p>预期完整路径: <code>{file_path}</code></p>")
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                stream.setCodec("UTF-8")
                content = stream.readAll()
                file.close()
            else:
                content = (f"<h3>无法打开文件</h3>"
                           f"<p>文件 '<code>{file_path}</code>' 存在但无法打开。</p>"
                           f"<p>错误: {file.errorString()}</p>")
        except Exception as e:
            content = (f"<h3>读取错误</h3>"
                       f"<p>读取文件 '<code>{file_path}</code>' 时发生错误: {e}</p>")
    else:
        print(f"HelpPanel (load_html): HTML file not found at {file_path}")
    return content


class HelpPanel(QWidget):
    # *** 关键修改：构造函数接收 project_root 参数 ***
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root_dir = project_root # 保存传入的项目根目录
        self.setObjectName("HelpPanel")
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setObjectName("HelpTabWidget")

        # 使用保存的 self.project_root_dir 来构建资源搜索路径
        self.resources_search_path = os.path.join(self.project_root_dir, 'resources')
        print(f"HelpPanel (_init_ui): Resource search path set to: {self.resources_search_path}")

        # --- 1. 使用说明标签页 ---
        self.manual_browser = QTextBrowser()
        self.manual_browser.setOpenExternalLinks(True)
        self.manual_browser.setSearchPaths([self.resources_search_path])
        # 调用 load_html_for_help_panel 时传递 self.project_root_dir
        self.manual_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "manual.html"))
        self.tab_widget.addTab(self.manual_browser, "使用说明")

        # --- 2. 免责声明标签页 ---
        self.disclaimer_browser = QTextBrowser()
        self.disclaimer_browser.setOpenExternalLinks(True)
        self.disclaimer_browser.setSearchPaths([self.resources_search_path])
        self.disclaimer_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "disclaimer.html"))
        self.tab_widget.addTab(self.disclaimer_browser, "免责声明")

        # --- 3. 关于与支持 (包含赞助) 标签页 ---
        self.contact_about_browser = QTextBrowser()
        self.contact_about_browser.setOpenExternalLinks(True)
        self.contact_about_browser.setSearchPaths([self.resources_search_path])
        self.contact_about_browser.setHtml(load_html_for_help_panel(self.project_root_dir, "contact.html"))
        self.tab_widget.addTab(self.contact_about_browser, "关于与支持")

        main_layout.addWidget(self.tab_widget)

    def refresh_all_html_content(self):
        """如果HTML文件在程序运行时可能被外部修改，可以调用此方法刷新所有标签页的内容"""
        # 确保 self.resources_search_path 和 self.project_root_dir 已初始化
        if not hasattr(self, 'resources_search_path') or not hasattr(self, 'project_root_dir'):
            # 尝试重新获取/设置，但这通常应该在 __init__ 中完成
            # 如果是从旧的 save/load 状态恢复，可能需要特殊处理
            # 简单起见，如果未初始化，我们假设它可以通过某种方式获取
            # 但最佳实践是在 __init__ 中确保这些成员被设置
            current_dir_of_this_file = os.path.dirname(os.path.abspath(__file__))
            # 这是一个后备，假设 main_app.py 和此文件在同一目录
            self.project_root_dir = current_dir_of_this_file
            self.resources_search_path = os.path.join(self.project_root_dir, 'resources')
            print(f"HelpPanel (refresh_all_html_content): Re-initialized paths (fallback).")


        if self.tab_widget.widget(0) and isinstance(self.tab_widget.widget(0), QTextBrowser):
            self.tab_widget.widget(0).setSearchPaths([self.resources_search_path])
            self.tab_widget.widget(0).setHtml(load_html_for_help_panel(self.project_root_dir, "manual.html"))
        if self.tab_widget.widget(1) and isinstance(self.tab_widget.widget(1), QTextBrowser):
            self.tab_widget.widget(1).setSearchPaths([self.resources_search_path])
            self.tab_widget.widget(1).setHtml(load_html_for_help_panel(self.project_root_dir, "disclaimer.html"))
        if self.tab_widget.widget(2) and isinstance(self.tab_widget.widget(2), QTextBrowser):
            self.tab_widget.widget(2).setSearchPaths([self.resources_search_path])
            self.tab_widget.widget(2).setHtml(load_html_for_help_panel(self.project_root_dir, "contact.html"))