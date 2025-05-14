# main_app.py
import sys
import os  # 新增导入 os模块，用于处理文件路径
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QStackedWidget, QMessageBox, QDialog, QTextBrowser,
                             QPushButton, QDialogButtonBox, QLabel, QGridLayout,QFrame,QGroupBox,
                             QHBoxLayout)  # 新增 QGridLayout
from PyQt5.QtCore import Qt, QSettings, QUrl, QFile, QTextStream, QIODevice  # 新增 QFile, QTextStream, QIODevice
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon  # QIcon 用于应用图标

import ui_styles
from widgets_basic_settings import BasicSettingsDialog  # 确保导入的是对话框版本
from widgets_questionnaire_setup import QuestionnaireSetupWidget
from widgets_filling_process import FillingProcessWidget

MSedgedriverPathGlobal = None


# --- 辅助函数：从文件加载HTML内容 ---
def load_html_from_file(file_name):
    """从指定文件加载HTML内容，文件应位于resources目录下"""
    # 获取当前脚本所在的目录
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建资源文件的完整路径
    file_path = os.path.join(current_script_dir, "resources", file_name)

    content = f"<p>错误：无法加载内容文件 '{file_name}'。请确保文件存在于 'resources' 目录下。</p>"
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                stream.setCodec("UTF-8")  # 确保以UTF-8读取
                content = stream.readAll()
                file.close()
            else:
                content = f"<p>错误：无法打开文件 '{file_path}'。错误: {file.errorString()}</p>"
        except Exception as e:
            content = f"<p>读取文件 '{file_path}' 时发生错误: {e}</p>"
    return content


