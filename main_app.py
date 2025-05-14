# main_app.py
import sys
import os
import traceback  # 导入 traceback 模块用于打印详细错误信息
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QStackedWidget, QMessageBox, QDialog, QTextBrowser,
                             QPushButton, QDialogButtonBox, QLabel, QFrame, QGroupBox,
                             QButtonGroup, QSizePolicy, QSpacerItem, QMenu)
from PyQt5.QtCore import Qt, QSettings, QUrl, QFile, QTextStream, QIODevice, QSize
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon  # 确保 QIcon 已导入

import ui_styles  # 你的样式模块
from widgets_basic_settings import BasicSettingsPanel
from widgets_help_panel import HelpPanel
from widgets_questionnaire_setup import QuestionnaireSetupWidget
from widgets_filling_process import FillingProcessWidget

MSedgedriverPathGlobal = None  # 全局驱动路径，主要由设置面板更新


# --- 辅助函数：load_html_from_file (用于加载帮助文档等) ---
def load_html_from_file(file_name):
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    # 假设 resources 文件夹与 main_app.py 在同一级的子目录中
    file_path = os.path.join(current_script_dir, "resources", file_name)
    content = f"<p>错误：无法加载内容文件 '{file_name}'。请确保文件存在于 'resources' 目录下。</p>"
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                stream.setCodec("UTF-8")  # 确保UTF-8编码
                content = stream.readAll()
                file.close()
            else:
                content = f"<p>错误：无法打开文件 '{file_path}'。错误: {file.errorString()}</p>"
        except Exception as e:
            content = f"<p>读取文件 '{file_path}' 时发生错误: {e}</p>"
    return content


# --- InfoDialog (用于显示HTML内容的简单对话框) ---
class InfoDialog(QDialog):
    def __init__(self, title, html_content_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 550)  # 合适的对话框大小
        self.setStyleSheet(ui_styles.get_app_qss())  # 应用全局样式

        layout = QVBoxLayout(self)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)  # 允许打开HTML中的外部链接
        html_content = load_html_from_file(html_content_file)
        self.text_browser.setHtml(html_content)
        layout.addWidget(self.text_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)  # 只显示关闭按钮
        button_box.rejected.connect(self.reject)  # 关闭按钮连接到reject槽
        layout.addWidget(button_box)


