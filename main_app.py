# main_app.py
import sys
import os
import traceback
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QStackedWidget, QMessageBox, QDialog, QTextBrowser,
                             QPushButton, QDialogButtonBox, QLabel, QFrame, QGroupBox,
                             QButtonGroup, QSizePolicy, QSpacerItem, QMenu)
from PyQt5.QtCore import Qt, QSettings, QUrl, QFile, QTextStream, QIODevice, QSize, QTimer, QDateTime
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

import ui_styles
from widgets_basic_settings import BasicSettingsPanel
from widgets_help_panel import HelpPanel
from widgets_questionnaire_setup import QuestionnaireSetupWidget
from widgets_filling_process import FillingProcessWidget
from activation_dialog import ActivationDialog
import time
import tempfile  # 新增：用于可能的临时用户数据目录基础路径

CURRENT_APP_VERSION = "1.4.5"
VERSION_INFO_URL = "YOUR_VERSION_JSON_FILE_URL_HERE"  # 请替换为您的真实URL
IS_TEST_MODE = True  # <--- 设置为 True 启用测试模式，False 禁用

MSedgedriverPathGlobal = None  # 这个全局变量似乎未使用，可以考虑移除
TOTAL_FILLS_LIMIT_UNACTIVATED = 500
ACTIVATIONS_JSON_FILENAME = "activations.json"


def resource_path(relative_path):
    """获取资源的绝对路径，无论是在开发环境还是在PyInstaller打包后。"""
    try:
        # PyInstaller 创建的临时文件夹，打包后运行时资源在这里
        base_path = sys._MEIPASS
    except Exception:
        # 不在打包环境中（例如，直接从Python解释器运行）
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):  # 更可靠的打包后检测
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def load_html_from_file(file_name):
    """从指定的HTML文件加载内容，使用resource_path确保路径正确。"""
    file_path = resource_path(os.path.join("resources", file_name))  # 假设HTML文件在resources子目录
    content = f"<p>错误：无法加载内容文件 '{file_name}'。路径: {file_path}</p>"  # 包含路径以便调试
    if os.path.exists(file_path):
        try:
            file = QFile(file_path)
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                stream.setCodec("UTF-8")  # 确保使用UTF-8编码
                content = stream.readAll()
                file.close()
            else:
                content = f"<p>错误：无法打开文件 '{file_path}'。错误: {file.errorString()}</p>"
        except Exception as e:
            content = f"<p>读取文件 '{file_path}' 时发生错误: {e}</p>"
    return content


class InfoDialog(QDialog):
    """通用的信息展示对话框，加载HTML内容。"""

    def __init__(self, title, html_content_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 550)
        self.setStyleSheet(ui_styles.get_app_qss())  # 应用统一样式
        layout = QVBoxLayout(self)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)  # 允许打开HTML中的外部链接
        html_content = load_html_from_file(html_content_file)
        self.text_browser.setHtml(html_content)
        layout.addWidget(self.text_browser)
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)  # 关闭对话框
        layout.addWidget(button_box)