# --- 通用信息展示对话框 (与之前相同) ---
class InfoDialog(QDialog):
    def __init__(self, title, html_content_file, parent=None):  # 修改为接收文件名
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 450)  # 调整对话框大小

        layout = QVBoxLayout(self)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)

        html_content = load_html_from_file(html_content_file)  # 从文件加载
        self.text_browser.setHtml(html_content)
        layout.addWidget(self.text_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


# --- 关于/鼓励作者对话框 (可以做得更丰富一些) ---
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于与鼓励")
        self.setMinimumWidth(450)  # 允许内容决定高度
        # self.setFixedSize(450, 350) # 可以取消固定大小，让布局自适应

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)  # 增加边距

        # 应用图标和标题
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        # 尝试加载应用图标 (假设放在 resources/icons/app_icon.png)
        app_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icons", "app_icon.png")
        if os.path.exists(app_icon_path):
            pixmap = QPixmap(app_icon_path)
            icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header_layout.addWidget(icon_label)

        title_version_layout = QVBoxLayout()
        title_label = QLabel("问卷星助手 ")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        title_version_layout.addWidget(title_label)
        version_label = QLabel("版本: 1.0.1 (持续优化中)")  # 更新版本示例
        title_version_layout.addWidget(version_label)
        header_layout.addLayout(title_version_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line1)

        # 开发者信息
        author_label = QLabel("<b>开发者:</b> [您的名字或团队名称]")  # 请替换
        author_label.setTextFormat(Qt.RichText)  # 允许HTML标签
        main_layout.addWidget(author_label)

        github_label = QLabel(
            '<b>项目地址:</b> <a href="https://github.com/[您的GitHub]/[您的项目]">在GitHub上查看源码</a>')  # 请替换
        github_label.setTextFormat(Qt.RichText)
        github_label.setOpenExternalLinks(True)
        main_layout.addWidget(github_label)

        # 鼓励信息
        encourage_group = QGroupBox("鼓励开发者")
        encourage_layout = QVBoxLayout(encourage_group)
        encourage_text = QLabel(
            "如果您觉得这个工具对您有帮助，并且希望支持后续的开发和维护，可以通过以下方式鼓励一下作者：")
        encourage_text.setWordWrap(True)
        encourage_layout.addWidget(encourage_text)

        # 示例：显示二维码图片和打赏链接按钮
        qr_and_buttons_layout = QHBoxLayout()
        qr_label = QLabel("（打赏二维码区域）")  # 提示文字
        # 尝试加载二维码图片
        qr_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icons",
                                    "encourage_qr.png")
        if os.path.exists(qr_icon_path):
            qr_pixmap = QPixmap(qr_icon_path)
            if not qr_pixmap.isNull():
                qr_label.setPixmap(qr_pixmap.scaledToWidth(100, Qt.SmoothTransformation))  # 调整宽度
                qr_label.setAlignment(Qt.AlignCenter)
            else:
                qr_label.setText("打赏二维码加载失败")
        else:
            qr_label.setText("（请在此放置打赏二维码图片）")
            qr_label.setWordWrap(True)
            qr_label.setFixedSize(120, 120)
            qr_label.setStyleSheet("border: 1px dashed #ccc; text-align: center;")

        qr_and_buttons_layout.addWidget(qr_label, 0, Qt.AlignCenter)  # 左侧二维码

        buttons_for_encourage_layout = QVBoxLayout()
        donate_link_button1 = QPushButton("通过爱发电鼓励")  # 示例
        donate_link_button1.setIcon(QIcon.fromTheme("emblem-favorite"))  # 尝试使用系统图标
        donate_link_button1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://afdian.net")))  # 替换链接
        buttons_for_encourage_layout.addWidget(donate_link_button1)

        donate_link_button2 = QPushButton("访问开发者主页")  # 示例
        donate_link_button2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://example.com")))  # 替换链接
        buttons_for_encourage_layout.addWidget(donate_link_button2)
        buttons_for_encourage_layout.addStretch()
        qr_and_buttons_layout.addLayout(buttons_for_encourage_layout, 1)  # 右侧按钮

        encourage_layout.addLayout(qr_and_buttons_layout)
        main_layout.addWidget(encourage_group)

        main_layout.addStretch()

        # 关闭按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        main_layout.addWidget(button_box)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("问卷填写助手 Pro")
        self.setMinimumSize(800, 600)  # 设置主窗口最小尺寸，避免启动时过小
        # 尝试加载应用图标
        app_icon_main_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icons",
                                          "app_icon.png")
        if os.path.exists(app_icon_main_path):
            self.setWindowIcon(QIcon(app_icon_main_path))

        self.setGeometry(100, 100, 1024, 768)  # 初始尺寸可以大一些
        self.settings = QSettings("WJXHelperCompany", "QuestionnaireFillerPro")  # 公司名和应用名建议用英文
        self.load_settings()
        self._init_ui()  # UI初始化应该在加载设置之后，应用样式之前
        self.apply_styles()

    def load_settings(self):
        saved_theme = self.settings.value("theme", "经典默认")
        ui_styles.set_current_theme(saved_theme)  # 先设置主题，后续apply_styles会用到
        global MSedgedriverPathGlobal
        MSedgedriverPathGlobal = self.settings.value("msedgedriver_path", None)

    def save_settings(self):
        self.settings.setValue("theme", ui_styles.CURRENT_THEME)
        self.settings.setValue("msedgedriver_path", MSedgedriverPathGlobal)

    def _init_ui(self):
        menubar = self.menuBar()

        # --- 文件菜单 ---
        file_menu = menubar.addMenu("文件(&F)")
        # “基本设置”移到文件菜单下，或者保持为顶级菜单
        basic_settings_action = file_menu.addAction("基本设置(&S)...")  # 加省略号表示会弹出对话框
        basic_settings_action.triggered.connect(self.show_basic_settings_dialog)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("退出(&X)")
        exit_action.triggered.connect(self.close)

        # --- 功能区菜单 ---
        view_menu = menubar.addMenu("视图(&V)")  # 将面板切换放到视图菜单下
        self.stacked_widget = QStackedWidget(self)
        self.setCentralWidget(self.stacked_widget)

        self.questionnaire_setup_panel = QuestionnaireSetupWidget(self)
        self.filling_process_panel = FillingProcessWidget(self)

        self.idx_questionnaire_setup = self.stacked_widget.addWidget(self.questionnaire_setup_panel)
        self.idx_filling_process = self.stacked_widget.addWidget(self.filling_process_panel)

        q_setup_action = view_menu.addAction("问卷配置面板(&Q)")
        q_setup_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(self.idx_questionnaire_setup))

        fill_panel_action = view_menu.addAction("填写进度面板(&P)")  # Panel
        fill_panel_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(self.idx_filling_process))

        # --- 执行菜单 ---
        run_menu = menubar.addMenu("执行(&R)")
        start_fill_action = run_menu.addAction("开始/继续填写(&S)")
        start_fill_action.triggered.connect(self.navigate_to_filling_process)  # 这个会切换到填写面板并准备

        # --- 其它菜单 ---
        other_menu = menubar.addMenu("帮助(&H)")  # “其它”改为“帮助”更标准

        manual_action = other_menu.addAction("使用说明(&M)")
        manual_action.triggered.connect(self.show_manual)

        disclaimer_action = other_menu.addAction("免责声明(&D)")
        disclaimer_action.triggered.connect(self.show_disclaimer)

        other_menu.addSeparator()

        contact_action = other_menu.addAction("交流与联系(&C)")
        contact_action.triggered.connect(self.show_contact_info)

        about_action = other_menu.addAction("关于(&A)")
        about_action.triggered.connect(self.show_about_dialog)

        self.stacked_widget.setCurrentIndex(self.idx_questionnaire_setup)
        self.statusBar().showMessage("准备就绪")

        # BasicSettingsDialog 的信号连接移到 show_basic_settings_dialog 方法中
        # 因为对话框是临时创建的。

    def show_basic_settings_dialog(self):
        # BasicSettingsDialog 不再是 self.basic_settings_panel
        # 它是一个独立的对话框
        dialog = BasicSettingsDialog(self, self.settings)
        dialog.msedgedriver_path_changed.connect(self.update_global_msedgedriver_path)
        dialog.theme_changed_signal.connect(self.change_theme_from_settings)

        # 确保应用当前主题到对话框
        dialog.setStyleSheet(ui_styles.get_app_qss())

        if dialog.exec_() == QDialog.Accepted:
            self.statusBar().showMessage("基本设置已更新。", 3000)
            # 如果有任何需要立即在主窗口响应的设置更改（除了主题和driver路径），可以在此处理
        else:
            self.statusBar().showMessage("基本设置未更改或已取消。", 3000)
            # 如果取消，确保主题恢复（如果对话框内部可以临时预览主题的话）
            # 我们的 BasicSettingsDialog 在选择主题时只更新预览，应用/确定才真正改全局
            # 所以这里可能不需要特别做什么，除非 BasicSettingsDialog 的实现改了全局主题但用户点了取消

    def update_global_msedgedriver_path(self, new_path):
        global MSedgedriverPathGlobal
        if MSedgedriverPathGlobal != new_path:  # 仅当路径实际改变时才提示和保存
            MSedgedriverPathGlobal = new_path
            self.statusBar().showMessage(f"EdgeDriver路径已更新: {new_path if new_path else '未设置'}", 3000)
            self.save_settings()

    def change_theme_from_settings(self, theme_name_cn):  # 参数改为中文名
        if ui_styles.CURRENT_THEME != theme_name_cn:
            if ui_styles.set_current_theme(theme_name_cn):
                self.apply_styles()
                self.statusBar().showMessage(f"主题已更改为: {theme_name_cn}", 3000)
                self.save_settings()

    def apply_styles(self):
        qss = ui_styles.get_app_qss()
        self.setStyleSheet(qss)
        # 更新已打开的子面板样式
        if hasattr(self, 'questionnaire_setup_panel'): self.questionnaire_setup_panel.setStyleSheet(qss)
        if hasattr(self, 'filling_process_panel'): self.filling_process_panel.setStyleSheet(qss)
        # 如果 BasicSettingsDialog 是非模态的并且希望它也实时更新，会复杂些
        # 但因为它是模态的，通常在它打开时应用一次样式即可

    # --- “其它”菜单槽函数 ---
    def show_disclaimer(self):
        dialog = InfoDialog("免责声明", "disclaimer.html", self)
        dialog.exec_()

    def show_manual(self):
        dialog = InfoDialog("使用说明", "manual.html", self)
        dialog.exec_()

    def show_about_dialog(self):
        dialog = AboutDialog(self)
        dialog.exec_()

    def show_contact_info(self):
        dialog = InfoDialog("交流与联系", "contact.html", self)
        dialog.exec_()

    def navigate_to_filling_process(self):
        parsed_q_data = self.questionnaire_setup_panel.get_parsed_questionnaire_data()
        user_raw_configs_template = self.questionnaire_setup_panel.get_user_raw_configurations_template()

        if not parsed_q_data or (isinstance(parsed_q_data, dict) and "error" in parsed_q_data):
            QMessageBox.warning(self, "无法开始", "请先成功加载并解析一个问卷URL。")
            self.stacked_widget.setCurrentIndex(self.idx_questionnaire_setup)
            return
        if not user_raw_configs_template:
            QMessageBox.warning(self, "无法开始", "未能获取用户问卷配置模板，请检查问卷是否已加载并配置。")
            self.stacked_widget.setCurrentIndex(self.idx_questionnaire_setup)
            return

        # 从 QSettings 获取最新的基础设置
        current_basic_settings = {
            "msedgedriver_path": self.settings.value("msedgedriver_path", ""),
            "proxy": self.settings.value("proxy_address", ""),  # 确保键名一致
            "num_threads": int(self.settings.value("num_threads", 2)),
            "num_fills_total": int(self.settings.value("num_fills", 10)),
            "headless": self.settings.value("headless_mode", True, type=bool)  # 从QSettings读取
        }

        self.filling_process_panel.prepare_for_filling(
            url=self.questionnaire_setup_panel.url_input.text(),
            parsed_questionnaire_data=parsed_q_data,
            user_raw_configurations_template=user_raw_configs_template,
            basic_settings=current_basic_settings
        )
        self.stacked_widget.setCurrentIndex(self.idx_filling_process)
        self.statusBar().showMessage("已切换到填写问卷面板，请配置填写参数并开始。")

    def closeEvent(self, event):
        if hasattr(self, 'filling_process_panel'):
            self.filling_process_panel.stop_all_workers_forcefully()
        reply = QMessageBox.question(self, '确认退出',
                                     "确定要退出程序吗？未完成的填写任务将中止。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.save_settings()
            event.accept()
        else:
            event.ignore()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())