# --- AboutDialog (关于对话框) ---
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于与鼓励")
        self.setMinimumWidth(450)
        self.setStyleSheet(ui_styles.get_app_qss())  # 应用样式

        # --- 界面布局与内容 ---
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 头部：图标和标题
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        # About对话框内的图标路径 (来自resources/icons)
        app_icon_path_about = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icons",
                                           "app_icon.png")
        if os.path.exists(app_icon_path_about):
            pixmap = QPixmap(app_icon_path_about)
            icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header_layout.addWidget(icon_label)

        title_version_layout = QVBoxLayout()
        title_label = QLabel("问卷星助手 ")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        version_label = QLabel("版本: 1.0.4 (稳定版)")  # 版本号示例
        title_version_layout.addWidget(title_label)
        title_version_layout.addWidget(version_label)
        header_layout.addLayout(title_version_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line1)

        # 开发者和项目信息
        author_label = QLabel("<b>开发者:</b> [您的名字或团队名]")  # 请替换
        author_label.setTextFormat(Qt.RichText)
        main_layout.addWidget(author_label)
        github_label = QLabel(
            '<b>项目地址:</b> <a href="https://github.com/your_username/your_repo">GitHub源码</a>')  # 请替换为你的实际链接
        github_label.setTextFormat(Qt.RichText)
        github_label.setOpenExternalLinks(True)
        main_layout.addWidget(github_label)

        # 鼓励部分
        encourage_group = QGroupBox("鼓励开发者")
        encourage_layout = QVBoxLayout(encourage_group)
        encourage_text = QLabel(
            "如果您觉得这个工具对您有帮助，并且希望支持后续的开发和维护，可以通过以下方式鼓励一下作者：")
        encourage_text.setWordWrap(True)
        encourage_layout.addWidget(encourage_text)

        qr_and_buttons_layout = QHBoxLayout()
        qr_label = QLabel()
        # About对话框中仍然使用 encourage_qr.png (或者你可以改成也显示支付宝/微信)
        qr_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icons",
                                    "encourage_qr.png")
        if os.path.exists(qr_icon_path):
            qr_pixmap = QPixmap(qr_icon_path)
            if not qr_pixmap.isNull():
                qr_label.setPixmap(qr_pixmap.scaledToWidth(100, Qt.SmoothTransformation))
            else:
                qr_label.setText("二维码加载失败")
        else:
            qr_label.setText("(打赏二维码)")
            qr_label.setFixedSize(100, 100)
            qr_label.setAlignment(Qt.AlignCenter)
            qr_label.setStyleSheet("border: 1px dashed #ccc;")
        qr_and_buttons_layout.addWidget(qr_label, 0, Qt.AlignCenter)

        buttons_for_encourage_layout = QVBoxLayout()
        # donate_link_button1 = QPushButton("爱发电") # 如果有其他捐赠链接
        # donate_link_button1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("YOUR_DONATION_PLATFORM_LINK")))
        # buttons_for_encourage_layout.addWidget(donate_link_button1)
        buttons_for_encourage_layout.addStretch()
        qr_and_buttons_layout.addLayout(buttons_for_encourage_layout, 1)
        encourage_layout.addLayout(qr_and_buttons_layout)
        main_layout.addWidget(encourage_group)

        main_layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        main_layout.addWidget(button_box)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("问卷星助手")
        self.setMinimumSize(960, 720)

        # --- 设置窗口图标 ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 优先尝试 WJX.png (如果用户把它从 .jpg 改成了 .png 以获得更好效果)
        primary_icon_name = "WJX.png"
        secondary_icon_name = "WJX.jpg"  # 作为第二选择
        fallback_icon_path_in_resources = os.path.join(current_dir, "resources", "icons", "app_icon.png")

        window_icon_to_set = None

        # 1. 尝试主图标 (WJX.png)
        primary_icon_path = os.path.join(current_dir, primary_icon_name)
        if os.path.exists(primary_icon_path):
            window_icon_to_set = primary_icon_path
            print(f"MainWindow: 使用主窗口图标 '{primary_icon_path}'。")
        else:
            # 2. 尝试次要图标 (WJX.jpg)
            secondary_icon_path = os.path.join(current_dir, secondary_icon_name)
            if os.path.exists(secondary_icon_path):
                window_icon_to_set = secondary_icon_path
                print(f"MainWindow: 主图标 '{primary_icon_name}' 未找到，使用次要图标 '{secondary_icon_path}'。")
            else:
                # 3. 尝试资源文件夹中的后备图标
                if os.path.exists(fallback_icon_path_in_resources):
                    window_icon_to_set = fallback_icon_path_in_resources
                    print(f"MainWindow: 主图标和次要图标均未找到，使用资源后备图标 '{fallback_icon_path_in_resources}'。")
                else:
                    print(f"MainWindow: 所有指定窗口图标均未找到。将使用默认系统图标。")

        if window_icon_to_set:
            self.setWindowIcon(QIcon(window_icon_to_set))

        self.setGeometry(100, 100, 1100, 800)
        self.settings = QSettings("WJXHelperCo", "WJXNavEdition_v2")  # 更改应用名以确保配置隔离

        self.load_settings()
        self._init_ui_with_top_navigation()
        self.apply_styles()

    def load_settings(self):
        saved_theme = self.settings.value("theme", "经典默认")
        ui_styles.set_current_theme(saved_theme)
        global MSedgedriverPathGlobal
        MSedgedriverPathGlobal = self.settings.value("msedgedriver_path", None)

    def save_settings(self):
        self.settings.setValue("theme", ui_styles.CURRENT_THEME)
        print("MainWindow: 主题设置已保存。")  # 其他设置由面板保存

    def _init_ui_with_top_navigation(self):
        central_widget_container = QWidget()
        main_v_layout = QVBoxLayout(central_widget_container)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        main_v_layout.setSpacing(0)

        self.nav_bar_widget = QWidget()
        self.nav_bar_widget.setObjectName("TopNavigationBar")
        nav_bar_h_layout = QHBoxLayout(self.nav_bar_widget)
        nav_bar_h_layout.setContentsMargins(10, 2, 10, 0)
        nav_bar_h_layout.setSpacing(2)

        self.top_nav_button_group = QButtonGroup(self)
        self.top_nav_button_group.setExclusive(True)

        nav_config = [
            ("问卷配置", "panel_idx_questionnaire_setup", "edit_form.png"),
            ("开始运行", "panel_idx_filling_process", "play_arrow.png"),
            ("程序设置", "panel_idx_basic_settings", "settings.png"),
            ("使用帮助", "panel_idx_help", "help_outline.png"),
        ]
        self.nav_buttons = {}

        for text, panel_idx_attr, icon_file in nav_config:
            button = QPushButton(text)
            button.setProperty("class", "NavButton")
            button.setCheckable(True)
            button.setMinimumHeight(32)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            nav_button_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icons",
                                                icon_file)
            if os.path.exists(nav_button_icon_path):
                button.setIcon(QIcon(nav_button_icon_path))
                button.setIconSize(QSize(18, 18))
            nav_bar_h_layout.addWidget(button)
            self.top_nav_button_group.addButton(button)
            self.nav_buttons[panel_idx_attr] = button

        nav_bar_h_layout.addStretch(1)
        main_v_layout.addWidget(self.nav_bar_widget)

        self.main_content_stack = QStackedWidget()
        # 确保在创建 HelpPanel 时传递项目根目录 (如果 HelpPanel 需要它来定位资源)
        project_root = os.path.dirname(os.path.abspath(__file__))
        self.questionnaire_setup_panel = QuestionnaireSetupWidget(self)
        self.filling_process_panel = FillingProcessWidget(self)
        self.basic_settings_panel = BasicSettingsPanel(self.settings, self)
        self.help_panel = HelpPanel(project_root=project_root, parent=self)  # 传递 project_root

        self.panel_idx_questionnaire_setup = self.main_content_stack.addWidget(self.questionnaire_setup_panel)
        self.panel_idx_filling_process = self.main_content_stack.addWidget(self.filling_process_panel)
        self.panel_idx_basic_settings = self.main_content_stack.addWidget(self.basic_settings_panel)
        self.panel_idx_help = self.main_content_stack.addWidget(self.help_panel)

        main_v_layout.addWidget(self.main_content_stack, 1)
        self.setCentralWidget(central_widget_container)

        for panel_idx_attr, button in self.nav_buttons.items():
            target_panel_index = getattr(self, panel_idx_attr, -1)
            if target_panel_index != -1:
                if panel_idx_attr == "panel_idx_filling_process":
                    button.clicked.connect(self._handle_filling_navigation_click)
                    button.toggled.connect(
                        lambda checked, idx=target_panel_index: \
                            self.main_content_stack.setCurrentIndex(idx) if checked else None
                    )
                else:
                    button.toggled.connect(
                        lambda checked, idx=target_panel_index: \
                            self.main_content_stack.setCurrentIndex(idx) if checked else None
                    )

        self.basic_settings_panel.msedgedriver_path_changed.connect(self._handle_driver_path_update)
        self.basic_settings_panel.theme_changed_signal.connect(self._handle_theme_update)

        self.statusBar().showMessage("就绪")
        self.statusBar().setStyleSheet("QStatusBar { padding-left: 5px; }")

        if "panel_idx_questionnaire_setup" in self.nav_buttons:
            self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)

    def _handle_filling_navigation_click(self):
        print("MainWindow: _handle_filling_navigation_click - “开始运行”导航按钮被点击。")
        can_navigate_to_fill_panel = self._prepare_data_for_filling_panel()
        fill_button = self.nav_buttons.get("panel_idx_filling_process")
        setup_button = self.nav_buttons.get("panel_idx_questionnaire_setup")

        if can_navigate_to_fill_panel:
            print("  数据准备成功。尝试激活“开始运行”面板。")
            if fill_button and fill_button.isCheckable():
                if not fill_button.isChecked():
                    fill_button.setChecked(True)
                elif self.main_content_stack.currentIndex() != self.panel_idx_filling_process:
                    self.main_content_stack.setCurrentIndex(self.panel_idx_filling_process)
            else:
                print("  错误: 未找到“开始运行”按钮或按钮不可选中。")
        else:
            print("  数据准备失败。将激活“问卷配置”面板。")
            if setup_button and setup_button.isCheckable():
                setup_button.setChecked(True)
            else:
                print("  错误: 未找到“问卷配置”按钮或按钮不可选中。")

    def _handle_driver_path_update(self, new_path):
        global MSedgedriverPathGlobal
        if MSedgedriverPathGlobal != new_path:
            MSedgedriverPathGlobal = new_path
            self.statusBar().showMessage(f"驱动路径已更新: {new_path if new_path else '将从PATH查找'}", 3000)

    def _handle_theme_update(self, theme_name_cn):
        if ui_styles.CURRENT_THEME != theme_name_cn:
            if ui_styles.set_current_theme(theme_name_cn):
                self.apply_styles()
                self.statusBar().showMessage(f"界面主题已更改为: {theme_name_cn}", 3000)

    def apply_styles(self):
        current_qss = ui_styles.get_app_qss()
        self.setStyleSheet(current_qss)
        if hasattr(self, 'nav_bar_widget'):
            self.nav_bar_widget.style().unpolish(self.nav_bar_widget)
            self.nav_bar_widget.style().polish(self.nav_bar_widget)
            self.nav_bar_widget.update()
        if hasattr(self, 'main_content_stack'):
            for i in range(self.main_content_stack.count()):
                panel = self.main_content_stack.widget(i)
                if panel:
                    panel.style().unpolish(panel)
                    panel.style().polish(panel)
                    panel.update()

    def _prepare_data_for_filling_panel(self):
        print("MainWindow: _prepare_data_for_filling_panel - 开始准备数据...")
        parsed_q_data = self.questionnaire_setup_panel.get_parsed_questionnaire_data()
        user_raw_configs_template = self.questionnaire_setup_panel.get_user_raw_configurations_template()

        if not parsed_q_data or (isinstance(parsed_q_data, dict) and "error" in parsed_q_data):
            QMessageBox.warning(self, "操作受阻", "请先成功加载并解析一个问卷链接。")
            return False

        if not user_raw_configs_template:
            QMessageBox.warning(self, "操作受阻",
                                "未能获取有效的问卷填写配置模板。\n请确保“问卷配置”面板中的设置已正确生成模板，或模板不为空。")
            return False

        current_msedgedriver_path = self.settings.value("msedgedriver_path", "")
        if current_msedgedriver_path == "": current_msedgedriver_path = None

        current_basic_settings = {
            "msedgedriver_path": current_msedgedriver_path,
            "proxy": self.settings.value("proxy_address", ""),
            "num_threads": int(self.settings.value("num_threads", 1)),
            "num_fills_total": int(self.settings.value("num_fills", 1)),
            "headless": self.settings.value("headless_mode", True, type=bool)
        }

        self.filling_process_panel.prepare_for_filling(
            url=self.questionnaire_setup_panel.url_input.text(),
            parsed_questionnaire_data=parsed_q_data,
            user_raw_configurations_template=user_raw_configs_template,
            basic_settings=current_basic_settings
        )
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("数据已准备就绪，请切换到“开始运行”面板并点击开始。",
                                                                    3000)
        print("  数据准备完成并已传递给 FillingProcessPanel。")
        return True

    def closeEvent(self, event):
        if hasattr(self, 'filling_process_panel') and self.filling_process_panel.is_process_running:
            reply = QMessageBox.question(self, '任务运行中',
                                         "当前有填写任务正在进行，确定要退出吗？\n未完成的任务将会中止。",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            else:
                self.filling_process_panel.stop_all_workers_forcefully()
        self.save_settings()
        event.accept()


if __name__ == '__main__':
    def excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("--------------------- 未处理的全局异常 ---------------------")
        print(tb_str)
        print("------------------------------------------------------------")
        QApplication.quit()


    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())