class AboutDialog(QDialog):
    """“关于”对话框，展示版本、开发者、项目链接和鼓励信息。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于与鼓励")
        self.setMinimumWidth(450)
        self.setStyleSheet(ui_styles.get_app_qss())
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 顶部图标和标题
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        # app_icon_path_about = resource_path(os.path.join("resources", "icons", "app_icon.png")) # 旧的
        app_icon_path_about = resource_path("WJX.ico")  # 优先使用项目根目录的WJX.ico作为"关于"对话框的图标
        if not os.path.exists(app_icon_path_about):  # 如果WJX.ico找不到，再尝试旧路径
            app_icon_path_about = resource_path(os.path.join("resources", "icons", "app_icon.png"))

        if os.path.exists(app_icon_path_about):
            pixmap = QPixmap(app_icon_path_about)
            icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header_layout.addWidget(icon_label)

        title_version_layout = QVBoxLayout()
        title_label = QLabel("问卷星助手 ")
        title_label.setStyleSheet("font-size:18pt;font-weight:bold;")
        self.version_label_in_about = QLabel(f"版本: {CURRENT_APP_VERSION}")
        title_version_layout.addWidget(title_label)
        title_version_layout.addWidget(self.version_label_in_about)
        header_layout.addLayout(title_version_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line1)

        # 作者和项目信息
        author_label = QLabel("<b>开发者:</b> XLin & WCH")  # 请替换为真实的开发者信息
        author_label.setTextFormat(Qt.RichText)
        main_layout.addWidget(author_label)
        github_label = QLabel(
            '<b>项目地址:</b> <a href="https://github.com/XLinandWCH/WJXHelper">GitHub源码</a>')  # 请替换为真实的项目链接
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
        qr_icon_path = resource_path(os.path.join("resources", "icons", "为爱发电.png"))  # 确保此图片存在
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
        # buttons_for_encourage_layout = QVBoxLayout() # 这部分似乎不需要额外按钮，可以简化
        # buttons_for_encourage_layout.addStretch()
        # qr_and_buttons_layout.addLayout(buttons_for_encourage_layout, 1)
        encourage_layout.addLayout(qr_and_buttons_layout)
        main_layout.addWidget(encourage_group)

        main_layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        main_layout.addWidget(button_box)


class MainWindow(QMainWindow):
    """主应用程序窗口。"""

    def __init__(self):
        super().__init__()
        self.force_update_mode = False
        self.latest_server_version_info = {}
        self.setWindowTitle(f"问卷星助手 v{CURRENT_APP_VERSION}")
        self.setMinimumSize(960, 720)
        # self.project_root_dir = os.path.dirname(os.path.abspath(__file__)) # 在resource_path已处理
        self.activations_file_path = resource_path(ACTIVATIONS_JSON_FILENAME)  # 使用resource_path确保打包后也能找到

        # --- 必须先初始化 QSettings ---
        self.settings = QSettings("WJXHelperCo", f"WJXNavEdition_v{CURRENT_APP_VERSION}")  # 公司和应用名
        # --- QSettings 初始化完成 ---

        self.current_browser_type = "edge"  # 默认值，会被 load_settings_and_activations覆盖
        self.current_driver_path = None  # 默认值
        self.base_user_data_dir_for_workers = None  # 新增：用于worker的临时用户数据目录的基础路径

        # --- 窗口图标设置 ---
        window_icon_path = resource_path("WJX.ico")
        if os.path.exists(window_icon_path):
            self.setWindowIcon(QIcon(window_icon_path))
        else:
            print(f"警告: 未找到主图标 WJX.ico at {window_icon_path}。尝试后备图标...")
            fallback_icon_path_png = resource_path("WJX.png")
            if os.path.exists(fallback_icon_path_png):
                self.setWindowIcon(QIcon(fallback_icon_path_png))
            else:
                fallback_icon_resources = resource_path(os.path.join("resources", "icons", "app_icon.png"))
                if os.path.exists(fallback_icon_resources):
                    self.setWindowIcon(QIcon(fallback_icon_resources))
                else:
                    print("警告: 所有指定的窗口图标均未找到。")
        # --- 窗口图标设置结束 ---

        # --- 现在可以安全调用 _check_bundled_edgedriver ---
        self._check_bundled_edgedriver()  # 检查捆绑驱动
        # --- _check_bundled_edgedriver 调用完成 ---

        self.setGeometry(100, 100, 1100, 800)
        # self.settings 已在前面初始化
        self.global_total_fills_count = 0
        self.is_activated = False
        self.activated_uuid = None
        self.activation_expiry_timestamp = 0.0
        self._valid_activations_from_json = {}

        if IS_TEST_MODE:
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print("!!!!!!!!!!! 测试模式：正在强制重置激活状态和全局填写次数!!!!!!!!!!!")
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            self.settings.setValue("global_total_fills", 0)
            self.settings.setValue("activated_uuid", None)
            self.settings.sync()
            print("  主窗口调试: 测试模式：已重置激活状态和全局填写次数。")

        self.load_settings_and_activations()  # 这个方法会读取settings，所以settings必须已存在
        self._init_ui_with_top_navigation()
        self.apply_styles()

        self.activation_check_timer = QTimer(self)
        self.activation_check_timer.timeout.connect(self.recheck_activation_status_from_json)
        self.activation_check_timer.start(5 * 60 * 1000)

        self.network_manager = QNetworkAccessManager(self)
        self.update_grace_period_days = 7
        self.last_update_check_key = "last_update_prompt_timestamp"
        self.first_install_key = "first_install_timestamp_for_update_grace"
        QTimer.singleShot(1500, self.check_for_updates_on_startup)
    def _check_bundled_edgedriver(self):
        """检查捆绑的EdgeDriver是否存在，并相应设置current_driver_path的默认值。"""
        # bundled_driver_path = os.path.join(self.project_root_dir, "msedgedriver.exe") # 旧
        bundled_driver_path = resource_path("msedgedriver.exe")  # 使用resource_path
        if os.path.exists(bundled_driver_path):
            # 如果捆绑驱动存在，并且用户设置是使用捆绑驱动，则将其设为默认
            if self.settings.value("use_bundled_edgedriver", True, type=bool):  # 默认为True
                self.current_driver_path = bundled_driver_path
                print(f"MainWindow: 检测到捆绑的 msedgedriver.exe: {bundled_driver_path}")
        else:
            print("MainWindow: 未在预期路径找到捆绑的 msedgedriver.exe。")
            # 如果捆绑驱动不存在，确保 use_bundled_edgedriver 设置为 False，除非用户明确选择
            # 这一步可以在 load_settings_and_activations 中进一步处理

    def _load_json_activations_data(self):
        """从JSON文件加载激活数据。"""
        # self.activations_file_path 已经在 __init__ 中使用 resource_path 初始化
        if os.path.exists(self.activations_file_path):
            try:
                with open(self.activations_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict): return data
            except Exception as e:
                print(f"主窗口调试: 读取或解析 {self.activations_file_path} 失败: {e}")
        else:
            print(f"主窗口调试: 警告 - 激活文件 {self.activations_file_path} 未找到。")
        return {}

    def load_settings_and_activations(self):
        """加载程序设置和激活状态。"""
        saved_theme = self.settings.value("theme", "经典默认")
        ui_styles.set_current_theme(saved_theme)

        self.current_browser_type = self.settings.value("browser_type", "edge").lower()
        use_bundled = self.settings.value("use_bundled_edgedriver", True, type=bool)

        # 临时用户数据目录的基础路径设置
        self.base_user_data_dir_for_workers = self.settings.value("base_user_data_dir", None)
        if self.base_user_data_dir_for_workers == "":
            self.base_user_data_dir_for_workers = None
        if self.base_user_data_dir_for_workers is None:  # 如果用户未设置，默认使用系统临时目录
            self.base_user_data_dir_for_workers = os.path.join(tempfile.gettempdir(), "WJXHelper_Profiles")
            os.makedirs(self.base_user_data_dir_for_workers, exist_ok=True)  # 确保基础目录存在
            print(f"MainWindow: 未指定基础用户数据目录，将使用: {self.base_user_data_dir_for_workers}")

        # 驱动路径设置
        bundled_driver_phys_path = resource_path("msedgedriver.exe")  # 捆绑驱动的物理(或打包后临时)路径

        if self.current_browser_type == "edge":
            if use_bundled and os.path.exists(bundled_driver_phys_path):
                self.current_driver_path = bundled_driver_phys_path
            else:  # 不使用捆绑的，或者捆绑的不存在
                self.current_driver_path = self.settings.value("edgedriver_path", None)
        elif self.current_browser_type == "chrome":
            # 假设Chrome驱动也可能捆绑，名为 chromedriver.exe
            bundled_chromedriver_path = resource_path("chromedriver.exe")
            if use_bundled and os.path.exists(bundled_chromedriver_path):  # 假设chrome也支持捆绑
                self.current_driver_path = bundled_chromedriver_path
            else:
                self.current_driver_path = self.settings.value("chromedriver_path", None)
        elif self.current_browser_type == "firefox":
            # 假设Firefox驱动也可能捆绑，名为 geckodriver.exe
            bundled_geckodriver_path = resource_path("geckodriver.exe")
            if use_bundled and os.path.exists(bundled_geckodriver_path):  # 假设firefox也支持捆绑
                self.current_driver_path = bundled_geckodriver_path
            else:
                self.current_driver_path = self.settings.value("geckodriver_path", None)
        else:  # 未知浏览器类型，重置为edge默认
            self.current_browser_type = "edge"
            if use_bundled and os.path.exists(bundled_driver_phys_path):
                self.current_driver_path = bundled_driver_phys_path
            else:
                self.current_driver_path = self.settings.value("edgedriver_path", None)  # 再次尝试edge的设置

        if self.current_driver_path == "":  # 用户清空了路径输入框
            self.current_driver_path = None

        print(f"MainWindow: 初始化浏览器配置为 Type='{self.current_browser_type}', "
              f"Path='{self.current_driver_path if self.current_driver_path else '从PATH查找或无'}'")

        # 激活状态
        self.global_total_fills_count = self.settings.value("global_total_fills", 0, type=int)
        self.activated_uuid = self.settings.value("activated_uuid", None)
        self._valid_activations_from_json = self._load_json_activations_data()
        self.recheck_activation_status_from_json()

    def save_settings(self):
        """保存程序设置。"""
        self.settings.setValue("theme", ui_styles.CURRENT_THEME)
        self.settings.setValue("global_total_fills", self.global_total_fills_count)
        self.settings.setValue("activated_uuid", self.activated_uuid)
        self.settings.setValue("browser_type", self.current_browser_type)

        # 保存驱动路径时，如果当前使用的是捆绑驱动，则不应覆盖用户的自定义路径设置
        # 只有当 use_bundled_edgedriver 为 False 时，才保存用户指定的路径
        use_bundled_setting = self.settings.value("use_bundled_edgedriver", True, type=bool)

        if self.current_browser_type == "edge":
            if not use_bundled_setting:  # 仅当不使用捆绑驱动时，保存edgedriver_path
                self.settings.setValue("edgedriver_path", self.current_driver_path if self.current_driver_path else "")
        elif self.current_browser_type == "chrome":
            # 假设对chrome也有类似的 use_bundled 设置，或总是保存自定义路径
            self.settings.setValue("chromedriver_path", self.current_driver_path if self.current_driver_path else "")
        elif self.current_browser_type == "firefox":
            self.settings.setValue("geckodriver_path", self.current_driver_path if self.current_driver_path else "")

        # 保存基础用户数据目录设置
        self.settings.setValue("base_user_data_dir",
                               self.base_user_data_dir_for_workers if self.base_user_data_dir_for_workers else "")

        self.settings.sync()  # 确保写入磁盘

    def recheck_activation_status_from_json(self):
        """重新检查激活状态，基于加载的JSON数据和当前存储的UUID。"""
        # (此方法逻辑保持不变)
        previously_activated_state = self.is_activated;
        current_activated_uuid_before_recheck = self.activated_uuid;
        self._valid_activations_from_json = self._load_json_activations_data();
        self.is_activated = False;
        self.activation_expiry_timestamp = 0.0
        if self.activated_uuid and self.activated_uuid in self._valid_activations_from_json:
            entry = self._valid_activations_from_json[self.activated_uuid];
            validity_code_json = None
            if isinstance(entry, dict):
                validity_code_json = entry.get("validity_code", "").upper()
            elif isinstance(entry, str):
                validity_code_json = entry.upper()
            if validity_code_json:
                now = time.time();
                calculated_expiry_ts = 0.0
                if validity_code_json == "UNL":  # 无限期
                    calculated_expiry_ts = now + (365 * 20 * 24 * 60 * 60)  # 假设20年为无限
                else:  # 有限期，例如 30D, 1M, 1Y
                    val_str = "".join(filter(str.isdigit, validity_code_json));
                    unit = "".join(filter(str.isalpha, validity_code_json)).upper()
                    if val_str.isdigit() and int(val_str) > 0:
                        val = int(val_str);
                        seconds_multiplier = {'H': 3600, 'D': 86400, 'M': 30 * 86400, 'Y': 365 * 86400}.get(unit, 0)
                        if seconds_multiplier > 0:
                            issue_ts = 0.0  # 激活码签发时间戳 (UTC)
                            if isinstance(entry, dict) and "issue_timestamp_utc" in entry:
                                issue_ts = float(entry["issue_timestamp_utc"])

                            if issue_ts > 0:  # 如果有签发时间，则从签发时间开始计算有效期
                                calculated_expiry_ts = issue_ts + (val * seconds_multiplier)
                            else:  # 否则从当前时间开始计算 (兼容旧格式或简单激活)
                                calculated_expiry_ts = now + (val * seconds_multiplier)

                if calculated_expiry_ts > now:  # 如果计算出的过期时间晚于当前时间
                    self.is_activated = True
                    self.activation_expiry_timestamp = calculated_expiry_ts
                else:  # 已过期
                    if previously_activated_state:  # 如果之前是激活状态，现在过期了，给个提示
                        QMessageBox.warning(self, "激活已过期",
                                            f"已激活的码 (UUID: {self.activated_uuid[:8]}...) 根据最新激活文件已过期或有效期配置错误。")
                    self.activated_uuid = None  # 清除过期的UUID
            else:  # JSON中条目格式错误
                if previously_activated_state:
                    print(f"  主窗口调试: UUID '{self.activated_uuid}' 在JSON中，但条目格式错误或有效期代码缺失。")
                self.activated_uuid = None

        # 如果之前记录的UUID不在新的JSON文件中了 (可能被吊销或文件更新)
        if current_activated_uuid_before_recheck and not self.activated_uuid and previously_activated_state:
            QMessageBox.warning(self, "激活已失效",
                                f"之前激活的码 (UUID: {current_activated_uuid_before_recheck[:8]}...) 可能已从有效列表移除或已过期。")

        self._update_window_title_with_activation_status()

    def _update_window_title_with_activation_status(self):
        """根据激活状态更新窗口标题。"""
        # (此方法逻辑保持不变)
        base_title = f"问卷星助手 v{CURRENT_APP_VERSION}";
        if self.is_activated and self.activation_expiry_timestamp > 0:
            expiry_date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(
                self.activation_expiry_timestamp));
            uuid_disp = f" (UUID: {self.activated_uuid[:8]}...)" if self.activated_uuid else "";
            self.setWindowTitle(
                f"{base_title} (已激活{uuid_disp} - 至 {expiry_date_str})")
        else:
            remaining = TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count;
            remaining = max(0,
                            remaining);
            self.setWindowTitle(
                f"{base_title} (未激活 - 剩余免费: {remaining}次)")
        if self.force_update_mode: self.setWindowTitle(f"{self.windowTitle()} [需更新!]")

    def increment_global_fill_count(self):
        """增加全局填写次数（如果未激活）。"""
        if not self.is_activated:
            self.global_total_fills_count += 1
        self.save_settings()  # 保存更改
        self._update_window_title_with_activation_status()

    def get_remaining_free_fills(self):
        """获取剩余的免费填写次数。"""
        if self.is_activated:
            return float('inf')  # 已激活则无限
        return max(0, TOTAL_FILLS_LIMIT_UNACTIVATED - self.global_total_fills_count)

    def _is_update_grace_period_expired(self, force_update_version_str):
        """检查更新宽限期是否已过。"""
        # (此方法逻辑保持不变)
        if not self.settings.contains(self.first_install_key): self.settings.setValue(self.first_install_key,
                                                                                      QDateTime.currentSecsSinceEpoch());return False
        first_install_ts = self.settings.value(self.first_install_key, 0, type=int);
        current_ts = QDateTime.currentSecsSinceEpoch();
        days_since_install = (current_ts - first_install_ts) / (24 * 60 * 60)
        if self._version_tuple(CURRENT_APP_VERSION) < self._version_tuple(force_update_version_str):
            if days_since_install > self.update_grace_period_days: return True
        return False

    def _can_proceed_with_filling(self):
        """检查是否可以继续填写（激活状态、免费额度、强制更新）。"""
        # (此方法逻辑保持不变)
        force_ver = self.latest_server_version_info.get("force_update_before", "0.0.0")
        if self.force_update_mode and self._is_update_grace_period_expired(force_ver): QMessageBox.critical(self,
                                                                                                            "强制更新",
                                                                                                            "检测到重要版本更新，请先更新软件后再使用。\n部分功能已受限。")  # 这里可以考虑返回False阻止进行
        self.recheck_activation_status_from_json()  # 确保状态最新
        if self.is_activated:
            return True
        remaining_fills = self.get_remaining_free_fills()
        if remaining_fills > 0:
            return True

        # 免费额度用尽，尝试激活
        dialog = ActivationDialog(project_root_dir=os.path.dirname(os.path.abspath(__file__)),
                                  parent=self)  # project_root_dir 参数可能需要调整或移除
        if dialog.exec_() == QDialog.Accepted:
            activated_uuid_dlg, expiry_ts_dlg_from_dialog = dialog.get_activation_details()
            if activated_uuid_dlg and expiry_ts_dlg_from_dialog:  # 激活对话框返回了有效信息
                self.activated_uuid = activated_uuid_dlg
                # self.activation_expiry_timestamp = expiry_ts_dlg_from_dialog # 应该由recheck确认
                self.save_settings()  # 保存新UUID
                self.recheck_activation_status_from_json()  # 根据新UUID和JSON文件重新确认激活状态
                if self.is_activated:
                    QMessageBox.information(self, "激活成功", "激活已完成，您可以继续使用了！")
                    return True
                else:
                    QMessageBox.warning(self, "激活失败", "激活未能最终确认或已立即失效。请检查激活码和网络。")
                    return False
        else:  # 用户关闭了激活对话框
            QMessageBox.warning(self, "操作受限",
                                f"免费填写已达上限 ({TOTAL_FILLS_LIMIT_UNACTIVATED}次)。请激活软件或检查激活状态。")
        return False

    def _init_ui_with_top_navigation(self):
        """初始化带顶部导航栏的UI。"""
        # (此方法逻辑基本不变, 但确保nav按钮图标路径使用resource_path)
        central_widget_container = QWidget();
        main_v_layout = QVBoxLayout(central_widget_container);
        main_v_layout.setContentsMargins(0, 0, 0, 0);
        main_v_layout.setSpacing(0)
        self.nav_bar_widget = QWidget();
        self.nav_bar_widget.setObjectName("TopNavigationBar");
        nav_bar_h_layout = QHBoxLayout(self.nav_bar_widget);
        nav_bar_h_layout.setContentsMargins(10, 2, 10, 0);
        nav_bar_h_layout.setSpacing(2)
        self.top_nav_button_group = QButtonGroup(self);
        self.top_nav_button_group.setExclusive(True)
        nav_config = [("问卷配置", "panel_idx_questionnaire_setup", "edit_form.png"),
                      ("开始运行", "panel_idx_filling_process", "play_arrow.png"),
                      ("程序设置", "panel_idx_basic_settings", "settings.png"),
                      ("使用帮助", "panel_idx_help", "help_outline.png"), ]
        self.nav_buttons = {};
        for text, panel_idx_attr, icon_file_name in nav_config:
            button = QPushButton(text);
            button.setProperty("class", "NavButton");
            button.setMinimumHeight(32);
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            icon_path = resource_path(os.path.join("resources", "icons", icon_file_name))  # 使用resource_path
            if os.path.exists(icon_path): button.setIcon(QIcon(icon_path));button.setIconSize(QSize(18, 18))
            button.setCheckable(True);
            self.top_nav_button_group.addButton(button);
            self.nav_buttons[panel_idx_attr] = button;
            nav_bar_h_layout.addWidget(button)
        nav_bar_h_layout.addStretch(1);
        main_v_layout.addWidget(self.nav_bar_widget)
        self.main_content_stack = QStackedWidget()
        self.questionnaire_setup_panel = QuestionnaireSetupWidget(self)
        self.filling_process_panel = FillingProcessWidget(self)
        self.basic_settings_panel = BasicSettingsPanel(self.settings, self);  # settings 和 parent
        self.help_panel = HelpPanel(project_root=os.path.dirname(os.path.abspath(__file__)),
                                    parent=self)  # project_root 可能需要调整
        self.panel_idx_questionnaire_setup = self.main_content_stack.addWidget(self.questionnaire_setup_panel)
        self.panel_idx_filling_process = self.main_content_stack.addWidget(self.filling_process_panel)
        self.panel_idx_basic_settings = self.main_content_stack.addWidget(self.basic_settings_panel)
        self.panel_idx_help = self.main_content_stack.addWidget(self.help_panel)
        main_v_layout.addWidget(self.main_content_stack, 1);
        self.setCentralWidget(central_widget_container)
        for panel_idx_attr, button in self.nav_buttons.items():
            target_idx = getattr(self, panel_idx_attr, -1)
            if target_idx != -1: button.toggled.connect(
                lambda checked, idx=target_idx, btn_attr=panel_idx_attr: self._nav_button_toggled(checked, idx,
                                                                                                  btn_attr))
        self.basic_settings_panel.browser_config_changed.connect(self._handle_browser_config_update)
        self.basic_settings_panel.theme_changed_signal.connect(self._handle_theme_update)
        self.statusBar().showMessage("就绪");
        self.statusBar().setStyleSheet("QStatusBar { padding-left: 5px; }")
        if "panel_idx_questionnaire_setup" in self.nav_buttons: self.nav_buttons[
            "panel_idx_questionnaire_setup"].setChecked(True)

    def _nav_button_toggled(self, checked, panel_index_to_set, button_attribute_name):
        """处理顶部导航按钮的切换。"""
        # (此方法逻辑保持不变)
        if not checked: return  # 只处理选中的情况
        if button_attribute_name == "panel_idx_help":  # 帮助面板直接切换
            self.main_content_stack.setCurrentIndex(panel_index_to_set)
            return

        if button_attribute_name == "panel_idx_filling_process":
            # 切换到“开始运行”前，检查是否可以进行
            force_ver = self.latest_server_version_info.get("force_update_before", "0.0.0")
            # if self.force_update_mode and self._is_update_grace_period_expired(force_ver): # 这个检查在_can_proceed_with_filling里
            #     pass # 提示已在 _can_proceed_with_filling 中处理

            can_proceed = self._can_proceed_with_filling()
            if can_proceed:
                data_prepared_ok = self._prepare_data_for_filling_panel()
                if data_prepared_ok:
                    self.main_content_stack.setCurrentIndex(panel_index_to_set)
                    # 自动开始逻辑（如果需要）
                    if hasattr(self.filling_process_panel, '_start_filling_process'):
                        print("MainWindow: 自动调用 _start_filling_process on FillingProcessPanel.")
                        QTimer.singleShot(100, self.filling_process_panel._start_filling_process)
                    else:
                        print("MainWindow: FillingProcessPanel 没有 _start_filling_process 方法。")
                else:  # 数据准备失败
                    QMessageBox.warning(self, "无法开始", "问卷数据准备失败或因版本过旧受限。请返回问卷配置。")
                    self.nav_buttons["panel_idx_filling_process"].setChecked(False)  # 取消选中“开始运行”
                    # 自动切回问卷配置页
                    if not self.nav_buttons["panel_idx_questionnaire_setup"].isChecked():
                        self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
                    elif self.main_content_stack.currentIndex() != self.panel_idx_questionnaire_setup:
                        self.main_content_stack.setCurrentIndex(self.panel_idx_questionnaire_setup)

            else:  # 不能进行 (例如免费额度用完且未激活)
                self.nav_buttons["panel_idx_filling_process"].setChecked(False)  # 取消选中“开始运行”
                # 确保焦点在问卷配置或设置页
                if not self.nav_buttons["panel_idx_questionnaire_setup"].isChecked():
                    self.nav_buttons["panel_idx_questionnaire_setup"].setChecked(True)
                elif self.main_content_stack.currentIndex() != self.panel_idx_questionnaire_setup:
                    self.main_content_stack.setCurrentIndex(self.panel_idx_questionnaire_setup)
        else:  # 其他面板直接切换
            self.main_content_stack.setCurrentIndex(panel_index_to_set)

    def _handle_browser_config_update(self, config: dict):
        """处理来自BasicSettingsPanel的浏览器配置更新。"""
        new_browser_type = config.get("browser_type", "edge").lower()
        new_driver_path = config.get("driver_path")  # 可能为None或空字符串
        new_base_user_data_dir = config.get("base_user_data_dir", None)

        config_changed = False
        if self.current_browser_type != new_browser_type:
            self.current_browser_type = new_browser_type
            config_changed = True

        if self.current_driver_path != new_driver_path:
            self.current_driver_path = new_driver_path if new_driver_path else None  # 确保空字符串转为None
            config_changed = True

        if self.base_user_data_dir_for_workers != new_base_user_data_dir:
            self.base_user_data_dir_for_workers = new_base_user_data_dir if new_base_user_data_dir else None
            if self.base_user_data_dir_for_workers is None:  # 如果用户清空，则重置为默认临时目录
                self.base_user_data_dir_for_workers = os.path.join(tempfile.gettempdir(), "WJXHelper_Profiles")
                os.makedirs(self.base_user_data_dir_for_workers, exist_ok=True)
            config_changed = True

        if config_changed:
            self.statusBar().showMessage(
                f"浏览器配置更新: {self.current_browser_type.capitalize()}, "
                f"驱动: {'PATH查找或捆绑' if not self.current_driver_path else os.path.basename(self.current_driver_path) if self.current_driver_path else '无'}",
                3000)
            print(f"MainWindow: 浏览器配置更新 -> 类型='{self.current_browser_type}', "
                  f"驱动路径='{self.current_driver_path}', "
                  f"基础用户数据目录='{self.base_user_data_dir_for_workers}'")
            self.save_settings()  # 保存新的配置

    def _handle_driver_path_update(self, new_path):
        """旧方法，似乎未使用，保留或移除。"""
        pass

    def _handle_theme_update(self, theme_name_cn):
        """处理主题更改。"""
        if ui_styles.CURRENT_THEME != theme_name_cn:
            if ui_styles.set_current_theme(theme_name_cn):
                self.apply_styles()
                self.statusBar().showMessage(f"主题更改为: {theme_name_cn}", 3000)

    def apply_styles(self):
        """应用当前选定的QSS样式。"""
        current_qss = ui_styles.get_app_qss()
        self.setStyleSheet(current_qss)
        # 强制刷新导航栏和堆叠窗口中的面板样式
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
        """为FillingProcessPanel准备运行所需的数据。"""
        force_update_version_str = self.latest_server_version_info.get("force_update_before", "0.0.0")
        is_restricted_by_update = False

        if self.force_update_mode and self._is_update_grace_period_expired(force_update_version_str):
            is_restricted_by_update = True
            # 此处可以添加更严格的限制，如完全禁止运行，或在FillingProcessPanel中实现
            # if hasattr(self.filling_process_panel, 'apply_restricted_mode'):
            #     self.filling_process_panel.apply_restricted_mode(max_threads=1) # 例如限制线程
            # else:
            QMessageBox.warning(self, "功能受限", "软件版本过旧，建议尽快更新以获取完整功能。部分操作可能受限。")

        parsed_q_data = self.questionnaire_setup_panel.get_parsed_questionnaire_data()
        user_raw_configs_template = self.questionnaire_setup_panel.get_user_raw_configurations_template()

        if not parsed_q_data or (isinstance(parsed_q_data, dict) and "error" in parsed_q_data):
            QMessageBox.warning(self, "数据错误", "未能获取有效的问卷解析数据。请先加载并解析问卷。")
            return False
        if not user_raw_configs_template:  # and isinstance(parsed_q_data, list) and len(parsed_q_data) > 0: # 后半条件之前是get_user_raw_configurations_template里的警告
            QMessageBox.warning(self, "配置错误", "未能获取有效的问卷配置模板。请确保问卷已加载且题目已显示。")
            return False

        # 从self.settings或self成员变量获取最新的浏览器相关设置
        current_basic_settings = {
            "browser_type": self.current_browser_type,  # 已是最新
            "driver_executable_path": self.current_driver_path,  # 已是最新
            "base_user_data_dir": self.base_user_data_dir_for_workers,  # 新增，传递给worker
            "proxy": self.settings.value("proxy_address", ""),
            "num_threads": int(self.settings.value("num_threads", 1)),
            "num_fills_total": int(self.settings.value("num_fills", 1)),
            "headless": self.settings.value("headless_mode", True, type=bool)
        }

        if is_restricted_by_update:  # 如果因版本旧而受限
            current_basic_settings["num_threads"] = min(current_basic_settings["num_threads"], 1)  # 例如限制为1线程
            print(f"MainWindow: 由于版本限制，线程数被调整为: {current_basic_settings['num_threads']}")

        print(f"MainWindow: 准备运行 FillingProcessPanel，配置: {current_basic_settings}")

        self.filling_process_panel.prepare_for_filling(
            url=self.questionnaire_setup_panel.url_input.text(),  # 获取当前URL
            parsed_questionnaire_data=parsed_q_data,
            user_raw_configurations_template=user_raw_configs_template,
            basic_settings=current_basic_settings  # 传递包含所有所需设置的字典
        )
        if hasattr(self, 'statusBar'):
            self.statusBar().showMessage("数据准备就绪，可开始运行。", 3000)
        return True

    def _version_tuple(self, v_str):
        """将版本字符串（如 "1.2.0"）转换为元组（如 (1, 2, 0)）以方便比较。"""
        try:
            return tuple(map(int, (v_str.split("."))))
        except:  # 处理无效版本字符串
            return (0, 0, 0)

    def check_for_updates_on_startup(self):
        """应用启动时检查更新。"""
        self.manual_check_for_updates(silent_if_no_update=True, update_help_panel_directly=True)

    def manual_check_for_updates(self, silent_if_no_update=False, update_help_panel_directly=False):
        """手动触发检查更新。"""
        # (此方法逻辑保持不变)
        if VERSION_INFO_URL == "YOUR_VERSION_JSON_FILE_URL_HERE":
            if update_help_panel_directly and hasattr(self, 'help_panel') and hasattr(self.help_panel,
                                                                                      'display_update_info'):
                self.help_panel.display_update_info(True, {"error": "尚未配置更新服务器URL。"}, CURRENT_APP_VERSION)
            elif not silent_if_no_update:
                QMessageBox.information(self, "检查更新", "尚未配置更新服务器URL。")
            return
        if update_help_panel_directly and hasattr(self, 'help_panel') and hasattr(self.help_panel,
                                                                                  'display_update_info'): self.help_panel.display_update_info(
            False, {"status": "checking"}, CURRENT_APP_VERSION)
        self.statusBar().showMessage("正在检查更新...", 2000)
        request = QNetworkRequest(QUrl(VERSION_INFO_URL));
        request.setRawHeader(b"Cache-Control", b"no-cache");  # 强制不使用缓存
        request.setRawHeader(b"Pragma", b"no-cache");
        request.setRawHeader(b"Expires", b"0")
        reply = self.network_manager.get(request)
        # 使用 lambda 传递额外参数给槽函数
        reply.finished.connect(
            lambda: self._handle_update_check_response(reply, silent_if_no_update, update_help_panel_directly))

    def _handle_update_check_response(self, reply, silent_if_no_update, update_help_panel_directly):
        """处理更新检查的网络响应。"""
        # (此方法逻辑保持不变)
        is_update_available = False;
        server_info_for_panel = None;
        popup_message_title = "";
        popup_message_text = "";
        popup_icon = QMessageBox.Information
        show_download_button_in_popup = False;
        download_url_for_popup = None
        if reply.error() == QNetworkReply.NoError:
            try:
                data = bytes(reply.readAll()).decode('utf-8');  # 确保正确解码
                server_version_info = json.loads(data)
                self.latest_server_version_info = server_version_info;  # 存储最新信息
                server_info_for_panel = server_version_info  # 用于传递给帮助面板
                latest_version_str = server_version_info.get("latest_version", "0.0.0");
                force_update_version_str = server_version_info.get("force_update_before", "0.0.0")  # 低于此版本则强制
                download_url_for_popup = server_version_info.get("download_url");
                release_notes = server_version_info.get("release_notes", "暂无详细信息。")
                current_v_tuple = self._version_tuple(CURRENT_APP_VERSION);
                latest_v_tuple = self._version_tuple(latest_version_str)
                is_update_available = latest_v_tuple > current_v_tuple;
                is_force_required_by_server = current_v_tuple < self._version_tuple(force_update_version_str)
                if is_force_required_by_server:
                    self.force_update_mode = True
                else:
                    self.force_update_mode = False  # 确保每次检查后重置
                if is_update_available:
                    self.settings.setValue(self.last_update_check_key, QDateTime.currentSecsSinceEpoch());  # 记录提示时间
                    grace_period_expired = self._is_update_grace_period_expired(force_update_version_str)
                    popup_message_title = "发现新版本！";
                    popup_message_text = f"检测到新版本: <b>{latest_version_str}</b> (您当前为: {CURRENT_APP_VERSION})。\n\n<b>更新内容:</b>\n{release_notes.replace('<br>', '\\n').replaceNewLine('<br>')}\n\n";  # 处理换行
                    show_download_button_in_popup = True
                    if self.force_update_mode:
                        if grace_period_expired:
                            popup_message_text += "<font color='red'><b>此为重要更新，为确保正常使用，请立即更新！部分功能可能已受限。</b></font>\n";
                            popup_icon = QMessageBox.Critical
                        else:
                            days_left = self.update_grace_period_days - ((
                                                                                 QDateTime.currentSecsSinceEpoch() - self.settings.value(
                                                                             self.first_install_key, 0,
                                                                             type=int)) / (
                                                                                 24 * 60 * 60));
                            popup_message_text += f"<font color='orange'><b>此为重要更新，建议您尽快更新。剩余宽限期约 {max(0, int(days_left))} 天。</b></font>\n";
                            popup_icon = QMessageBox.Warning
                else:  # 没有新版本
                    self.force_update_mode = False  # 确保重置
                    if not silent_if_no_update and not update_help_panel_directly:  # 如果不是静默检查或直接更新帮助面板
                        popup_message_title = "检查更新";
                        popup_message_text = f"您当前已是最新版本 ({CURRENT_APP_VERSION})。";
                        popup_icon = QMessageBox.Information;
                        show_download_button_in_popup = False
            except Exception as e:
                print(f"处理版本信息错误: {e}\n{traceback.format_exc()}")
                server_info_for_panel = {"error": f"解析版本信息错误: {e}"};
                if not silent_if_no_update and not update_help_panel_directly:
                    popup_message_title = "更新检查失败";
                    popup_message_text = f"处理版本信息时出错: {e}";
                    popup_icon = QMessageBox.Warning
                self.statusBar().showMessage(f"更新检查失败: {e}", 3000)
        else:  # 网络错误
            error_string = reply.errorString();
            server_info_for_panel = {"error": f"网络错误: {error_string}"};
            if not silent_if_no_update and not update_help_panel_directly:
                popup_message_title = "更新检查失败";
                popup_message_text = f"无法连接到更新服务器: {error_string}";
                popup_icon = QMessageBox.Warning
            self.statusBar().showMessage(f"更新检查失败: {error_string}", 3000)

        if update_help_panel_directly and hasattr(self, 'help_panel') and hasattr(self.help_panel,
                                                                                  'display_update_info'):
            is_latest_for_panel = not is_update_available or (reply.error() != QNetworkReply.NoError)
            self.help_panel.display_update_info(is_latest_for_panel, server_info_for_panel, CURRENT_APP_VERSION)

        # 显示弹窗逻辑
        if popup_message_text and \
                (not silent_if_no_update or  # 如果不是静默模式，则总显示弹窗
                 (self.force_update_mode and self._is_update_grace_period_expired(
                     self.latest_server_version_info.get("force_update_before", "0.0.0")))  # 或者如果是强制更新且宽限期已过
                ):
            msg_box = QMessageBox(self);
            msg_box.setWindowTitle(popup_message_title);
            msg_box.setIcon(popup_icon);
            msg_box.setTextFormat(Qt.RichText);  # 允许富文本
            msg_box.setText(popup_message_text)
            dl_button = None
            if show_download_button_in_popup and download_url_for_popup:
                dl_button = msg_box.addButton("立即更新", QMessageBox.AcceptRole)

            is_critical_force_update = self.force_update_mode and self._is_update_grace_period_expired(
                self.latest_server_version_info.get("force_update_before", "0.0.0"))

            if not (is_critical_force_update and show_download_button_in_popup):  # 如果不是紧急强制更新 或者 没有下载按钮
                if not show_download_button_in_popup:  # 如果根本没有下载按钮（例如已是最新版或检查失败）
                    msg_box.addButton("确定", QMessageBox.OkRole)
                else:  # 有下载按钮，但不是紧急强制更新
                    msg_box.addButton("稍后提醒", QMessageBox.RejectRole)  # 或者 "忽略"

            msg_box.exec_()
            if dl_button and msg_box.clickedButton() == dl_button:
                QDesktopServices.openUrl(QUrl(download_url_for_popup))

        self._update_window_title_with_activation_status();  # 更新标题以反映可能的 force_update_mode
        reply.deleteLater()  # 清理网络请求对象

    def closeEvent(self, event):
        """处理窗口关闭事件。"""
        if self.filling_process_panel.is_process_running:
            reply = QMessageBox.question(self, '任务运行中', "任务正在进行，确定退出吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            else:
                self.filling_process_panel.stop_all_workers_forcefully(is_target_reached=False,
                                                                       message_override="程序关闭，任务中止。")
        self.save_settings()  # 确保关闭前保存设置
        event.accept()


if __name__ == '__main__':
    def excepthook(exc_type, exc_value, exc_tb):
        """全局异常处理器，用于捕获未处理的异常并显示错误信息。"""
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb));
        print("--------------------- 未处理的全局异常 (main.py) ---------------------");
        print(tb_str);
        print("------------------------------------------------------------")
        error_msg = f"发生未捕获的全局异常:\n{exc_type.__name__}: {exc_value}\n\n详细信息已打印到控制台。\n程序即将退出。"
        try:
            # 尝试用QMessageBox显示错误，如果GUI部分也出错了，这个可能不会显示
            msg_box = QMessageBox();
            msg_box.setIcon(QMessageBox.Critical);
            msg_box.setWindowTitle("致命错误");
            msg_box.setText(error_msg);
            msg_box.exec_()
        except Exception:
            pass  # 如果显示消息框也失败了，至少控制台有输出
        QApplication.quit()  # 尝试优雅退出


    sys.excepthook = excepthook  # 设置全局异常钩子

    app = QApplication(sys.argv)

    # 启用高DPI缩放支持 (如果Qt版本支持)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())