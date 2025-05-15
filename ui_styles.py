# ui_styles.py

MORANDI_COLORS = {
    "灰粉玫瑰": {
        "background_light": "#E0C0C0", "foreground_light": "#5C4033",
        "widget_bg_light": "#F0E0E0", "panel_bg_light": "#E8D0D0",
        "border_light": "#C0A0A0", "button_bg_light": "#D8B0B0",
        "button_hover_light": "#C8A0A0", "highlight_bg_light": "#B08080",
        "text_highlight_light": "#FFFFFF", "accent1": "#A07070",
        "accent2": "#F8D0D0", "nav_button_text_light": "#5C4033",
        "nav_button_hover_bg_light": "#D8B0B0", "nav_button_checked_bg_light": "#A07070",  # 选中用主强调色
        "nav_button_checked_text_light": "#FFFFFF",
        "tab_selected_bg_light": "#E8D0D0",  # Tab选中背景与面板一致
        "tab_selected_text_light": "#5C4033",
    },
    "薄雾蓝空": {
        "background_light": "#B8C4D8", "foreground_light": "#3A404C",
        "widget_bg_light": "#DCE4F0", "panel_bg_light": "#C8D4E8",
        "border_light": "#90A0B8", "button_bg_light": "#A0B0C8",
        "button_hover_light": "#90A0B8", "highlight_bg_light": "#7080A0",
        "text_highlight_light": "#FFFFFF", "accent1": "#607090",
        "accent2": "#E0E8F8", "nav_button_text_light": "#3A404C",
        "nav_button_hover_bg_light": "#A0B0C8", "nav_button_checked_bg_light": "#607090",
        "nav_button_checked_text_light": "#FFFFFF",
        "tab_selected_bg_light": "#C8D4E8",
        "tab_selected_text_light": "#3A404C",
    },
    "暖意灰调": {
        "background_light": "#D3CFC7", "foreground_light": "#4A4640",
        "widget_bg_light": "#E9E5E0", "panel_bg_light": "#DAD5CD",
        "border_light": "#B0ACA5", "button_bg_light": "#C0BABA",
        "button_hover_light": "#B0A8A0", "highlight_bg_light": "#908A80",
        "text_highlight_light": "#FFFFFF", "accent1": "#7D7870",
        "accent2": "#F5F0EB", "nav_button_text_light": "#4A4640",
        "nav_button_hover_bg_light": "#C0BABA", "nav_button_checked_bg_light": "#7D7870",
        "nav_button_checked_text_light": "#FFFFFF",
        "tab_selected_bg_light": "#DAD5CD",
        "tab_selected_text_light": "#4A4640",
    },
    "经典默认": {
        "background_light": "#F0F0F0", "foreground_light": "#202020",
        "widget_bg_light": "#FFFFFF", "panel_bg_light": "#F5F5F5",  # 面板背景比主窗口略深或不同
        "border_light": "#D0D0D0",  # 边框颜色更柔和
        "button_bg_light": "#E8E8E8", "button_hover_light": "#D8D8D8",
        "highlight_bg_light": "#CCE5FF", "text_highlight_light": "#000000",
        "accent1": "#0078D7", "accent2": "#B0D0F0",
        "nav_button_text_light": "#333333", "nav_button_hover_bg_light": "#E0EAF3",
        "nav_button_checked_bg_light": "#0078D7", "nav_button_checked_text_light": "#FFFFFF",
        "tab_selected_bg_light": "#F5F5F5",  # Tab选中背景与面板一致
        "tab_selected_text_light": "#005A9E",  # Tab选中文本用深一点的强调色
    }
}
CURRENT_THEME = "经典默认"


def get_current_theme_colors():
    return MORANDI_COLORS.get(CURRENT_THEME, MORANDI_COLORS["经典默认"])


def set_current_theme(theme_name):
    global CURRENT_THEME
    if theme_name in MORANDI_COLORS:
        CURRENT_THEME = theme_name
        return True
    return False


