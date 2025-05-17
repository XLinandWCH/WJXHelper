# main_app.py
import sys
import os
import traceback
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QStackedWidget, QMessageBox, QDialog, QTextBrowser,
                             QPushButton, QDialogButtonBox, QLabel, QFrame, QGroupBox,
                             QButtonGroup, QSizePolicy, QSpacerItem, QMenu)
from PyQt5.QtCore import Qt, QSettings, QUrl, QFile, QTextStream, QIODevice, QSize, QTimer
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon

import ui_styles
from widgets_basic_settings import BasicSettingsPanel
from widgets_help_panel import HelpPanel
from widgets_questionnaire_setup import QuestionnaireSetupWidget
from widgets_filling_process import FillingProcessWidget  # 确保这个import正确
from activation_dialog import ActivationDialog
import time

MSedgedriverPathGlobal = None
TOTAL_FILLS_LIMIT_UNACTIVATED = 500  # 未激活状态下的总填写次数限制
ACTIVATIONS_JSON_FILENAME = "activations.json"  # 激活信息JSON文件名


def load_html_from_file(file_name):
    # 从资源文件加载HTML内容
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_script_dir, "resources", file_name)
    content = f"<p>错误：无法加载内容文件 '{file_name}'。</p>"
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                stream.setCodec("UTF-8")  # 确保使用UTF-8编码读取
                content = stream.readAll()
                file.close()
            else:
                content = f"<p>错误：无法打开文件 '{file_path}'。错误: {file.errorString()}</p>"
        except Exception as e:
            content = f"<p>读取文件 '{file_path}' 时发生错误: {e}</p>"
    return content


class InfoDialog(QDialog):  # 信息对话框，无需修改
    def __init__(self, title, html_content_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 550)
        self.setStyleSheet(ui_styles.get_app_qss())  # 应用QSS样式
        layout = QVBoxLayout(self)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)  # 允许打开外部链接
        html_content = load_html_from_file(html_content_file)
        self.text_browser.setHtml(html_content)
        layout.addWidget(self.text_browser)
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)  # 关闭按钮连接到reject
        layout.addWidget(button_box)


