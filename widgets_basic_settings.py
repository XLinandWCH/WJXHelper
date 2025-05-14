# widgets_basic_settings.py
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QGroupBox, QFormLayout, QSpinBox,
                             QFileDialog, QComboBox, QCheckBox,
                             QFrame, QGridLayout, QScrollArea,
                             QSizePolicy, QSpacerItem)  # 新增 QSpacerItem
from PyQt5.QtCore import pyqtSignal, Qt, QSettings
from PyQt5.QtGui import QColor, QPalette  # QPixmap, QIcon 在此模块不再直接使用

import ui_styles  # 导入样式模块以访问主题颜色定义


class BasicSettingsPanel(QWidget):
    msedgedriver_path_changed = pyqtSignal(str)  # 当驱动路径实际改变时发射
    theme_changed_signal = pyqtSignal(str)  # 当用户选择并希望应用新主题时发射 (中文名)

    def __init__(self, settings_manager: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings_manager  # 主窗口传入的QSettings实例
        self.setObjectName("BasicSettingsPanel")  # 用于QSS

        self._init_ui_layout()  # 初始化整体布局和滚动区域
        self._create_driver_settings_group()  # 创建驱动设置相关的UI
        self._create_filling_params_group()  # 创建填写参数相关的UI
        self._create_theme_settings_group()  # 创建主题设置相关的UI

        self._add_widgets_to_main_layout()  # 将创建的GroupBox添加到主布局

        self._load_settings_to_ui()  # 加载已保存的设置到各个控件
        self._connect_all_signals()  # 连接所有控件的信号到槽函数

    def _init_ui_layout(self):
        """初始化面板的主布局和滚动区域"""
        self.outer_layout = QVBoxLayout(self)  # 面板的主布局
        self.outer_layout.setContentsMargins(0, 0, 0, 0)  # 通常面板本身不设边距

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # 允许内容控件调整大小以填充滚动区
        self.scroll_area.setObjectName("SettingsScrollArea")
        # QSS中可以设置滚动区样式，如 "border: none; background-color: transparent;"

        self.content_widget_for_scroll = QWidget()  # 作为滚动区域的内容承载控件
        self.main_settings_layout = QVBoxLayout(self.content_widget_for_scroll)
        self.main_settings_layout.setSpacing(20)  # 各个GroupBox之间的垂直间距
        self.main_settings_layout.setContentsMargins(15, 15, 15, 15)  # 内容的内边距
        self.main_settings_layout.setAlignment(Qt.AlignTop)  # 组从顶部开始排列

        self.scroll_area.setWidget(self.content_widget_for_scroll)
        self.outer_layout.addWidget(self.scroll_area)

    def _create_driver_settings_group(self):
        """创建驱动与代理设置的GroupBox及其内部控件"""
        self.driver_group = QGroupBox("驱动与代理配置")
        driver_form_layout = QFormLayout(self.driver_group)
        driver_form_layout.setSpacing(12)  # 行间距
        driver_form_layout.setLabelAlignment(Qt.AlignLeft)  # 标签左对齐
        driver_form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # MS Edge Driver 路径
        self.msedgedriver_path_input = QLineEdit()
        self.msedgedriver_path_input.setPlaceholderText("推荐指定路径，或留空从系统PATH查找")
        self.msedgedriver_path_button = QPushButton("浏览...")
        self.msedgedriver_path_button.setObjectName("SelectPathButton")
        self.msedgedriver_path_button.setToolTip("选择 msedgedriver.exe 文件路径")
        path_input_layout = QHBoxLayout()
        path_input_layout.addWidget(self.msedgedriver_path_input, 1)  # 输入框占据更多空间
        path_input_layout.addWidget(self.msedgedriver_path_button)
        driver_form_layout.addRow("Edge Driver 路径:", path_input_layout)

        # HTTP/SOCKS5 代理
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("格式: IP地址:端口 (例如 127.0.0.1:8080)")
        self.proxy_input.setToolTip("填写HTTP或SOCKS5代理服务器地址和端口，留空则不使用代理")
        driver_form_layout.addRow("代理服务器:", self.proxy_input)

    def _create_filling_params_group(self):
        """创建默认填写参数的GroupBox及其内部控件"""
        self.filling_params_group = QGroupBox("自动化填写参数")
        params_form_layout = QFormLayout(self.filling_params_group)
        params_form_layout.setSpacing(12)
        params_form_layout.setLabelAlignment(Qt.AlignLeft)
        params_form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.num_threads_spinbox = QSpinBox()
        self.num_threads_spinbox.setMinimum(1)
        self.num_threads_spinbox.setMaximum(32)  # 合理上限
        self.num_threads_spinbox.setToolTip("同时运行的浏览器窗口数量")
        params_form_layout.addRow("并行线程数:", self.num_threads_spinbox)

        self.num_fills_spinbox = QSpinBox()
        self.num_fills_spinbox.setMinimum(1)
        self.num_fills_spinbox.setMaximum(99999)  # 更大上限
        self.num_fills_spinbox.setToolTip("本次任务计划填写的问卷总份数")
        params_form_layout.addRow("目标填写总份数:", self.num_fills_spinbox)

        self.headless_checkbox = QCheckBox("以无头模式运行浏览器 (不显示浏览器界面)")
        self.headless_checkbox.setToolTip("勾选后，浏览器将在后台运行，速度更快，资源消耗更少")
        params_form_layout.addRow(self.headless_checkbox)  # QFormLayout能处理单个控件的行

    def _create_theme_settings_group(self):
        """创建界面主题设置的GroupBox及其内部控件"""
        self.theme_group = QGroupBox("界面与主题")
        theme_main_v_layout = QVBoxLayout(self.theme_group)  # GroupBox内部使用垂直布局
        theme_main_v_layout.setSpacing(12)

        # 主题选择下拉框
        theme_selection_layout = QHBoxLayout()
        theme_selection_layout.addWidget(QLabel("选择预设主题:"))
        self.theme_combobox = QComboBox()
        self.theme_combobox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # 下拉框宽度扩展
        for theme_name_cn in ui_styles.MORANDI_COLORS.keys():
            self.theme_combobox.addItem(theme_name_cn)
        theme_selection_layout.addWidget(self.theme_combobox, 1)
        theme_main_v_layout.addLayout(theme_selection_layout)

        # 颜色预览区域
        theme_main_v_layout.addWidget(QLabel("当前主题主要颜色预览:"))
        self.color_preview_container = QWidget()  # 容纳颜色块的容器
        self.color_preview_grid_layout = QGridLayout(self.color_preview_container)
        self.color_preview_grid_layout.setSpacing(8)  # 颜色块间距
        self.color_preview_grid_layout.setContentsMargins(5, 5, 5, 5)  # 预览区内边距
        theme_main_v_layout.addWidget(self.color_preview_container)

    def _add_widgets_to_main_layout(self):
        """将所有创建的GroupBox添加到主内容布局中"""
        self.main_settings_layout.addWidget(self.driver_group)
        self.main_settings_layout.addWidget(self.filling_params_group)
        self.main_settings_layout.addWidget(self.theme_group)
        self.main_settings_layout.addStretch(1)  # 确保内容在垂直方向上不会被不必要地拉伸

    def _connect_all_signals(self):
        """集中连接所有控件的信号到对应的处理槽函数"""
        self.msedgedriver_path_button.clicked.connect(self._handle_select_driver_path)
        # editingFinished 在用户完成编辑（例如失去焦点或按回车）时触发
        self.msedgedriver_path_input.editingFinished.connect(self._handle_driver_path_changed_by_input)
        self.proxy_input.editingFinished.connect(self._handle_proxy_changed)

        self.num_threads_spinbox.valueChanged.connect(self._handle_filling_param_changed)
        self.num_fills_spinbox.valueChanged.connect(self._handle_filling_param_changed)
        self.headless_checkbox.stateChanged.connect(self._handle_filling_param_changed)

        self.theme_combobox.currentTextChanged.connect(self._handle_theme_selection_changed)

    def _load_settings_to_ui(self):
        """从QSettings对象加载已保存的设置到UI控件"""
        if not self.settings: return

        self.msedgedriver_path_input.setText(self.settings.value("msedgedriver_path", ""))
        self.proxy_input.setText(self.settings.value("proxy_address", ""))
        self.num_threads_spinbox.setValue(self.settings.value("num_threads", 2, type=int))
        self.num_fills_spinbox.setValue(self.settings.value("num_fills", 10, type=int))
        self.headless_checkbox.setChecked(self.settings.value("headless_mode", True, type=bool))

        # 加载并设置主题，这会触发 _update_color_previews
        current_theme_name = self.settings.value("theme", ui_styles.CURRENT_THEME)  # 使用当前激活的主题
        self.theme_combobox.setCurrentText(current_theme_name)
        # 如果 setCurrentText 的值与当前 ComboBox 的文本相同，可能不会触发 currentTextChanged
        # 所以在这里也手动调用一次更新预览，确保初始预览正确
        self._update_color_previews(current_theme_name)

    # --- 槽函数：处理用户交互和设置更改 ---
    def _handle_select_driver_path(self):
        current_path = self.msedgedriver_path_input.text()
        start_dir = os.path.dirname(current_path) if current_path and os.path.exists(
            os.path.dirname(current_path)) else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 msedgedriver.exe 文件",
                                                   start_dir, "可执行文件 (*.exe);;所有文件 (*)")
        if file_path:
            self.msedgedriver_path_input.setText(file_path)
            self._save_setting_and_emit("msedgedriver_path", file_path, self.msedgedriver_path_changed)

    def _handle_driver_path_changed_by_input(self):
        self._save_setting_and_emit("msedgedriver_path", self.msedgedriver_path_input.text(),
                                    self.msedgedriver_path_changed)

    def _handle_proxy_changed(self):
        self._save_setting_and_emit("proxy_address", self.proxy_input.text())

    def _handle_filling_param_changed(self):  # 一个通用函数处理多个填写参数的保存
        self.settings.setValue("num_threads", self.num_threads_spinbox.value())
        self.settings.setValue("num_fills", self.num_fills_spinbox.value())
        self.settings.setValue("headless_mode", self.headless_checkbox.isChecked())
        # 这些参数的更改通常不需要立即发射信号到主窗口，除非主窗口需要实时知道

    def _handle_theme_selection_changed(self, theme_name_cn):
        self._update_color_previews(theme_name_cn)
        self._save_setting_and_emit("theme", theme_name_cn, self.theme_changed_signal)

    def _save_setting_and_emit(self, key: str, value, signal_to_emit: pyqtSignal = None):
        """通用方法：保存设置到QSettings，如果值改变并且有信号，则发射信号"""
        if self.settings.value(key) != value:
            self.settings.setValue(key, value)
            if signal_to_emit:
                signal_to_emit.emit(value)

    def _update_color_previews(self, theme_name_cn):
        """根据选定的主题名称更新颜色预览块的显示"""
        # 清除旧的预览控件
        while self.color_preview_grid_layout.count():
            item = self.color_preview_grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        theme_colors = ui_styles.MORANDI_COLORS.get(theme_name_cn)
        if not theme_colors:
            # 可以显示一个提示，例如 "无法加载主题颜色"
            no_preview_label = QLabel("无法加载主题颜色预览。")
            self.color_preview_grid_layout.addWidget(no_preview_label, 0, 0, 1, 4)  # 占据几列
            return

        # 定义要预览的关键颜色及其更友好的中文标签
        # (可以从 ui_styles.py 中获取这些键名，避免硬编码)
        preview_config = [
            ("主背景", "background_light"), ("主文字", "foreground_light"),
            ("控件背景", "widget_bg_light"), ("面板背景", "panel_bg_light"),
            ("边框色", "border_light"), ("按钮背景", "button_bg_light"),
            ("强调色1", "accent1"), ("选中背景", "highlight_bg_light")
        ]

        row, col = 0, 0
        max_cols_per_row = 2  # 每行显示两对 标签+颜色块

        for display_name, color_key in preview_config:
            color_hex = theme_colors.get(color_key)
            if color_hex:
                # 创建颜色显示块
                color_swatch = QFrame()
                color_swatch.setFixedSize(20, 20)  # 颜色块大小
                color_swatch.setFrameShape(QFrame.StyledPanel)  # 给个边框感
                color_swatch.setFrameShadow(QFrame.Sunken)
                color_swatch.setStyleSheet(f"background-color: {color_hex}; border: 1px solid #555;")
                color_swatch.setToolTip(f"{display_name}: {color_hex}")

                # 创建颜色名称标签
                name_label = QLabel(display_name)
                name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                # 将颜色块和名称标签添加到网格布局
                self.color_preview_grid_layout.addWidget(color_swatch, row, col * 2)
                self.color_preview_grid_layout.addWidget(name_label, row, col * 2 + 1)

                col += 1
                if col >= max_cols_per_row:
                    col = 0
                    row += 1

        # 确保网格布局中的列有合理的拉伸行为
        for c_idx in range(max_cols_per_row * 2):
            if c_idx % 2 == 1:  # 标签列可以拉伸
                self.color_preview_grid_layout.setColumnStretch(c_idx, 1)
            else:  # 颜色块列不拉伸
                self.color_preview_grid_layout.setColumnStretch(c_idx, 0)

        # 如果最后一行未填满，添加一个垂直伸缩项到底部，避免预览区过大
        # self.color_preview_grid_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), row + 1, 0, 1, max_cols_per_row * 2)

