# widgets_basic_settings.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QGroupBox, QFormLayout, QSpinBox,
                             QFileDialog, QDialog, QDialogButtonBox, QComboBox,
                             QColorDialog, QGridLayout, QFrame, QScrollArea,
                             QSizePolicy)  # 新增导入
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor, QPixmap, QIcon  # 新增导入
import ui_styles  # 导入样式模块


# 全局变量的引用方式需要调整，因为 BasicSettingsWidget 现在是对话框，可能无法直接访问 main_window_ref.settings
# 我们可以通过构造函数传递 QSettings 对象，或者让主窗口处理设置的保存和加载。
# 为了简单起见，暂时让它仍然尝试通过 parent 访问，但更好的做法是解耦。

class BasicSettingsDialog(QDialog):  # 修改为继承 QDialog
    # 当任何可能影响全局的设置（如driver路径、主题）发生变化时发射信号
    settings_changed_signal = pyqtSignal()
    msedgedriver_path_changed = pyqtSignal(str)  # 单独为driver路径保留，因为主窗口可能需要立即知道
    theme_changed_signal = pyqtSignal(str)  # 主题改变信号

    def __init__(self, parent=None, settings_qsettings=None):  # parent 是 MainWindow, settings 是 QSettings 对象
        super().__init__(parent)
        self.main_window_ref = parent
        self.settings = settings_qsettings  # 直接使用传入的 QSettings 对象

        self.setWindowTitle("基本设置")
        self.setMinimumWidth(550)  # 给对话框一个合适的最小宽度
        # self.setModal(True) # 设为模态对话框，打开时会阻塞主窗口

        self._init_ui()
        self._load_settings_to_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # 使用 QScrollArea 使内容过多时可以滚动
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")  # 移除滚动区域边框

        content_widget = QWidget()  # 滚动区域的实际内容控件
        form_layout = QVBoxLayout(content_widget)  # 主布局改为垂直，内部使用GroupBox
        form_layout.setSpacing(15)  # 组之间的间距

        # --- 1. 驱动与代理设置 ---
        driver_group = QGroupBox("驱动与代理")
        driver_form = QFormLayout(driver_group)  # GroupBox内部使用QFormLayout
        driver_form.setSpacing(10)

        self.msedgedriver_path_input = QLineEdit()
        self.msedgedriver_path_input.setPlaceholderText("留空则从系统PATH查找")
        self.msedgedriver_path_button = QPushButton("选择路径...")  # 按钮文本稍作修改
        self.msedgedriver_path_button.clicked.connect(self._select_msedgedriver_path)
        path_h_layout = QHBoxLayout()
        path_h_layout.addWidget(self.msedgedriver_path_input, 1)
        path_h_layout.addWidget(self.msedgedriver_path_button)
        driver_form.addRow("MS Edge Driver 路径:", path_h_layout)

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("例如: 127.0.0.1:8080 (留空不使用)")
        driver_form.addRow("HTTP/SOCKS5 代理:", self.proxy_input)
        form_layout.addWidget(driver_group)

        # --- 2. 默认填写参数 ---
        filling_params_group = QGroupBox("默认填写参数")
        params_form = QFormLayout(filling_params_group)
        params_form.setSpacing(10)

        self.num_threads_spinbox = QSpinBox()
        self.num_threads_spinbox.setMinimum(1);
        self.num_threads_spinbox.setMaximum(32);
        self.num_threads_spinbox.setValue(2)
        params_form.addRow("并行线程数:", self.num_threads_spinbox)

        self.num_fills_spinbox = QSpinBox()
        self.num_fills_spinbox.setMinimum(1);
        self.num_fills_spinbox.setMaximum(10000);
        self.num_fills_spinbox.setValue(10)
        params_form.addRow("目标填写总份数:", self.num_fills_spinbox)

        # 可以增加一个 Headless 模式的复选框
        from PyQt5.QtWidgets import QCheckBox
        self.headless_checkbox = QCheckBox("默认以无头模式运行浏览器")
        self.headless_checkbox.setChecked(True)  # 默认勾选
        params_form.addRow(self.headless_checkbox)
        form_layout.addWidget(filling_params_group)

        # --- 3. 界面主题设置 ---
        theme_group = QGroupBox("界面主题")
        theme_v_layout = QVBoxLayout(theme_group)  # GroupBox内部使用QVBoxLayout
        theme_v_layout.setSpacing(10)

        theme_h_layout = QHBoxLayout()  # 用于下拉列表和预览/自定义按钮
        self.theme_combobox = QComboBox()
        for theme_name_cn in ui_styles.MORANDI_COLORS.keys():  # 使用中文主题名
            self.theme_combobox.addItem(theme_name_cn)
        self.theme_combobox.currentTextChanged.connect(self._on_theme_selected_preview)  # 选中时尝试预览
        theme_h_layout.addWidget(QLabel("选择预设主题:"))
        theme_h_layout.addWidget(self.theme_combobox, 1)
        theme_v_layout.addLayout(theme_h_layout)

        # 主题颜色预览区域 (简单实现)
        self.preview_layout = QGridLayout()  # 使用网格布局显示颜色
        theme_v_layout.addWidget(QLabel("当前主题颜色预览:"))
        theme_v_layout.addLayout(self.preview_layout)
        self._update_color_previews(ui_styles.CURRENT_THEME)  # 初始化预览

        # (高级功能 - 自定义颜色，暂时注释，实现会比较复杂)
        # custom_theme_button = QPushButton("自定义当前主题颜色...")
        # custom_theme_button.clicked.connect(self._customize_theme_colors)
        # theme_v_layout.addWidget(custom_theme_button, 0, Qt.AlignCenter)
        form_layout.addWidget(theme_group)

        form_layout.addStretch(1)  # 将内容推到顶部
        content_widget.setLayout(form_layout)
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # --- 对话框按钮 (确定, 取消, 应用) ---
        self.button_box = QDialogButtonBox()
        self.apply_button = self.button_box.addButton("应用", QDialogButtonBox.ApplyRole)
        self.ok_button = self.button_box.addButton("确定", QDialogButtonBox.AcceptRole)
        self.cancel_button = self.button_box.addButton("取消", QDialogButtonBox.RejectRole)

        self.apply_button.clicked.connect(self._apply_settings)
        self.ok_button.clicked.connect(self.accept_settings)  # accept会关闭对话框
        self.cancel_button.clicked.connect(self.reject)  # reject会关闭对话框

        main_layout.addWidget(self.button_box)

    def _on_theme_selected_preview(self, theme_name_cn):
        """当用户在下拉框中选择主题时，更新预览区域"""
        self._update_color_previews(theme_name_cn)
        # 可以在这里临时应用样式到对话框自身以预览，但不保存
        # temp_colors = ui_styles.MORANDI_COLORS.get(theme_name_cn)
        # if temp_colors:
        #     # 构建一个临时的QSS片段来改变对话框背景等，但这比较复杂且可能效果不好
        #     pass

    def _update_color_previews(self, theme_name_cn):
        """根据主题名称更新颜色预览块"""
        # 清除旧的预览
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        colors = ui_styles.MORANDI_COLORS.get(theme_name_cn)
        if not colors:
            return

        # 定义要预览的颜色及其标签
        preview_map = {
            "背景色 (主)": colors.get("background_light"),
            "前景色 (文字)": colors.get("foreground_light"),
            "控件背景": colors.get("widget_bg_light"),
            "边框/辅助色": colors.get("border_light"),
            "按钮背景": colors.get("button_bg_light"),
            "强调色1": colors.get("accent1"),
        }

        row, col = 0, 0
        for label_text, color_hex in preview_map.items():
            if color_hex:
                color_label = QLabel(label_text)
                color_block = QFrame()
                color_block.setFrameShape(QFrame.StyledPanel)
                color_block.setFixedSize(50, 20)
                color_block.setStyleSheet(f"background-color: {color_hex}; border: 1px solid #888;")

                self.preview_layout.addWidget(color_label, row, col * 2)
                self.preview_layout.addWidget(color_block, row, col * 2 + 1)

                col += 1
                if col >= 2:  # 每行显示2对颜色
                    col = 0
                    row += 1
        self.preview_layout.setColumnStretch(1, 1)  # 让颜色块占据一些空间
        self.preview_layout.setColumnStretch(3, 1)

    def _select_msedgedriver_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 msedgedriver.exe", "",
                                                   "可执行文件 (*.exe);;所有文件 (*)")
        if file_path:
            self.msedgedriver_path_input.setText(file_path)

    def _load_settings_to_ui(self):
        if not self.settings: return

        self.msedgedriver_path_input.setText(self.settings.value("msedgedriver_path", ""))
        self.proxy_input.setText(self.settings.value("proxy_address", ""))
        self.num_threads_spinbox.setValue(int(self.settings.value("num_threads", 2)))
        self.num_fills_spinbox.setValue(int(self.settings.value("num_fills", 10)))
        self.headless_checkbox.setChecked(self.settings.value("headless_mode", True, type=bool))

        current_theme_name = self.settings.value("theme", "经典默认")
        self.theme_combobox.setCurrentText(current_theme_name)
        self._update_color_previews(current_theme_name)  # 加载时也更新预览

    def _apply_settings(self):
        """应用当前UI上的设置，但不关闭对话框"""
        if not self.settings: return

        # 保存常规设置
        self.settings.setValue("msedgedriver_path", self.msedgedriver_path_input.text())
        self.settings.setValue("proxy_address", self.proxy_input.text())
        self.settings.setValue("num_threads", self.num_threads_spinbox.value())
        self.settings.setValue("num_fills", self.num_fills_spinbox.value())
        self.settings.setValue("headless_mode", self.headless_checkbox.isChecked())

        # 发射driver路径变化信号（如果路径真的变了）
        # 这里改为在主窗口的 MainWindow.update_global_msedgedriver_path 中保存到settings
        self.msedgedriver_path_changed.emit(self.msedgedriver_path_input.text())

        # 应用并保存主题
        selected_theme_name = self.theme_combobox.currentText()
        if ui_styles.CURRENT_THEME != selected_theme_name:  # 只有主题改变了才发射信号
            self.theme_changed_signal.emit(selected_theme_name)  # 主窗口接收后会set_current_theme和apply_styles

        self.settings_changed_signal.emit()  # 发射一个通用信号表示设置已更改
        if self.main_window_ref:
            self.main_window_ref.statusBar().showMessage("设置已应用。", 3000)

    def accept_settings(self):
        """应用设置并关闭对话框"""
        self._apply_settings()
        self.accept()  # QDialog的标准方法，会关闭对话框并返回 QDialog.Accepted

    # get_settings 方法，如果主窗口在打开对话框前需要获取旧设置，或者其他地方需要
    # 但通常对话框的设置通过信号传递或在关闭时由主窗口读取
    def get_current_dialog_settings(self):
        """返回当前对话框中的设置值（不一定已保存）"""
        return {
            "msedgedriver_path": self.msedgedriver_path_input.text(),
            "proxy_address": self.proxy_input.text(),
            "num_threads": self.num_threads_spinbox.value(),
            "num_fills_total": self.num_fills_spinbox.value(),
            "headless_mode": self.headless_checkbox.isChecked(),
            "theme": self.theme_combobox.currentText()
        }

    # 之前 BasicSettingsWidget 用的 get_settings() 方法，现在这个对话框的设置主要通过信号和QSettings同步
    # 如果其他模块需要直接从这个“面板”（即使它是对话框）获取数据，可以保留类似方法
    # 但对于对话框，通常是“应用”或“确定”时才使设置生效。
    # 为了兼容旧的调用方式，我们可以保留一个 get_settings，它返回已保存（或将要保存）的值
    def get_settings(self):
        """
        返回将会被保存或已经保存的设置。
        注意：这可能不是UI上实时最新的值，除非先调用了 _apply_settings。
        更推荐的方式是通过 QSettings 在各模块间共享设置。
        """
        if self.settings:
            return {
                "msedgedriver_path": self.settings.value("msedgedriver_path", ""),
                "proxy": self.settings.value("proxy_address", ""),  # key名统一
                "num_threads": int(self.settings.value("num_threads", 2)),
                "num_fills_total": int(self.settings.value("num_fills", 10)),
                "headless": self.settings.value("headless_mode", True, type=bool)  # 新增
            }
        return {}  # 如果没有settings对象，返回空