class AboutDialog(QDialog):  # 关于对话框，无需修改
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于与鼓励")
        self.setMinimumWidth(450)
        self.setStyleSheet(ui_styles.get_app_qss())
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        project_root = parent.project_root_dir if parent and hasattr(parent, 'project_root_dir') else os.path.dirname(
            os.path.abspath(__file__))
        app_icon_path_about = os.path.join(project_root, "resources", "icons", "app_icon.png")
        if os.path.exists(app_icon_path_about):
            pixmap = QPixmap(app_icon_path_about)
            icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header_layout.addWidget(icon_label)
        title_version_layout = QVBoxLayout()
        title_label = QLabel("问卷星助手 ")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        version_label = QLabel("版本: 1.1.0 (UI响应与限制优化)")  # 版本信息
        title_version_layout.addWidget(title_label)
        title_version_layout.addWidget(version_label)
        header_layout.addLayout(title_version_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line1)
        author_label = QLabel("<b>开发者:</b> XLin & WCH")
        author_label.setTextFormat(Qt.RichText)
        main_layout.addWidget(author_label)
        github_label = QLabel('<b>项目地址:</b> <a href="https://github.com/XLinandWCH/WJXHelper">GitHub源码</a>')
        github_label.setTextFormat(Qt.RichText)
        github_label.setOpenExternalLinks(True)
        main_layout.addWidget(github_label)
        encourage_group = QGroupBox("鼓励开发者")
        encourage_layout = QVBoxLayout(encourage_group)
        encourage_text = QLabel(
            "如果您觉得这个工具对您有帮助，并且希望支持后续的开发和维护，可以通过以下方式鼓励一下作者：")
        encourage_text.setWordWrap(True)
        encourage_layout.addWidget(encourage_text)
        qr_and_buttons_layout = QHBoxLayout()
        qr_label = QLabel()
        # 此处的二维码 "为爱发电.png" 是关于对话框中的打赏码，与激活流程中的支付码分离
        qr_icon_path = os.path.join(project_root, "resources", "icons", "为爱发电.png")
        if os.path.exists(qr_icon_path):
            qr_pixmap = QPixmap(qr_icon_path)
            if not qr_pixmap.isNull():
                qr_label.setPixmap(qr_pixmap.scaledToWidth(200, Qt.SmoothTransformation))
            else:
                qr_label.setText("二维码加载失败")
        else:
            qr_label.setText("(打赏二维码)")
            qr_label.setFixedSize(200, 200)
            qr_label.setAlignment(Qt.AlignCenter)
            qr_label.setStyleSheet("border: 1px dashed #ccc;")
        qr_and_buttons_layout.addWidget(qr_label, 0, Qt.AlignCenter)
        buttons_for_encourage_layout = QVBoxLayout()
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
        self.project_root_dir = os.path.dirname(os.path.abspath(__file__))  # 项目根目录
        self.activations_file_path = os.path.join(self.project_root_dir, ACTIVATIONS_JSON_FILENAME)  # 激活文件路径

        primary_icon_name = "WJX.png"
        secondary_icon_name = "WJX.jpg"
        fallback_icon_path_in_resources = os.path.join(self.project_root_dir, "resources", "icons", "app_icon.png")
        window_icon_to_set = None
        # --- 图标设置逻辑 ---
        primary_icon_path = os.path.join(self.project_root_dir, primary_icon_name)
        if os.path.exists(primary_icon_path):
            window_icon_to_set = primary_icon_path
        else:
            secondary_icon_path = os.path.join(self.project_root_dir, secondary_icon_name)
            if os.path.exists(secondary_icon_path):
                window_icon_to_set = secondary_icon_path
            elif os.path.exists(fallback_icon_path_in_resources):
                window_icon_to_set = fallback_icon_path_in_resources
        if window_icon_to_set: self.setWindowIcon(QIcon(window_icon_to_set))

        self.setGeometry(100, 100, 1100, 800)
        self.settings = QSettings("WJXHelperCo", "WJXNavEdition_v3.6_PaymentActivation")  # QSettings 用于存储程序设置

        # --- 测试重置代码块 (按需启用) ---
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!!!!!!!!!! 测试模式：正在强制重置激活状态和全局填写次数!!!!!!!!!!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        self.settings.setValue("global_total_fills", 0)
        self.settings.setValue("activated_uuid", None)
        self.settings.sync()
        # --- 测试代码块结束 ---

        self.global_total_fills_count = 0  # 全局总填写次数
        self.is_activated = False  # 程序是否激活
        self.activated_uuid = None  # 已激活的UUID
        self.activation_expiry_timestamp = 0.0  # 激活到期时间戳
        self._valid_activations_from_json = {}  # 从JSON文件加载的有效激活信息

        self.load_settings_and_activations()  # 加载设置和激活信息
        self._init_ui_with_top_navigation()  # 初始化UI
        self.apply_styles()  # 应用样式

        self.activation_check_timer = QTimer(self)  # 定时器，用于周期性检查激活状态
        self.activation_check_timer.timeout.connect(self.recheck_activation_status_from_json)
        self.activation_check_timer.start(5 * 60 * 1000)  # 每5分钟检查一次
        self.recheck_activation_status_from_json()  # 初始检查一次

    def _load_json_activations_data(self):  # 从JSON文件加载激活数据
        if os.path.exists(self.activations_file_path):
            try:
                with open(self.activations_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"主窗口调试: 读取或解析 {self.activations_file_path} 失败: {e}")
        else:
            print(f"主窗口调试: 警告 - 激活文件 {self.activations_file_path} 未找到。")
        return {}

    def load_settings_and_activations(self):  # 加载程序设置和激活状态
        # print("主窗口调试: load_settings_and_activations 调用。")
        saved_theme = self.settings.value("theme", "经典默认")
        ui_styles.set_current_theme(saved_theme)
        global MSedgedriverPathGlobal
        MSedgedriverPathGlobal = self.settings.value("msedgedriver_path", None)
        self.global_total_fills_count = self.settings.value("global_total_fills", 0, type=int)
        self.activated_uuid = self.settings.value("activated_uuid", None)
        # print(f"  主窗口调试: 加载的 global_total_fills: {self.global_total_fills_count}, activated_uuid: {self.activated_uuid}")
        self._valid_activations_from_json = self._load_json_activations_data()
        self.recheck_activation_status_from_json()

    def save_settings(self):  # 保存程序设置
        self.settings.setValue("theme", ui_styles.CURRENT_THEME)
        self.settings.setValue("global_total_fills", self.global_total_fills_count)
        self.settings.setValue("activated_uuid", self.activated_uuid)
        self.settings.sync()  # 确保设置已写入

    def recheck_activation_status_from_json(self):  # 重新检查激活状态(从JSON文件)
        previously_activated_state = self.is_activated
        current_activated_uuid_before_recheck = self.activated_uuid
        self._valid_activations_from_json = self._load_json_activations_data()  # 重新加载激活文件
        self.is_activated = False
        self.activation_expiry_timestamp = 0.0

        if self.activated_uuid and self.activated_uuid in self._valid_activations_from_json:
            entry = self._valid_activations_from_json[self.activated_uuid]
            validity_code_json = None
            # 兼容旧格式 (直接是有效期字符串) 和新格式 (字典包含validity_code)
            if isinstance(entry, dict):
                validity_code_json = entry.get("validity_code", "").upper()
            elif isinstance(entry, str):  # 兼容旧的直接存储有效期代码的格式
                validity_code_json = entry.upper()

            if validity_code_json:
                now = time.time()
                calculated_expiry_ts = 0.0
                if validity_code_json == "UNL":  # 永久激活
                    calculated_expiry_ts = now + (365 * 20 * 24 * 60 * 60)  # 约20年
                else:
                    # 解析有效期代码，如 "7D", "1M", "24H"
                    val_str = "".join(filter(str.isdigit, validity_code_json))
                    unit = "".join(filter(str.isalpha, validity_code_json)).upper()
                    if val_str.isdigit() and int(val_str) > 0:
                        val = int(val_str)
                        seconds_multiplier = {'H': 3600, 'D': 86400, 'M': 30 * 86400, 'Y': 365 * 86400}.get(unit, 0)
                        if seconds_multiplier > 0:
                            # 重要: 此处有效期是基于 *当前时间* + 有效期时长
                            # 如果JSON中已有签发时间，并且希望基于签发时间计算，则逻辑需调整
                            # 当前实现: 每次检查都刷新有效期（如果基于签发时间，则该码的过期时间是固定的）
                            # 为了简化，我们假设 validity_code 指的是 *从激活时刻起* 的有效期
                            # 或者更准确地说，只要码在json里且未到期，就认为是激活的。
                            # 此处使用从JSON加载时的签发时间 (如果存在)
                            issue_ts = 0.0
                            if isinstance(entry, dict) and "issue_timestamp_utc" in entry:
                                issue_ts = float(entry["issue_timestamp_utc"])

                            if issue_ts > 0:  # 如果有签发时间，则基于签发时间计算
                                calculated_expiry_ts = issue_ts + (val * seconds_multiplier)
                            else:  # 否则（旧格式或无签发时间），基于当前时间 + 持续时间（这会导致有效期被“刷新”）
                                # 为了避免“刷新”，对于没有 issue_timestamp_utc 的旧数据，可以考虑不激活或给个固定短期
                                # 但当前我们还是信任这个码，并假设它是从现在开始有效的，如果它是旧格式。
                                # 更好的做法是所有激活码都带签发时间。
                                # 这里我们保持原逻辑，如果json里有这个码，且算出来没过期，就激活。
                                # 对于新生成的码，ActivationDialog会写入issue_timestamp_utc
                                calculated_expiry_ts = now + (val * seconds_multiplier)  # 保持现有逻辑：如果没签发时间戳，就当它是“可续期”的

                if calculated_expiry_ts > now:
                    self.is_activated = True
                    self.activation_expiry_timestamp = calculated_expiry_ts
                else:  # 已过期
                    if previously_activated_state:  # 如果之前是激活的，现在过期了
                        QMessageBox.warning(self, "激活已过期",
                                            f"已激活的码 (UUID: {self.activated_uuid[:8]}...) 根据最新激活文件已过期或有效期配置错误。")
                    self.activated_uuid = None  # 清除已激活的UUID
            else:  # validity_code_json 无效或缺失
                if previously_activated_state: print(
                    f"  主窗口调试: UUID '{self.activated_uuid}' 在JSON中，但条目格式错误或有效期代码缺失。")
                self.activated_uuid = None

        # 如果之前记录的 activated_uuid 在 json 文件中找不到了 (可能被手动删除)
        if current_activated_uuid_before_recheck and not self.activated_uuid and previously_activated_state:
            QMessageBox.warning(self, "激活已失效",
                                f"之前激活的码 (UUID: {current_activated_uuid_before_recheck[:8]}...) 可能已从有效列表移除或已过期。")

        self.save_settings()  # 保存激活状态的变化
        self._update_window_title_with_activation_status()

    def _update_window_title_with_activation_status(self):  # 更新窗口标题以反映激活状态
        base_title = "问卷星助手"
        if self.is_activated and self.activation_expiry_timestamp > 0:
            expiry_date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.activation_expiry_timestamp))
            uuid_disp = f" (UUID: {self.activated_uuid[:8]}...)" if self.activated_uuid else ""
            self.setWindowTitle(f"{base_title} (已激活{uuid_disp} - 至 {expiry_date_str})")
        else:
            remaining = TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count
            remaining = max(0, remaining)  # 确保不为负
            self.setWindowTitle(f"{base_title} (未激活 - 剩余免费: {remaining}次)")

    def increment_global_fill_count(self):  # 增加全局填写次数（未激活时）
        if not self.is_activated:
            self.global_total_fills_count += 1
            # print(f"主窗口调试: 未激活状态下，全局填写次数增加到 {self.global_total_fills_count}。")
        self.save_settings()
        self._update_window_title_with_activation_status()

    def get_remaining_free_fills(self):  # 获取剩余免费填写次数
        if self.is_activated:
            return float('inf')  # 已激活则无限次
        return max(0, TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count)

    def _can_proceed_with_filling(self):  # 检查是否可以继续填写（激活或有免费次数）
        # print("主窗口调试: _can_proceed_with_filling 调用。")
        self.recheck_activation_status_from_json()  # 每次检查前都刷新激活状态
        if self.is_activated:
            # print("  主窗口调试: _can_proceed_with_filling: 已激活。返回 True。")
            return True

        remaining_fills = self.get_remaining_free_fills()
        # print(f"  主窗口调试: _can_proceed_with_filling: 未激活。剩余免费次数: {remaining_fills}")
        if remaining_fills > 0:
            # print("  主窗口调试: _can_proceed_with_filling: 未激活，但有免费次数。返回 True。")
            return True

        # print("  主窗口调试: _can_proceed_with_filling: 未激活且无免费次数。弹出激活对话框。")
        # 没有免费次数了，弹出激活对话框
        dialog = ActivationDialog(project_root_dir=self.project_root_dir, parent=self)
        if dialog.exec_() == QDialog.Accepted:  # 如果用户在对话框中成功激活
            activated_uuid_dlg, expiry_ts_dlg_from_dialog = dialog.get_activation_details()
            if activated_uuid_dlg and expiry_ts_dlg_from_dialog:
                self.activated_uuid = activated_uuid_dlg  # 保存激活的UUID
                # self.activation_expiry_timestamp = expiry_ts_dlg_from_dialog # 这个由 recheck 更新
                self.save_settings()
                self.recheck_activation_status_from_json()  # 再次检查以更新 is_activated 和 expiry_timestamp
                if self.is_activated:
                    QMessageBox.information(self, "激活成功", "激活已完成，您可以继续使用了！")
                    return True
                else:
                    QMessageBox.warning(self, "激活失败", "激活未能最终确认或已立即失效，请检查激活码或联系支持。")
                    return False
        else:  # 用户关闭了激活对话框或未成功激活
            QMessageBox.warning(self, "操作受限",
                                f"免费填写已达 {TOTAL_FILLS_LIMIT_UNACTIVATED} 次上限。请激活软件或检查激活状态。")
        return False

    def _init_ui_with_top_navigation(self):  # 初始化带顶部导航栏的UI
        central_widget_container = QWidget()
        main_v_layout = QVBoxLayout(central_widget_container)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        main_v_layout.setSpacing(0)

        # --- 顶部导航栏 ---
        self.nav_bar_widget = QWidget()
        self.nav_bar_widget.setObjectName("TopNavigationBar")  # 用于QSS选择器
        nav_bar_h_layout = QHBoxLayout(self.nav_bar_widget)
        nav_bar_h_layout.setContentsMargins(10, 2, 10, 0)
        nav_bar_h_layout.setSpacing(2)

        self.top_nav_button_group = QButtonGroup(self)  # 按钮组，确保单选
        self.top_nav_button_group.setExclusive(True)

        nav_config = [  # 导航按钮配置 (文本, 面板索引属性名, 图标文件名)
            ("问卷配置", "panel_idx_questionnaire_setup", "edit_form.png"),
            ("开始运行", "panel_idx_filling_process", "play_arrow.png"),
            ("程序设置", "panel_idx_basic_settings", "settings.png"),
            ("使用帮助", "panel_idx_help", "help_outline.png"),
        ]
        self.nav_buttons = {}  # 存储导航按钮

        for text, panel_idx_attr, icon_file in nav_config:
            button = QPushButton(text)
            button.setProperty("class", "NavButton")  # 用于QSS
            button.setCheckable(True)  # 可选中状态
            button.setMinimumHeight(32)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            icon_path = os.path.join(self.project_root_dir, "resources", "icons", icon_file)
            if os.path.exists(icon_path):
                button.setIcon(QIcon(icon_path))
                button.setIconSize(QSize(18, 18))
            nav_bar_h_layout.addWidget(button)
            self.top_nav_button_group.addButton(button)
            self.nav_buttons[panel_idx_attr] = button

        nav_bar_h_layout.addStretch(1)  # 右侧空白伸展
        main_v_layout.addWidget(self.nav_bar_widget)

        # --- 内容堆叠窗口 ---
        self.main_content_stack = QStackedWidget()
        self.questionnaire_setup_panel = QuestionnaireSetupWidget(self)
        self.filling_process_panel = FillingProcessWidget(self)  # 创建实例
        self.basic_settings_panel = BasicSettingsPanel(self.settings, self)
        self.help_panel = HelpPanel(project_root=self.project_root_dir, parent=self)

        # 将面板添加到堆叠窗口并获取其索引
        self.panel_idx_questionnaire_setup = self.main_content_stack.addWidget(self.questionnaire_setup_panel)
        self.panel_idx_filling_process = self.main_content_stack.addWidget(self.filling_process_panel)
        self.panel_idx_basic_settings = self.main_content_stack.addWidget(self.basic_settings_panel)
        self.panel_idx_help = self.main_content_stack.addWidget(self.help_panel)

        main_v_layout.addWidget(self.main_content_stack, 1)  # 内容区域占据剩余空间
        self.setCentralWidget(central_widget_container)

        # --- 连接导航按钮的 toggled 信号 ---
        for panel_idx_attr, button in self.nav_buttons.items():
            target_idx = getattr(self, panel_idx_attr, -1)  # 获取面板索引
            if target_idx != -1:
                # 使用 lambda 传递额外参数 (目标索引, 按钮属性名)
                button.toggled.connect(lambda checked, idx=target_idx, btn_attr=panel_idx_attr: \
                                           self._nav_button_toggled(checked, idx, btn_attr))

        # --- 连接子面板的信号 ---
        self.basic_settings_panel.msedgedriver_path_changed.connect(self._handle_driver_path_update)
        self.basic_settings_panel.theme_changed_signal.connect(self._handle_theme_update)

        self.statusBar().showMessage("就绪")
        self.statusBar().setStyleSheet("QStatusBar { padding-left: 5px; }")

        # 默认选中第一个导航按钮 (问卷配置)
        if "panel_idx_questionnaire_setup" in self.nav_buttons:
            self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)

        self._update_window_title_with_activation_status()  # 初始化窗口标题

    def _nav_button_toggled(self, checked, panel_index_to_set, button_attribute_name):  # 导航按钮切换处理
        if not checked:  # 只处理选中状态
            return

        # print(f"主窗口调试: 导航按钮 '{button_attribute_name}' 切换, 选中: {checked}, 目标索引: {panel_index_to_set}")

        if button_attribute_name == "panel_idx_filling_process":  # 如果是切换到“开始运行”面板
            # print("  主窗口调试: 尝试导航到“开始运行”面板。")
            can_proceed = self._can_proceed_with_filling()  # 检查激活/免费次数
            # print(f"  主窗口调试: _can_proceed_with_filling() 返回: {can_proceed}")
            if can_proceed:
                data_prepared_ok = self._prepare_data_for_filling_panel()  # 准备运行数据
                # print(f"  主窗口调试: _prepare_data_for_filling_panel() 返回: {data_prepared_ok}")
                if data_prepared_ok:
                    # print("    主窗口调试: 数据准备完成，切换到“开始运行”面板。")
                    self.main_content_stack.setCurrentIndex(panel_index_to_set)
                else:
                    # print("    主窗口调试: 数据准备失败。切换回配置面板。")
                    QMessageBox.warning(self, "无法开始", "问卷数据准备失败，请检查“问卷配置”面板。")
                    self.nav_buttons["panel_idx_filling_process"].setChecked(False)  # 取消选中“开始运行”
                    # 确保“问卷配置”被选中（如果它当前未被选中的话）
                    if not self.nav_buttons["panel_idx_questionnaire_setup"].isChecked():
                        self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
            else:  # 不能继续（未激活且无免费次数，且用户未在弹窗中激活）
                # print("    主窗口调试: _can_proceed_with_filling 返回 False。切换回配置面板。")
                self.nav_buttons["panel_idx_filling_process"].setChecked(False)  # 取消选中“开始运行”
                # 确保“问卷配置”被选中
                if not self.nav_buttons["panel_idx_questionnaire_setup"].isChecked():
                    self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
                # 如果当前显示的不是问卷配置页，也切换过去
                elif self.main_content_stack.currentIndex() != self.panel_idx_questionnaire_setup:
                    self.main_content_stack.setCurrentIndex(self.panel_idx_questionnaire_setup)
        else:  # 其他导航按钮，直接切换
            # print(f"  主窗口调试: 切换到面板索引 {panel_index_to_set} (按钮: {button_attribute_name})")
            self.main_content_stack.setCurrentIndex(panel_index_to_set)

    def _handle_driver_path_update(self, new_path):  # 处理驱动路径更新
        global MSedgedriverPathGlobal
        if MSedgedriverPathGlobal != new_path:
            MSedgedriverPathGlobal = new_path
            self.statusBar().showMessage(f"驱动路径更新: {new_path if new_path else 'PATH查找'}", 3000)
            # print(f"主窗口调试: 驱动路径更新为: {MSedgedriverPathGlobal}")

    def _handle_theme_update(self, theme_name_cn):  # 处理主题更新
        if ui_styles.CURRENT_THEME != theme_name_cn:
            if ui_styles.set_current_theme(theme_name_cn):
                self.apply_styles()  # 应用新主题样式
                self.statusBar().showMessage(f"主题更改为: {theme_name_cn}", 3000)

    def apply_styles(self):  # 应用当前主题的QSS样式
        current_qss = ui_styles.get_app_qss()
        self.setStyleSheet(current_qss)
        # 强制刷新一些可能受样式影响的复杂控件
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

    def _prepare_data_for_filling_panel(self):  # 为“开始运行”面板准备数据
        # print("主窗口调试: _prepare_data_for_filling_panel 调用。")
        parsed_q_data = self.questionnaire_setup_panel.get_parsed_questionnaire_data()
        user_raw_configs_template = self.questionnaire_setup_panel.get_user_raw_configurations_template()

        if not parsed_q_data or (isinstance(parsed_q_data, dict) and "error" in parsed_q_data):
            # print("  主窗口调试: 解析的问卷数据无效或缺失。")
            return False
        if not user_raw_configs_template:
            # print("  主窗口调试: 用户原始配置模板缺失。")
            return False

        current_msedgedriver_path = self.settings.value("msedgedriver_path", "")
        if current_msedgedriver_path == "": current_msedgedriver_path = None  # "" 表示使用PATH

        current_basic_settings = {  # 从QSettings获取基础设置
            "msedgedriver_path": current_msedgedriver_path,
            "proxy": self.settings.value("proxy_address", ""),
            "num_threads": int(self.settings.value("num_threads", 1)),
            "num_fills_total": int(self.settings.value("num_fills", 1)),  # 这是单次运行的总填写数
            "headless": self.settings.value("headless_mode", True, type=bool)
        }
        # print(f"  主窗口调试: “开始运行”面板的基础设置: {current_basic_settings}")

        self.filling_process_panel.prepare_for_filling(
            url=self.questionnaire_setup_panel.url_input.text(),
            parsed_questionnaire_data=parsed_q_data,
            user_raw_configurations_template=user_raw_configs_template,
            basic_settings=current_basic_settings
        )
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("数据准备就绪，可开始运行。", 3000)
        # print("  主窗口调试: 数据成功为“开始运行”面板准备。")
        return True

    def closeEvent(self, event):  # 关闭窗口事件处理
        # print("主窗口调试: closeEvent 调用。")
        if self.filling_process_panel.is_process_running:  # 如果有任务在运行
            reply = QMessageBox.question(self, '任务运行中', "任务正在进行，确定退出吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()  # 忽略关闭事件
                return
            else:
                # print("  主窗口调试: 因关闭事件停止工作线程。")
                self.filling_process_panel.stop_all_workers_forcefully(is_target_reached=False,
                                                                       message_override="程序关闭，任务中止。")
        self.save_settings()  # 保存设置
        event.accept()  # 接受关闭事件


if __name__ == '__main__':
    # 全局异常处理器
    def excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("--------------------- 未处理的全局异常 (main.py) ---------------------")
        print(tb_str)
        print("------------------------------------------------------------")
        error_msg = f"发生未捕获的全局异常:\n{exc_type.__name__}: {exc_value}\n\n详细信息已打印到控制台。\n程序即将退出。"
        try:
            # 尝试用QMessageBox显示错误，如果GUI已不可用，则会失败
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("致命错误")
            msg_box.setText(error_msg)
            msg_box.exec_()
        except Exception:
            pass  # 避免在异常处理中再次抛出异常
        QApplication.quit()  # 退出程序


    sys.excepthook = excepthook  # 设置全局异常钩子

    app = QApplication(sys.argv)
    # 启用高DPI缩放 (如果Qt版本支持)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())