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
TOTAL_FILLS_LIMIT_UNACTIVATED = 11  # 按您的截图，测试时仍为2
ACTIVATIONS_JSON_FILENAME = "activations.json"


def load_html_from_file(file_name):
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_script_dir, "resources", file_name)
    content = f"<p>错误：无法加载内容文件 '{file_name}'。</p>"
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


class AboutDialog(QDialog):  # 无需修改
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
        version_label = QLabel("版本: 1.1.0 (UI响应与限制优化)")
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
        self.project_root_dir = os.path.dirname(os.path.abspath(__file__))
        self.activations_file_path = os.path.join(self.project_root_dir, ACTIVATIONS_JSON_FILENAME)

        primary_icon_name = "WJX.png"
        secondary_icon_name = "WJX.jpg"
        fallback_icon_path_in_resources = os.path.join(self.project_root_dir, "resources", "icons", "app_icon.png")
        window_icon_to_set = None
        # ... (图标设置代码无变化)
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
        self.settings = QSettings("WJXHelperCo", "WJXNavEdition_v3.5_UI_Response")  # 版本迭代

        # --- 测试重置代码块 ---
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!!!!!!!!!! 测试模式：正在强制重置激活状态和全局填写次数!!!!!!!!!!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        self.settings.setValue("global_total_fills", 0) # 测试用，比如设为 TOTAL_FILLS_LIMIT_UNACTIVATED - 3
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
        self.activation_check_timer.start(5 * 60 * 1000)
        self.recheck_activation_status_from_json()

    def _load_json_activations_data(self):  # 无变化
        if os.path.exists(self.activations_file_path):
            try:
                with open(self.activations_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"MainWindow DEBUG: 读取或解析 {self.activations_file_path} 失败: {e}")
        else:
            print(f"MainWindow DEBUG: 警告 - 激活文件 {self.activations_file_path} 未找到。")
        return {}

    def load_settings_and_activations(self):  # 无变化
        # print("MainWindow DEBUG: load_settings_and_activations called.")
        saved_theme = self.settings.value("theme", "经典默认")
        ui_styles.set_current_theme(saved_theme)
        global MSedgedriverPathGlobal
        MSedgedriverPathGlobal = self.settings.value("msedgedriver_path", None)
        self.global_total_fills_count = self.settings.value("global_total_fills", 0, type=int)
        self.activated_uuid = self.settings.value("activated_uuid", None)
        # print(f"  MainWindow DEBUG: Loaded global_total_fills: {self.global_total_fills_count}, activated_uuid: {self.activated_uuid}")
        self._valid_activations_from_json = self._load_json_activations_data()
        self.recheck_activation_status_from_json()

    def save_settings(self):  # 无变化
        self.settings.setValue("theme", ui_styles.CURRENT_THEME)
        self.settings.setValue("global_total_fills", self.global_total_fills_count)
        self.settings.setValue("activated_uuid", self.activated_uuid)
        self.settings.sync()

    def recheck_activation_status_from_json(self):  # 无变化
        previously_activated_state = self.is_activated
        current_activated_uuid_before_recheck = self.activated_uuid
        self._valid_activations_from_json = self._load_json_activations_data()
        self.is_activated = False
        self.activation_expiry_timestamp = 0.0
        if self.activated_uuid and self.activated_uuid in self._valid_activations_from_json:
            entry = self._valid_activations_from_json[self.activated_uuid]
            validity_code_json = None
            if isinstance(entry, dict):
                validity_code_json = entry.get("validity_code", "").upper()
            elif isinstance(entry, str):
                validity_code_json = entry.upper()
            if validity_code_json:
                now = time.time()
                calculated_expiry_ts = 0.0
                if validity_code_json == "UNL":
                    calculated_expiry_ts = now + (365 * 20 * 24 * 60 * 60)
                else:
                    # ... (有效期计算逻辑无变化)
                    val_str = "".join(filter(str.isdigit, validity_code_json))
                    unit = "".join(filter(str.isalpha, validity_code_json)).upper()
                    if val_str.isdigit() and int(val_str) > 0:
                        val = int(val_str)
                        seconds_multiplier = {'H': 3600, 'D': 86400, 'M': 30 * 86400, 'Y': 365 * 86400}.get(unit, 0)
                        if seconds_multiplier > 0:
                            calculated_expiry_ts = now + val * seconds_multiplier
                if calculated_expiry_ts > now:
                    self.is_activated = True
                    self.activation_expiry_timestamp = calculated_expiry_ts
                else:
                    if previously_activated_state: QMessageBox.warning(self, "激活已过期",
                                                                       f"已激活的码 (UUID: {self.activated_uuid[:8]}...) 根据最新激活文件已过期或有效期配置错误。")
                    self.activated_uuid = None
            else:
                if previously_activated_state: print(
                    f"  MainWindow DEBUG: UUID '{self.activated_uuid}' in JSON but entry format error.")
                self.activated_uuid = None
        if current_activated_uuid_before_recheck and not self.activated_uuid and previously_activated_state:
            QMessageBox.warning(self, "激活已失效",
                                f"之前激活的码 (UUID: {current_activated_uuid_before_recheck[:8]}...) 可能已从有效列表移除或已过期。")
        self.save_settings()
        self._update_window_title_with_activation_status()

    def _update_window_title_with_activation_status(self):  # 无变化
        base_title = "问卷星助手"
        if self.is_activated and self.activation_expiry_timestamp > 0:
            expiry_date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.activation_expiry_timestamp))
            uuid_disp = f" (UUID: {self.activated_uuid[:8]}...)" if self.activated_uuid else ""
            self.setWindowTitle(f"{base_title} (已激活{uuid_disp} - 理论至 {expiry_date_str})")
        else:
            remaining = TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count
            remaining = max(0, remaining)
            self.setWindowTitle(f"{base_title} (未激活 - 剩余免费: {remaining}次)")

    def increment_global_fill_count(self):  # 无变化
        if not self.is_activated:
            self.global_total_fills_count += 1
            # print(f"MainWindow DEBUG: Global fill count incremented to {self.global_total_fills_count} (unactivated).")
        self.save_settings()
        self._update_window_title_with_activation_status()

    def get_remaining_free_fills(self):  # 无变化
        if self.is_activated:
            return float('inf')
        return max(0, TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count)

    def _can_proceed_with_filling(self):  # 无变化，调试日志已加入
        # print("MainWindow DEBUG: _can_proceed_with_filling called.")
        self.recheck_activation_status_from_json()
        if self.is_activated:
            # print("  MainWindow DEBUG: _can_proceed_with_filling: Activated. Returning True.")
            return True
        remaining_fills = self.get_remaining_free_fills()
        # print(f"  MainWindow DEBUG: _can_proceed_with_filling: Unactivated. Remaining free fills: {remaining_fills}")
        if remaining_fills > 0:
            # print("  MainWindow DEBUG: _can_proceed_with_filling: Unactivated, but has free fills. Returning True.")
            return True
        # print("  MainWindow DEBUG: _can_proceed_with_filling: Unactivated and no free fills. Prompting activation dialog.")
        dialog = ActivationDialog(project_root_dir=self.project_root_dir, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            activated_uuid_dlg, expiry_ts_dlg_from_dialog = dialog.get_activation_details()
            if activated_uuid_dlg and expiry_ts_dlg_from_dialog:
                self.activated_uuid = activated_uuid_dlg
                self.save_settings()
                self.recheck_activation_status_from_json()
                if self.is_activated:
                    QMessageBox.information(self, "激活成功", "激活已完成，您可以继续使用了！")
                    return True
                else:
                    QMessageBox.warning(self, "激活失败", "激活未能最终确认或已立即失效，请检查激活码或联系支持。")
                    return False
        else:
            QMessageBox.warning(self, "操作受限",
                                f"免费填写已达 {TOTAL_FILLS_LIMIT_UNACTIVATED} 次上限。请激活软件或检查激活状态。")
        return False

    def _init_ui_with_top_navigation(self):  # 无变化
        central_widget_container = QWidget()
        main_v_layout = QVBoxLayout(central_widget_container)
        # ... (大部分UI初始化代码无变化) ...
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
        self.filling_process_panel = FillingProcessWidget(self)  # 创建实例
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
                button.toggled.connect(lambda checked, idx=target_idx, btn_attr=panel_idx_attr: \
                                           self._nav_button_toggled(checked, idx, btn_attr))

        self.basic_settings_panel.msedgedriver_path_changed.connect(self._handle_driver_path_update)
        self.basic_settings_panel.theme_changed_signal.connect(self._handle_theme_update)
        self.statusBar().showMessage("就绪");
        self.statusBar().setStyleSheet("QStatusBar { padding-left: 5px; }")
        if "panel_idx_questionnaire_setup" in self.nav_buttons:
            self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
        self._update_window_title_with_activation_status()

    def _nav_button_toggled(self, checked, panel_index_to_set, button_attribute_name):  # 无变化，调试日志已加入
        if not checked:
            return
        # print(f"MainWindow DEBUG: Nav button '{button_attribute_name}' toggled, checked: {checked}, target_index: {panel_index_to_set}")
        if button_attribute_name == "panel_idx_filling_process":
            # print("  MainWindow DEBUG: Attempting to navigate to Filling Process panel.")
            can_proceed = self._can_proceed_with_filling()
            # print(f"  MainWindow DEBUG: _can_proceed_with_filling() returned: {can_proceed}")
            if can_proceed:
                data_prepared_ok = self._prepare_data_for_filling_panel()
                # print(f"  MainWindow DEBUG: _prepare_data_for_filling_panel() returned: {data_prepared_ok}")
                if data_prepared_ok:
                    # print("    MainWindow DEBUG: Data prepared, switching to Filling Process panel.")
                    self.main_content_stack.setCurrentIndex(panel_index_to_set)
                else:
                    # print("    MainWindow DEBUG: Data preparation failed. Switching back to setup.")
                    QMessageBox.warning(self, "无法开始", "问卷数据准备失败，请检查“问卷配置”面板。")
                    self.nav_buttons["panel_idx_filling_process"].setChecked(False)
                    if not self.nav_buttons["panel_idx_questionnaire_setup"].isChecked():
                        self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
            else:
                # print("    MainWindow DEBUG: _can_proceed_with_filling returned False. Switching back to setup.")
                self.nav_buttons["panel_idx_filling_process"].setChecked(False)
                if not self.nav_buttons["panel_idx_questionnaire_setup"].isChecked():
                    self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
                elif self.main_content_stack.currentIndex() != self.panel_idx_questionnaire_setup:
                    self.main_content_stack.setCurrentIndex(self.panel_idx_questionnaire_setup)
        else:
            # print(f"  MainWindow DEBUG: Switching to panel index {panel_index_to_set} for button {button_attribute_name}")
            self.main_content_stack.setCurrentIndex(panel_index_to_set)

    def _handle_driver_path_update(self, new_path):  # 无变化
        global MSedgedriverPathGlobal
        if MSedgedriverPathGlobal != new_path:
            MSedgedriverPathGlobal = new_path
            self.statusBar().showMessage(f"驱动路径更新: {new_path if new_path else 'PATH查找'}", 3000)
            # print(f"MainWindow DEBUG: Driver path updated to: {MSedgedriverPathGlobal}")

    def _handle_theme_update(self, theme_name_cn):  # 无变化
        if ui_styles.CURRENT_THEME != theme_name_cn:
            if ui_styles.set_current_theme(theme_name_cn):
                self.apply_styles()
                self.statusBar().showMessage(f"主题更改为: {theme_name_cn}", 3000)

    def apply_styles(self):  # 无变化
        current_qss = ui_styles.get_app_qss()
        self.setStyleSheet(current_qss)
        # ... (控件刷新逻辑无变化)
        if hasattr(self, 'nav_bar_widget'):
            self.nav_bar_widget.style().unpolish(self.nav_bar_widget);
            self.nav_bar_widget.style().polish(self.nav_bar_widget);
            self.nav_bar_widget.update()
        if hasattr(self, 'main_content_stack'):
            for i in range(self.main_content_stack.count()):
                panel = self.main_content_stack.widget(i)
                if panel: panel.style().unpolish(panel); panel.style().polish(panel); panel.update()

    def _prepare_data_for_filling_panel(self):  # 无变化，调试日志已加入
        # print("MainWindow DEBUG: _prepare_data_for_filling_panel called.")
        parsed_q_data = self.questionnaire_setup_panel.get_parsed_questionnaire_data()
        user_raw_configs_template = self.questionnaire_setup_panel.get_user_raw_configurations_template()
        if not parsed_q_data or (isinstance(parsed_q_data, dict) and "error" in parsed_q_data):
            # print("  MainWindow DEBUG: Parsed questionnaire data is invalid or missing.")
            return False
        if not user_raw_configs_template:
            # print("  MainWindow DEBUG: User raw configurations template is missing.")
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
        # print(f"  MainWindow DEBUG: Basic settings for filling panel: {current_basic_settings}")
        self.filling_process_panel.prepare_for_filling(
            url=self.questionnaire_setup_panel.url_input.text(),
            parsed_questionnaire_data=parsed_q_data,
            user_raw_configurations_template=user_raw_configs_template,
            basic_settings=current_basic_settings
        )
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("数据准备就绪，可开始运行。", 3000)
        # print("  MainWindow DEBUG: Data prepared successfully for filling panel.")
        return True

    def closeEvent(self, event):  # 无变化
        # print("MainWindow DEBUG: closeEvent called.")
        if self.filling_process_panel.is_process_running:
            reply = QMessageBox.question(self, '任务运行中', "任务正在进行，确定退出吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore();
                return
            else:
                # print("  MainWindow DEBUG: Stopping workers due to close event.")
                self.filling_process_panel.stop_all_workers_forcefully(is_target_reached=False,
                                                                       message_override="程序关闭，任务中止。")
        self.save_settings()
        event.accept()


if __name__ == '__main__':  # 无变化
    def excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("--------------------- 未处理的全局异常 (main.py) ---------------------")
        print(tb_str)
        print("------------------------------------------------------------")
        error_msg = f"发生未捕获的全局异常:\n{exc_type.__name__}: {exc_value}\n\n详细信息已打印到控制台。\n程序即将退出。"
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("致命错误")
            msg_box.setText(error_msg)
            msg_box.exec_()
        except Exception:
            pass
        QApplication.quit()


    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())

