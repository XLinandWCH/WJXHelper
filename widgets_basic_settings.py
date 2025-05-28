# widgets_basic_settings.py
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QGroupBox, QFormLayout, QSpinBox,
                             QFileDialog, QComboBox, QCheckBox,
                             QSizePolicy, QSpacerItem,QFrame,QScrollArea,
                             QGridLayout)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings
from PyQt5.QtGui import QColor, QPalette

import ui_styles


class BasicSettingsPanel(QWidget):
    # 新信号：当浏览器配置（类型或路径）改变时发射
    # 传递一个字典，例如: {"browser_type": "edge", "driver_path": "/path/to/driver.exe"}
    browser_config_changed = pyqtSignal(dict)
    theme_changed_signal = pyqtSignal(str)

    def __init__(self, settings_manager: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings_manager
        self.main_window_ref = parent  # 获取对 MainWindow 的引用，以便访问 project_root_dir
        self.setObjectName("BasicSettingsPanel")

        self._init_ui_layout()
        self._create_browser_driver_group()  # 替换原来的 _create_driver_settings_group
        self._create_filling_params_group()
        self._create_theme_settings_group()
        self._add_widgets_to_main_layout()
        self._load_settings_to_ui()
        self._connect_all_signals()
        self._update_driver_path_visibility()  # 初始根据浏览器类型显示正确的路径输入

    def _init_ui_layout(self):
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("SettingsScrollArea")
        self.content_widget_for_scroll = QWidget()
        self.main_settings_layout = QVBoxLayout(self.content_widget_for_scroll)
        self.main_settings_layout.setSpacing(20)
        self.main_settings_layout.setContentsMargins(15, 15, 15, 15)
        self.main_settings_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.content_widget_for_scroll)
        self.outer_layout.addWidget(self.scroll_area)

    def _create_browser_driver_group(self):
        self.browser_driver_group = QGroupBox("浏览器与驱动配置")
        layout = QFormLayout(self.browser_driver_group)
        layout.setSpacing(12);
        layout.setLabelAlignment(Qt.AlignLeft)
        layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # 浏览器类型选择
        self.browser_type_combo = QComboBox()
        self.browser_type_combo.addItems(["Microsoft Edge", "Google Chrome", "Mozilla Firefox"])
        layout.addRow("选择浏览器:", self.browser_type_combo)

        # --- Edge Driver 设置 ---
        self.edgedriver_path_widget = QWidget()  # 容器，方便显隐
        edgedriver_layout = QHBoxLayout(self.edgedriver_path_widget)
        edgedriver_layout.setContentsMargins(0, 0, 0, 0)
        self.edgedriver_path_input = QLineEdit()
        self.edgedriver_path_input.setPlaceholderText("留空从系统PATH查找，或使用内置")
        self.edgedriver_path_button = QPushButton("浏览...")
        edgedriver_layout.addWidget(self.edgedriver_path_input, 1)
        edgedriver_layout.addWidget(self.edgedriver_path_button)
        self.edgedriver_path_row_label = QLabel("Edge Driver 路径:")  # 单独的标签，方便显隐控制
        layout.addRow(self.edgedriver_path_row_label, self.edgedriver_path_widget)

        # 使用内置 Edge Driver 的复选框
        self.use_bundled_edgedriver_checkbox = QCheckBox("优先使用程序自带的 Edge Driver")
        self.use_bundled_edgedriver_checkbox.setToolTip(
            "如果勾选，将优先使用程序根目录下的msedgedriver.exe (如果存在)"
        )
        # 检查程序根目录是否有msedgedriver.exe，以决定是否默认勾选或启用此checkbox
        bundled_driver_path = ""
        if self.main_window_ref and hasattr(self.main_window_ref, 'project_root_dir'):
            bundled_driver_path = os.path.join(self.main_window_ref.project_root_dir, "msedgedriver.exe")

        if not os.path.exists(bundled_driver_path):
            self.use_bundled_edgedriver_checkbox.setEnabled(False)
            self.use_bundled_edgedriver_checkbox.setText("优先使用程序自带的 Edge Driver (未找到)")
        layout.addRow(self.use_bundled_edgedriver_checkbox)

        # --- Chrome Driver 设置 ---
        self.chromedriver_path_widget = QWidget()
        chromedriver_layout = QHBoxLayout(self.chromedriver_path_widget)
        chromedriver_layout.setContentsMargins(0, 0, 0, 0)
        self.chromedriver_path_input = QLineEdit()
        self.chromedriver_path_input.setPlaceholderText("指定 chromedriver.exe 路径")
        self.chromedriver_path_button = QPushButton("浏览...")
        chromedriver_layout.addWidget(self.chromedriver_path_input, 1)
        chromedriver_layout.addWidget(self.chromedriver_path_button)
        self.chromedriver_path_row_label = QLabel("Chrome Driver 路径:")
        layout.addRow(self.chromedriver_path_row_label, self.chromedriver_path_widget)

        # --- Firefox Driver 设置 ---
        self.geckodriver_path_widget = QWidget()
        geckodriver_layout = QHBoxLayout(self.geckodriver_path_widget)
        geckodriver_layout.setContentsMargins(0, 0, 0, 0)
        self.geckodriver_path_input = QLineEdit()
        self.geckodriver_path_input.setPlaceholderText("指定 geckodriver.exe 路径")
        self.geckodriver_path_button = QPushButton("浏览...")
        geckodriver_layout.addWidget(self.geckodriver_path_input, 1)
        geckodriver_layout.addWidget(self.geckodriver_path_button)
        self.geckodriver_path_row_label = QLabel("Firefox Driver 路径:")
        layout.addRow(self.geckodriver_path_row_label, self.geckodriver_path_widget)

        # 代理设置 (保持不变，但放在这个GroupBox里)
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("格式: IP地址:端口 (留空则不使用)")
        layout.addRow("代理服务器:", self.proxy_input)

    def _create_filling_params_group(self):  # (保持不变)
        self.filling_params_group = QGroupBox("自动化填写参数")
        params_form_layout = QFormLayout(self.filling_params_group)
        params_form_layout.setSpacing(12);
        params_form_layout.setLabelAlignment(Qt.AlignLeft)
        params_form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.num_threads_spinbox = QSpinBox();
        self.num_threads_spinbox.setMinimum(1);
        self.num_threads_spinbox.setMaximum(32)
        params_form_layout.addRow("并行线程数:", self.num_threads_spinbox)
        self.num_fills_spinbox = QSpinBox();
        self.num_fills_spinbox.setMinimum(1);
        self.num_fills_spinbox.setMaximum(99999)
        params_form_layout.addRow("目标填写总份数:", self.num_fills_spinbox)
        self.headless_checkbox = QCheckBox("以无头模式运行浏览器 (不显示浏览器界面)")
        params_form_layout.addRow(self.headless_checkbox)

    def _create_theme_settings_group(self):  # (保持不变)
        self.theme_group = QGroupBox("界面与主题");
        theme_main_v_layout = QVBoxLayout(self.theme_group);
        theme_main_v_layout.setSpacing(12)
        theme_selection_layout = QHBoxLayout();
        theme_selection_layout.addWidget(QLabel("选择预设主题:"))
        self.theme_combobox = QComboBox();
        self.theme_combobox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for theme_name_cn in ui_styles.MORANDI_COLORS.keys(): self.theme_combobox.addItem(theme_name_cn)
        theme_selection_layout.addWidget(self.theme_combobox, 1);
        theme_main_v_layout.addLayout(theme_selection_layout)
        theme_main_v_layout.addWidget(QLabel("当前主题主要颜色预览:"))
        self.color_preview_container = QWidget();
        self.color_preview_grid_layout = QGridLayout(self.color_preview_container)
        self.color_preview_grid_layout.setSpacing(8);
        self.color_preview_grid_layout.setContentsMargins(5, 5, 5, 5)
        theme_main_v_layout.addWidget(self.color_preview_container)

    def _add_widgets_to_main_layout(self):
        self.main_settings_layout.addWidget(self.browser_driver_group)  # 使用新的GroupBox
        self.main_settings_layout.addWidget(self.filling_params_group)
        self.main_settings_layout.addWidget(self.theme_group)
        self.main_settings_layout.addStretch(1)

    def _connect_all_signals(self):
        self.browser_type_combo.currentTextChanged.connect(self._handle_browser_type_changed)

        self.edgedriver_path_button.clicked.connect(lambda: self._select_driver_path_for_browser("edge"))
        self.chromedriver_path_button.clicked.connect(lambda: self._select_driver_path_for_browser("chrome"))
        self.geckodriver_path_button.clicked.connect(lambda: self._select_driver_path_for_browser("firefox"))

        self.edgedriver_path_input.editingFinished.connect(self._handle_driver_path_input_changed)
        self.chromedriver_path_input.editingFinished.connect(self._handle_driver_path_input_changed)
        self.geckodriver_path_input.editingFinished.connect(self._handle_driver_path_input_changed)

        self.use_bundled_edgedriver_checkbox.stateChanged.connect(self._handle_use_bundled_driver_changed)
        self.proxy_input.editingFinished.connect(self._handle_proxy_changed)

        self.num_threads_spinbox.valueChanged.connect(self._handle_filling_param_changed)
        self.num_fills_spinbox.valueChanged.connect(self._handle_filling_param_changed)
        self.headless_checkbox.stateChanged.connect(self._handle_filling_param_changed)
        self.theme_combobox.currentTextChanged.connect(self._handle_theme_selection_changed)

    def _load_settings_to_ui(self):
        if not self.settings: return

        # 加载浏览器类型和驱动路径
        saved_browser_type_str = self.settings.value("browser_type", "edge")  # 默认为edge
        if saved_browser_type_str == "edge":
            self.browser_type_combo.setCurrentText("Microsoft Edge")
        elif saved_browser_type_str == "chrome":
            self.browser_type_combo.setCurrentText("Google Chrome")
        elif saved_browser_type_str == "firefox":
            self.browser_type_combo.setCurrentText("Mozilla Firefox")

        self.edgedriver_path_input.setText(self.settings.value("edgedriver_path", ""))
        self.chromedriver_path_input.setText(self.settings.value("chromedriver_path", ""))
        self.geckodriver_path_input.setText(self.settings.value("geckodriver_path", ""))

        use_bundled = self.settings.value("use_bundled_edgedriver", True, type=bool)  # 默认尝试使用内置
        if self.use_bundled_edgedriver_checkbox.isEnabled():  # 仅当checkbox可用时才设置其状态
            self.use_bundled_edgedriver_checkbox.setChecked(use_bundled)
        else:  # 如果checkbox不可用（例如，没找到内置驱动），则强制不勾选
            self.use_bundled_edgedriver_checkbox.setChecked(False)

        self.proxy_input.setText(self.settings.value("proxy_address", ""))
        self.num_threads_spinbox.setValue(self.settings.value("num_threads", 2, type=int))
        self.num_fills_spinbox.setValue(self.settings.value("num_fills", 10, type=int))
        self.headless_checkbox.setChecked(self.settings.value("headless_mode", True, type=bool))

        current_theme_name = self.settings.value("theme", ui_styles.CURRENT_THEME)
        self.theme_combobox.setCurrentText(current_theme_name)
        self._update_color_previews(current_theme_name)
        self._update_driver_path_visibility()  # 确保基于加载的设置正确显示UI

    def _update_driver_path_visibility(self):
        """根据选择的浏览器类型，显示/隐藏对应的驱动路径输入行"""
        selected_browser_text = self.browser_type_combo.currentText()
        is_edge = (selected_browser_text == "Microsoft Edge")
        is_chrome = (selected_browser_text == "Google Chrome")
        is_firefox = (selected_browser_text == "Mozilla Firefox")

        self.edgedriver_path_row_label.setVisible(is_edge)
        self.edgedriver_path_widget.setVisible(is_edge)
        self.use_bundled_edgedriver_checkbox.setVisible(is_edge)

        self.chromedriver_path_row_label.setVisible(is_chrome)
        self.chromedriver_path_widget.setVisible(is_chrome)

        self.geckodriver_path_row_label.setVisible(is_firefox)
        self.geckodriver_path_widget.setVisible(is_firefox)

        # 如果选择Edge且勾选了“使用内置”，则禁用Edge路径输入
        if is_edge:
            self.edgedriver_path_input.setEnabled(not self.use_bundled_edgedriver_checkbox.isChecked())
            self.edgedriver_path_button.setEnabled(not self.use_bundled_edgedriver_checkbox.isChecked())

    def _handle_browser_type_changed(self, browser_text):
        self._update_driver_path_visibility()
        self._emit_current_browser_config()  # 浏览器类型改变，发射配置

    def _handle_use_bundled_driver_changed(self, state):
        self._update_driver_path_visibility()  # 更新输入框的启用状态
        self.settings.setValue("use_bundled_edgedriver", bool(state))
        self._emit_current_browser_config()  # 发射配置

    def _select_driver_path_for_browser(self, browser_key):
        input_field = None
        if browser_key == "edge":
            input_field = self.edgedriver_path_input
        elif browser_key == "chrome":
            input_field = self.chromedriver_path_input
        elif browser_key == "firefox":
            input_field = self.geckodriver_path_input
        else:
            return

        current_path = input_field.text()
        start_dir = os.path.dirname(current_path) if current_path and os.path.exists(
            os.path.dirname(current_path)) else os.path.expanduser("~")

        dialog_title = f"选择 {browser_key.capitalize()} Driver (e.g., {browser_key}driver.exe)"
        file_path, _ = QFileDialog.getOpenFileName(self, dialog_title, start_dir, "可执行文件 (*.exe);;所有文件 (*)")

        if file_path:
            input_field.setText(file_path)
            self.settings.setValue(f"{browser_key}driver_path", file_path)  # 保存对应的路径
            self._emit_current_browser_config()  # 发射配置

    def _handle_driver_path_input_changed(self):
        # 当任何一个驱动路径输入框完成编辑时触发
        # 需要确定是哪个输入框改变了，并保存对应设置
        sender_input = self.sender()
        if sender_input == self.edgedriver_path_input:
            self.settings.setValue("edgedriver_path", sender_input.text())
        elif sender_input == self.chromedriver_path_input:
            self.settings.setValue("chromedriver_path", sender_input.text())
        elif sender_input == self.geckodriver_path_input:
            self.settings.setValue("geckodriver_path", sender_input.text())
        self._emit_current_browser_config()  # 发射配置

    def _emit_current_browser_config(self):
        """收集当前浏览器配置并发出信号"""
        browser_text = self.browser_type_combo.currentText()
        browser_type_key = "edge"  # 默认
        driver_path = ""

        if browser_text == "Microsoft Edge":
            browser_type_key = "edge"
            if self.use_bundled_edgedriver_checkbox.isChecked():
                # 获取内置驱动路径
                bundled_driver_path = ""
                if self.main_window_ref and hasattr(self.main_window_ref, 'project_root_dir'):
                    bundled_driver_path = os.path.join(self.main_window_ref.project_root_dir, "msedgedriver.exe")
                if os.path.exists(bundled_driver_path):
                    driver_path = bundled_driver_path
                else:  # 如果内置驱动未找到，即使勾选了也尝试用户路径或PATH
                    driver_path = self.edgedriver_path_input.text()
            else:
                driver_path = self.edgedriver_path_input.text()
        elif browser_text == "Google Chrome":
            browser_type_key = "chrome"
            driver_path = self.chromedriver_path_input.text()
        elif browser_text == "Mozilla Firefox":
            browser_type_key = "firefox"
            driver_path = self.geckodriver_path_input.text()

        # 如果用户指定的路径为空，Selenium 会尝试从PATH查找，所以空字符串是有效的
        config = {"browser_type": browser_type_key, "driver_path": driver_path if driver_path else None}
        self.settings.setValue("browser_type", browser_type_key)  # 保存选择的浏览器类型
        # 各自的driver_path已在_select_driver_path_for_browser或_handle_driver_path_input_changed中保存

        self.browser_config_changed.emit(config)

    def _handle_proxy_changed(self):
        self.settings.setValue("proxy_address", self.proxy_input.text())
        # 代理更改通常不需要立即通知主窗口，worker启动时会读取

    def _handle_filling_param_changed(self):
        self.settings.setValue("num_threads", self.num_threads_spinbox.value())
        self.settings.setValue("num_fills", self.num_fills_spinbox.value())
        self.settings.setValue("headless_mode", self.headless_checkbox.isChecked())

    def _handle_theme_selection_changed(self, theme_name_cn):
        self._update_color_previews(theme_name_cn)
        if self.settings.value("theme") != theme_name_cn:
            self.settings.setValue("theme", theme_name_cn)
            self.theme_changed_signal.emit(theme_name_cn)

    def _update_color_previews(self, theme_name_cn):  # (保持不变)
        while self.color_preview_grid_layout.count():
            item = self.color_preview_grid_layout.takeAt(0)
            if item and item.widget(): item.widget().deleteLater()
        theme_colors = ui_styles.MORANDI_COLORS.get(theme_name_cn)
        if not theme_colors:
            self.color_preview_grid_layout.addWidget(QLabel("无法加载主题颜色预览。"), 0, 0, 1, 4);
            return
        preview_config = [("主背景", "background_light"), ("主文字", "foreground_light"),
                          ("控件背景", "widget_bg_light"),
                          ("面板背景", "panel_bg_light"), ("边框色", "border_light"), ("按钮背景", "button_bg_light"),
                          ("强调色1", "accent1"), ("选中背景", "highlight_bg_light")]
        row, col = 0, 0;
        max_cols_per_row = 2
        for display_name, color_key in preview_config:
            color_hex = theme_colors.get(color_key)
            if color_hex:
                color_swatch = QFrame();
                color_swatch.setFixedSize(20, 20);
                color_swatch.setFrameShape(QFrame.StyledPanel)
                color_swatch.setFrameShadow(QFrame.Sunken);
                color_swatch.setStyleSheet(f"background-color:{color_hex};border:1px solid #555;")
                color_swatch.setToolTip(f"{display_name}: {color_hex}");
                name_label = QLabel(display_name);
                name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.color_preview_grid_layout.addWidget(color_swatch, row, col * 2);
                self.color_preview_grid_layout.addWidget(name_label, row, col * 2 + 1)
                col += 1
                if col >= max_cols_per_row: col = 0; row += 1
        for c_idx in range(max_cols_per_row * 2):
            if c_idx % 2 == 1:
                self.color_preview_grid_layout.setColumnStretch(c_idx, 1)
            else:
                self.color_preview_grid_layout.setColumnStretch(c_idx, 0)

