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
from widgets_filling_process import FillingProcessWidget  # 确保 FillingProcessWidget 已更新以处理停止
from activation_dialog import ActivationDialog  # 确保 ActivationDialog 已更新以处理输入时效性
import time

MSedgedriverPathGlobal = None
TOTAL_FILLS_LIMIT_UNACTIVATED = 2  # 未激活时的填写上限 (用于测试，可改回2000)
ACTIVATIONS_JSON_FILENAME = "activations.json"  # 激活信息JSON文件名


def load_html_from_file(file_name):
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_script_dir, "resources", file_name)
    content = f"<p>错误：无法加载内容文件 '{file_name}'。</p>"  # 默认错误信息
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                stream.setCodec("UTF-8")
                content = stream.readAll()
                file.close()
            else:
                content = f"<p>错误：无法打开文件 '{file_path}'。错误: {file.errorString()}</p>"
        except Exception as e:
            content = f"<p>读取文件 '{file_path}' 时发生错误: {e}</p>"
    return content


class InfoDialog(QDialog):  # 无需修改
    def __init__(self, title, html_content_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 550)
        self.setStyleSheet(ui_styles.get_app_qss())
        layout = QVBoxLayout(self)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        html_content = load_html_from_file(html_content_file)
        self.text_browser.setHtml(html_content)
        layout.addWidget(self.text_browser)
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class AboutDialog(QDialog):  # 无需修改 (除了版本号，如果需要)
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
        version_label = QLabel("版本: 1.0.7 (时效激活)")  # 更新版本号示例
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
        qr_icon_path = os.path.join(project_root, "resources", "icons", "为爱发电.png")  # 或 payment_qr.png
        if os.path.exists(qr_icon_path):
            qr_pixmap = QPixmap(qr_icon_path)
            if not qr_pixmap.isNull():
                qr_label.setPixmap(qr_pixmap.scaledToWidth(200, Qt.SmoothTransformation))  # 调整二维码大小
            else:
                qr_label.setText("二维码加载失败")
        else:
            qr_label.setText("(打赏二维码)")
            qr_label.setFixedSize(200, 200)  # 调整占位符大小
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
        self.project_root_dir = os.path.dirname(os.path.abspath(__file__))
        self.activations_file_path = os.path.join(self.project_root_dir, ACTIVATIONS_JSON_FILENAME)

        # --- 窗口图标设置 (与你提供的一致) ---
        primary_icon_name = "WJX.png"
        secondary_icon_name = "WJX.jpg"
        fallback_icon_path_in_resources = os.path.join(self.project_root_dir, "resources", "icons", "app_icon.png")
        window_icon_to_set = None
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
        self.settings = QSettings("WJXHelperCo", "WJXNavEdition_v3.2_TimedInputActivation")  # 更新配置名

        # --- 测试重置代码块 (保留你原来的，提醒注释) ---
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! 测试模式：正在强制重置激活状态和全局填写次数！！！")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        self.settings.setValue("global_total_fills", 0)
        self.settings.setValue("activated_uuid", None)
        self.settings.sync()
        # --- 测试代码块结束 ---

        self.global_total_fills_count = 0
        self.is_activated = False
        self.activated_uuid = None
        self.activation_expiry_timestamp = 0.0

        self._valid_activations_from_json = {}

        self.load_settings_and_activations()
        self._init_ui_with_top_navigation()
        self.apply_styles()

        self.activation_check_timer = QTimer(self)
        self.activation_check_timer.timeout.connect(self.recheck_activation_status_from_json)
        # 定时器可以稍微频繁一些，比如5分钟，以便更快地反映JSON文件的外部更改（如果作者在运行时更新了它）
        self.activation_check_timer.start(5 * 60 * 1000)
        self.recheck_activation_status_from_json()

    def _load_json_activations_data(self):
        """从JSON文件加载激活数据。"""
        if os.path.exists(self.activations_file_path):
            try:
                with open(self.activations_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    print(f"MainWindow: 从 {self.activations_file_path} 加载 {len(data)} 条激活记录。")
                    return data
            except Exception as e:  # 更通用的异常捕获
                print(f"MainWindow: 读取或解析 {self.activations_file_path} 失败: {e}")
        else:
            print(f"MainWindow: 警告 - 激活文件 {self.activations_file_path} 未找到。")
        return {}

    def load_settings_and_activations(self):
        """加载QSettings和JSON激活数据。"""
        saved_theme = self.settings.value("theme", "经典默认")
        ui_styles.set_current_theme(saved_theme)
        global MSedgedriverPathGlobal
        MSedgedriverPathGlobal = self.settings.value("msedgedriver_path", None)
        self.global_total_fills_count = self.settings.value("global_total_fills", 0, type=int)
        self.activated_uuid = self.settings.value("activated_uuid", None)
        self._valid_activations_from_json = self._load_json_activations_data()
        self.recheck_activation_status_from_json()

    def save_settings(self):
        """保存设置到QSettings。"""
        self.settings.setValue("theme", ui_styles.CURRENT_THEME)
        self.settings.setValue("global_total_fills", self.global_total_fills_count)
        self.settings.setValue("activated_uuid", self.activated_uuid)
        self.settings.sync()
        print(f"MainWindow: 设置已保存 (激活UUID: {self.activated_uuid})。")

    def recheck_activation_status_from_json(self):
        """核心：根据QSettings中的UUID和JSON数据，刷新程序激活状态。"""
        previously_activated_state = self.is_activated
        self.is_activated = False
        self.activation_expiry_timestamp = 0.0

        if self.activated_uuid and self.activated_uuid in self._valid_activations_from_json:
            entry = self._valid_activations_from_json[self.activated_uuid]
            validity_code_json, issue_ts_json, input_win_sec_json = None, None, 0

            if isinstance(entry, dict):  # 新的详细格式
                validity_code_json = entry.get("validity_code", "").upper()
                issue_ts_json = entry.get("issue_timestamp_utc")  # 签发时间戳
                input_win_sec_json = entry.get("input_window_seconds", 0)  # 输入窗口期
            elif isinstance(entry, str):  # 兼容旧的简单格式 "UUID": "7D" (没有输入时效性)
                validity_code_json = entry.upper()

            # 1. 检查输入窗口期 (仅当激活码是通过 ActivationDialog 新输入时，此检查更相关)
            #    对于已激活的UUID，我们主要关心其激活后的有效期。
            #    但如果希望每次recheck都严格按JSON中的输入窗口期（如果存在且未过）来判断，
            #    这里的逻辑会更复杂，因为issue_ts_json是固定的，而当前时间在变。
            #    简单起见，这里我们假设如果一个UUID被激活了，输入窗口期的检查在激活那一刻已经通过。
            #    后续的 recheck 主要关注 validity_code_json。

            if validity_code_json:
                now = time.time()
                calculated_expiry_ts = 0.0
                if validity_code_json == "UNL":
                    calculated_expiry_ts = now + (365 * 20 * 24 * 60 * 60)
                else:
                    val_str = "".join(filter(str.isdigit, validity_code_json))
                    unit = "".join(filter(str.isalpha, validity_code_json)).upper()
                    if val_str.isdigit() and int(val_str) > 0:
                        val = int(val_str)
                        if unit == 'H':
                            calculated_expiry_ts = now + val * 60 * 60
                        elif unit == 'D':
                            calculated_expiry_ts = now + val * 24 * 60 * 60
                        elif unit == 'M':
                            calculated_expiry_ts = now + val * 30 * 24 * 60 * 60
                        elif unit == 'Y':
                            calculated_expiry_ts = now + val * 365 * 24 * 60 * 60

                if calculated_expiry_ts > now:
                    self.is_activated = True
                    self.activation_expiry_timestamp = calculated_expiry_ts
                else:  # 已过期或格式错误
                    if previously_activated_state:
                        QMessageBox.warning(self, "激活已过期",
                                            f"已激活的码 (UUID: {self.activated_uuid[:8]}...) 根据最新激活文件已过期。")
                    self.activated_uuid = None
                    self.save_settings()
            else:  # JSON条目格式错误
                if previously_activated_state: print(f"警告: UUID '{self.activated_uuid}' 在JSON中条目格式不正确。")
                self.activated_uuid = None;
                self.save_settings()
        else:  # QSettings中的UUID为空或不在当前JSON中
            if self.activated_uuid and previously_activated_state:
                QMessageBox.warning(self, "激活已失效",
                                    f"之前激活的码 (UUID: {self.activated_uuid[:8]}...) 已从有效列表中移除。")
            self.activated_uuid = None  # 确保清除
        self._update_window_title_with_activation_status()

    def _update_window_title_with_activation_status(self):
        """更新窗口标题以反映激活状态。"""
        base_title = "问卷星助手"
        if self.is_activated and self.activation_expiry_timestamp > 0:
            expiry_date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.activation_expiry_timestamp))
            uuid_disp = f" (UUID: {self.activated_uuid[:8]}...)" if self.activated_uuid else ""
            self.setWindowTitle(f"{base_title} (已激活{uuid_disp} - 至 {expiry_date_str})")
        else:
            remaining = TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count
            remaining = max(0, remaining)  # 不显示负数
            self.setWindowTitle(f"{base_title} (未激活 - 剩余免费: {remaining}次)")

    def increment_global_fill_count(self):
        """增加全局填写计数。"""
        self.global_total_fills_count += 1
        self.save_settings()
        self._update_window_title_with_activation_status()
        print(f"MainWindow: 全局填写次数更新为: {self.global_total_fills_count}")

    def _can_proceed_with_filling(self):
        """核心检查点：是否可以开始或继续填写。"""
        self._valid_activations_from_json = self._load_json_activations_data()  # 获取最新JSON
        self.recheck_activation_status_from_json()  # 更新激活状态

        if self.is_activated:
            return True
        if self.global_total_fills_count < TOTAL_FILLS_LIMIT_UNACTIVATED:
            return True

        # --- 超限且未激活，弹出对话框 ---
        # ActivationDialog 内部会处理输入时效性
        dialog = ActivationDialog(project_root_dir=self.project_root_dir, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            activated_uuid_dlg, expiry_ts_dlg = dialog.get_activation_details()
            if activated_uuid_dlg and expiry_ts_dlg:
                self.activated_uuid = activated_uuid_dlg
                self.save_settings()
                self.recheck_activation_status_from_json()  # 再次用JSON权威刷新
                if self.is_activated:
                    QMessageBox.information(self, "激活成功", "激活已完成，您可以继续使用了！")
                    return True
                else:
                    QMessageBox.warning(self, "激活失败", "激活未能最终确认，请检查激活码或联系支持。")
                    return False  # 即使对话框接受，如果 recheck 失败，则不允许
            # else: (对话框接受但未返回有效信息，理论上 dialog 内部会处理)
        else:  # 用户关闭对话框
            QMessageBox.warning(self, "操作受限", f"免费填写已达 {TOTAL_FILLS_LIMIT_UNACTIVATED} 次上限。请激活。")
        return False  # 默认不允许

    def _init_ui_with_top_navigation(self):  # UI初始化代码基本不变
        central_widget_container = QWidget()
        main_v_layout = QVBoxLayout(central_widget_container)
        main_v_layout.setContentsMargins(0, 0, 0, 0);
        main_v_layout.setSpacing(0)
        self.nav_bar_widget = QWidget();
        self.nav_bar_widget.setObjectName("TopNavigationBar")
        nav_bar_h_layout = QHBoxLayout(self.nav_bar_widget)
        nav_bar_h_layout.setContentsMargins(10, 2, 10, 0);
        nav_bar_h_layout.setSpacing(2)
        self.top_nav_button_group = QButtonGroup(self);
        self.top_nav_button_group.setExclusive(True)
        nav_config = [
            ("问卷配置", "panel_idx_questionnaire_setup", "edit_form.png"),
            ("开始运行", "panel_idx_filling_process", "play_arrow.png"),
            ("程序设置", "panel_idx_basic_settings", "settings.png"),
            ("使用帮助", "panel_idx_help", "help_outline.png"),
        ]
        self.nav_buttons = {}
        for text, panel_idx_attr, icon_file in nav_config:
            button = QPushButton(text);
            button.setProperty("class", "NavButton");
            button.setCheckable(True)
            button.setMinimumHeight(32);
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            icon_path = os.path.join(self.project_root_dir, "resources", "icons", icon_file)
            if os.path.exists(icon_path): button.setIcon(QIcon(icon_path)); button.setIconSize(QSize(18, 18))
            nav_bar_h_layout.addWidget(button);
            self.top_nav_button_group.addButton(button)
            self.nav_buttons[panel_idx_attr] = button
        nav_bar_h_layout.addStretch(1);
        main_v_layout.addWidget(self.nav_bar_widget)
        self.main_content_stack = QStackedWidget()
        self.questionnaire_setup_panel = QuestionnaireSetupWidget(self)
        self.filling_process_panel = FillingProcessWidget(self)  # 确保FillingProcessWidget已更新
        self.basic_settings_panel = BasicSettingsPanel(self.settings, self)
        self.help_panel = HelpPanel(project_root=self.project_root_dir, parent=self)
        self.panel_idx_questionnaire_setup = self.main_content_stack.addWidget(self.questionnaire_setup_panel)
        self.panel_idx_filling_process = self.main_content_stack.addWidget(self.filling_process_panel)
        self.panel_idx_basic_settings = self.main_content_stack.addWidget(self.basic_settings_panel)
        self.panel_idx_help = self.main_content_stack.addWidget(self.help_panel)
        main_v_layout.addWidget(self.main_content_stack, 1);
        self.setCentralWidget(central_widget_container)
        for panel_idx_attr, button in self.nav_buttons.items():
            target_idx = getattr(self, panel_idx_attr, -1)
            if target_idx != -1:
                if panel_idx_attr == "panel_idx_filling_process":
                    button.clicked.connect(self._handle_filling_navigation_click)
                button.toggled.connect(
                    lambda checked, idx=target_idx, btn_attr=panel_idx_attr: self._nav_button_toggled(checked, idx,
                                                                                                      btn_attr))
        self.basic_settings_panel.msedgedriver_path_changed.connect(self._handle_driver_path_update)
        self.basic_settings_panel.theme_changed_signal.connect(self._handle_theme_update)
        self.statusBar().showMessage("就绪");
        self.statusBar().setStyleSheet("QStatusBar { padding-left: 5px; }")
        if "panel_idx_questionnaire_setup" in self.nav_buttons:
            self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
        self._update_window_title_with_activation_status()

    def _nav_button_toggled(self, checked, panel_index_to_set, button_attribute_name):
        """处理导航按钮的 toggled 信号，确保只在 checked 时切换页面。"""
        # 这个通用处理可以简化之前的 lambda
        if checked:
            # 对于“开始运行”按钮，它的切换由 _handle_filling_navigation_click 决定
            # 所以如果点击的是它，并且can_proceed是false，它可能不会真的切换到目标页面
            # 因此，我们只在非“开始运行”按钮，或者“开始运行”按钮且数据准备成功时切换
            if button_attribute_name != "panel_idx_filling_process" or \
                    (button_attribute_name == "panel_idx_filling_process" and self.main_content_stack.widget(
                        panel_index_to_set) == self.filling_process_panel):
                # 上述条件是为了确保，如果点击的是“开始运行”，那么只有当_prepare_data_for_filling_panel成功（这意味着filling_process_panel已被设置为当前可切换的目标）时，
                # 或者说，是由_handle_filling_navigation_click中setChecked(True)触发的，才实际切换。
                # 简单来说，如果按钮被选中，就切换到对应页面。
                # _handle_filling_navigation_click 会处理是否应该选中“开始运行”按钮。
                self.main_content_stack.setCurrentIndex(panel_index_to_set)

    def _handle_filling_navigation_click(self):
        """当“开始运行”导航按钮被点击时的处理。"""
        print("MainWindow: _handle_filling_navigation_click")

        # 1. 检查激活和次数限制
        if not self._can_proceed_with_filling():
            print("  激活/次数检查未通过。")
            # 如果检查未通过，并且当前有任务在运行，则停止它们
            if self.filling_process_panel.is_process_running:
                print("  由于激活/次数限制，正在停止当前运行的任务...")
                self.filling_process_panel.stop_all_workers_forcefully(is_target_reached=False)
                QMessageBox.warning(self, "任务已中止", "由于激活或使用次数限制，当前运行的填写任务已被中止。")

            # 确保“开始运行”按钮不是选中状态，并将视图切换回“问卷配置”
            fill_button = self.nav_buttons.get("panel_idx_filling_process")
            setup_button = self.nav_buttons.get("panel_idx_questionnaire_setup")
            if fill_button and setup_button:
                if fill_button.isChecked():  # 如果用户刚点了它导致它被选中
                    fill_button.setChecked(False)  # 取消选中，避免触发toggled去切换
                if not setup_button.isChecked():
                    setup_button.setChecked(True)  # 选中配置页，这将通过toggled切换
                elif self.main_content_stack.currentIndex() != self.panel_idx_questionnaire_setup:
                    # 如果配置页按钮已选中但当前不是配置页，则强制切换
                    self.main_content_stack.setCurrentIndex(self.panel_idx_questionnaire_setup)
            return

        # 2. 如果激活检查通过，准备数据
        data_prepared_ok = self._prepare_data_for_filling_panel()

        fill_button = self.nav_buttons.get("panel_idx_filling_process")
        setup_button = self.nav_buttons.get("panel_idx_questionnaire_setup")

        if data_prepared_ok:
            if fill_button and not fill_button.isChecked():
                fill_button.setChecked(True)  # 选中按钮，这将通过 _nav_button_toggled 切换页面
            elif fill_button and self.main_content_stack.currentIndex() != self.panel_idx_filling_process:
                self.main_content_stack.setCurrentIndex(self.panel_idx_filling_process)  # 直接切换
        else:  # 数据准备失败
            if fill_button and fill_button.isChecked():  # 如果"开始运行"被错误地选中了
                fill_button.setChecked(False)
            if setup_button and not setup_button.isChecked():
                setup_button.setChecked(True)
            elif setup_button and self.main_content_stack.currentIndex() != self.panel_idx_questionnaire_setup:
                self.main_content_stack.setCurrentIndex(self.panel_idx_questionnaire_setup)
            QMessageBox.warning(self, "无法开始", "问卷数据准备失败，请检查“问卷配置”面板。")

    def _handle_driver_path_update(self, new_path):  # 无变化
        global MSedgedriverPathGlobal
        if MSedgedriverPathGlobal != new_path:
            MSedgedriverPathGlobal = new_path
            self.statusBar().showMessage(f"驱动路径更新: {new_path if new_path else 'PATH查找'}", 3000)

    def _handle_theme_update(self, theme_name_cn):  # 无变化
        if ui_styles.CURRENT_THEME != theme_name_cn:
            if ui_styles.set_current_theme(theme_name_cn):
                self.apply_styles()
                self.statusBar().showMessage(f"主题更改为: {theme_name_cn}", 3000)

    def apply_styles(self):  # 无变化
        current_qss = ui_styles.get_app_qss()
        self.setStyleSheet(current_qss)
        # ... (控件刷新逻辑) ...
        if hasattr(self, 'nav_bar_widget'):
            self.nav_bar_widget.style().unpolish(self.nav_bar_widget);
            self.nav_bar_widget.style().polish(self.nav_bar_widget);
            self.nav_bar_widget.update()
        if hasattr(self, 'main_content_stack'):
            for i in range(self.main_content_stack.count()):
                panel = self.main_content_stack.widget(i)
                if panel: panel.style().unpolish(panel); panel.style().polish(panel); panel.update()

    def _prepare_data_for_filling_panel(self):  # 无变化
        print("MainWindow: _prepare_data_for_filling_panel")
        parsed_q_data = self.questionnaire_setup_panel.get_parsed_questionnaire_data()
        user_raw_configs_template = self.questionnaire_setup_panel.get_user_raw_configurations_template()
        if not parsed_q_data or (isinstance(parsed_q_data, dict) and "error" in parsed_q_data):
            # QMessageBox.warning(self, "数据错误", "请先加载并解析问卷。") # _handle_filling_navigation_click 中已有提示
            return False
        if not user_raw_configs_template:
            # QMessageBox.warning(self, "配置错误", "未能获取问卷配置模板。")
            return False
        # ... (获取settings并传递给filling_process_panel.prepare_for_filling)
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
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("数据准备就绪，可开始运行。", 3000)
        return True

    def closeEvent(self, event):  # 无变化
        if self.filling_process_panel.is_process_running:
            reply = QMessageBox.question(self, '任务运行中', "任务正在进行，确定退出吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore(); return
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
        # QMessageBox.critical(None, "致命错误", f"发生未捕获的异常:\n{exc_type.__name__}: {exc_value}\n\n详细信息已打印到控制台。\n程序即将退出。")
        QApplication.quit()


    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())