def get_app_qss():
    colors = get_current_theme_colors()
    return f"""
        /* --- 全局基础样式 --- */
        QWidget {{
            font-family: "Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif; /* 更现代的字体栈 */
            font-size: 10pt;
            color: {colors['foreground_light']};
            outline: none; /* 移除默认焦点虚线框 */
        }}
        QMainWindow, QDialog {{
            background-color: {colors['background_light']};
        }}
        /* 主内容面板 (QStackedWidget的直接子QWidget) */
        QStackedWidget > QWidget {{
            background-color: {colors.get('panel_bg_light', colors['background_light'])};
            padding: 12px; /* 面板内边距 */
        }}

        /* --- 顶部导航栏 --- */
        QWidget#TopNavigationBar {{
            background-color: {colors['background_light']};
            border-bottom: 1px solid {colors['border_light']};
            padding: 4px 8px 0px 8px; /* 微调边距 */
        }}
        QPushButton.NavButton {{
            background-color: transparent;
            color: {colors.get('nav_button_text_light', colors['foreground_light'])};
            border: none;
            padding: 7px 14px; /* 微调按钮内边距 */
            font-size: 10pt;
            font-weight: 500; /* Normal to Medium weight */
            border-radius: 4px 4px 0 0;
            min-height: 30px;
        }}
        QPushButton.NavButton:hover {{
            background-color: {colors.get('nav_button_hover_bg_light', colors['button_hover_light'])};
        }}
        QPushButton.NavButton:checked {{
            background-color: {colors.get('nav_button_checked_bg_light', colors['accent1'])};
            color: {colors.get('nav_button_checked_text_light', '#FFFFFF')};
            /* border-bottom: 2px solid {colors.get('accent2', colors['accent1'])}; */ /* 可以用背景色区分，下边框可选 */
        }}

        /* --- 通用控件 --- */
        QLabel {{
            background-color: transparent;
            padding: 1px;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: {colors['widget_bg_light']};
            border: 1px solid {colors['border_light']};
            padding: 5px 8px; /* 左右内边距稍大 */
            border-radius: 4px;
            min-height: 26px; /* 增加最小高度 */
            selection-background-color: {colors['accent1']};
            selection-color: {colors.get('text_highlight_light', '#FFFFFF')};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
            border: 1.5px solid {colors['accent1']};
             /* padding: 4.5px 7.5px; */ /* 配合边框调整padding以保持内部空间 */
        }}
        QComboBox::drop-down {{
            border-left: 1px solid {colors['border_light']};
            background-color: {colors.get('button_bg_light', colors['widget_bg_light'])};
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
        }}
        QComboBox::down-arrow {{
            /* 使用主题提供的或系统默认箭头 */
            /* image: url(:/qt-project.org/styles/commonstyle/images/arrow-down-16.png); */
        }}
        QComboBox QAbstractItemView {{ /* 下拉列表美化 */
            background-color: {colors['widget_bg_light']};
            border: 1px solid {colors['accent1']};
            selection-background-color: {colors['highlight_bg_light']};
            selection-color: {colors.get('text_highlight_light', colors['foreground_light'])};
            padding: 2px;
            border-radius: 3px; /* 下拉列表也带点圆角 */
        }}
        QListView::item, QComboBox QAbstractItemView::item {{ /* 列表项 */
            padding: 5px 8px;
        }}

        QPushButton:not(.NavButton) {{ /* 普通按钮 */
            background-color: {colors['button_bg_light']};
            border: 1px solid {colors['border_light']};
            padding: 6px 16px; /* 普通按钮的padding */
            border-radius: 4px;
            min-height: 28px;
        }}
        QPushButton:not(.NavButton):hover {{
            background-color: {colors['button_hover_light']};
        }}
        QPushButton:not(.NavButton):pressed {{
            background-color: {colors.get('highlight_bg_light', colors['button_hover_light'])}; /* 按下时颜色更深 */
        }}
        QPushButton:not(.NavButton):disabled {{
            background-color: #E0E0E0; /* 禁用时更明确的灰色 */
            color: #A0A0A0;
            border-color: #C0C0C0;
        }}

        QGroupBox {{
            font-weight: 500; /* Medium weight */
            border: 1px solid {colors.get('border_light', '#D0D0D0')};
            border-radius: 5px;
            margin-top: 12px;
            padding: 10px 12px 12px 12px; /* 上左右下 */
            background-color: transparent;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0px 8px;
            left: 8px;
            color: {colors.get('accent1', colors['foreground_light'])};
            font-weight: bold;
        }}

        QProgressBar {{
            border: 1px solid {colors['border_light']};
            border-radius: 4px;
            text-align: center;
            background-color: {colors['widget_bg_light']};
            height: 20px; /* 进度条可以细一点 */
            color: {colors['foreground_light']};
        }}
        QProgressBar::chunk {{
            background-color: {colors['accent1']};
            border-radius: 3px;
            margin: 1px;
        }}

        QTableWidget {{
            gridline-color: {colors['border_light']};
            selection-background-color: {colors['highlight_bg_light']};
            selection-color: {colors.get('text_highlight_light', colors['foreground_light'])};
            background-color: {colors['widget_bg_light']};
            border: 1px solid {colors['border_light']};
            border-radius: 3px;
        }}
        QHeaderView::section {{
            background-color: {colors.get('button_bg_light', colors['background_light'])};
            color: {colors['foreground_light']};
            padding: 6px; /* 表头padding */
            border: none;
            border-bottom: 1px solid {colors['border_light']};
            font-weight: 500; /* Medium weight */
        }}

        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            border: none; background: {colors.get('widget_bg_light', '#F0F0F0')}; width: 10px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {colors.get('border_light', '#B0B0B0')}; min-height: 30px; border-radius: 5px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; }}
        QScrollBar:horizontal {{
            border: none; background: {colors.get('widget_bg_light', '#F0F0F0')}; height: 10px; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {colors.get('border_light', '#B0B0B0')}; min-width: 30px; border-radius: 5px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ border: none; background: none; width: 0px; }}

        /* --- QTabWidget 样式 (用于HelpPanel) --- */
        QTabWidget::pane {{
            border: 1px solid {colors['border_light']};
            border-top: none;
            background-color: {colors.get('panel_bg_light', colors['widget_bg_light'])}; /* Tab内容区域背景 */
            padding: 10px;
            border-bottom-left-radius: 3px;
            border-bottom-right-radius: 3px;
        }}
        QTabBar::tab {{
            background-color: {colors.get('button_bg_light', colors['background_light'])};
            color: {colors.get('nav_button_text_light', colors['foreground_light'])};
            border: 1px solid {colors['border_light']};
            border-bottom: none;
            padding: 7px 18px; /* Tab标签内边距 */
            margin-right: 1px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            min-width: 70px;
        }}
        QTabBar::tab:selected {{
            background-color: {colors.get('tab_selected_bg_light', colors.get('panel_bg_light', colors['widget_bg_light']))};
            color: {colors.get('tab_selected_text_light', colors['accent1'])};
            font-weight: bold;
            /* margin-bottom: -1px; */ /* 轻微下移，与pane连接更紧密 */
        }}
        QTabBar::tab:hover {{
            background-color: {colors.get('nav_button_hover_bg_light', colors['button_hover_light'])};
        }}
        QTabWidget::tab-bar {{
            alignment: left;
            /* qproperty-drawBase: 0; */ /* 移除Tab栏下方的额外线条 (如果存在) */
        }}

        /* 特定ID控件 */
        #QuestionTextLabel {{ font-size: 11pt; font-weight: bold; padding-bottom: 6px; }}
        #StatusLog {{ /* 全局日志输出 QTextEdit */
            font-family: "Consolas", "Courier New", monospace;
            font-size: 9pt;
            background-color: {colors.get('widget_bg_light')};
            border: 1px solid {colors['border_light']};
            border-radius: 3px;
            padding: 5px;
        }}
        QTextBrowser {{ /* 用于显示HTML内容的浏览器 */
            background-color: {colors['widget_bg_light']};
            border: 1px solid {colors['border_light']};
            border-radius: 3px;
            padding: 10px; /* 给HTML内容一些内边距 */
        }}
    """