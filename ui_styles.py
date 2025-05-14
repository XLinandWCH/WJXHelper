# ui_styles.py

MORANDI_COLORS = {
    "灰粉玫瑰": { # DustyRose
        "background_light": "#E0C0C0",
        "foreground_light": "#5C4033",
        "widget_bg_light": "#F0E0E0",
        "border_light": "#C0A0A0",
        "button_bg_light": "#D8B0B0",
        "button_hover_light": "#C8A0A0",
        "highlight_bg_light": "#B08080",
        "text_highlight_light": "#FFFFFF",
        "accent1": "#A07070",
        "accent2": "#F8D0D0",
    },
    "薄雾蓝空": { # MistyBlue
        "background_light": "#B8C4D8",
        "foreground_light": "#3A404C",
        "widget_bg_light": "#DCE4F0",
        "border_light": "#90A0B8",
        "button_bg_light": "#A0B0C8",
        "button_hover_light": "#90A0B8",
        "highlight_bg_light": "#7080A0",
        "text_highlight_light": "#FFFFFF",
        "accent1": "#607090",
        "accent2": "#E0E8F8",
    },
    "暖意灰调": { # WarmGrey
        "background_light": "#D3CFC7",
        "foreground_light": "#4A4640",
        "widget_bg_light": "#E9E5E0",
        "border_light": "#B0ACA5",
        "button_bg_light": "#C0BABA",
        "button_hover_light": "#B0A8A0",
        "highlight_bg_light": "#908A80",
        "text_highlight_light": "#FFFFFF",
        "accent1": "#7D7870",
        "accent2": "#F5F0EB",
    },
    "经典默认": { # Default
        "background_light": "#F0F0F0",
        "foreground_light": "#202020",
        "widget_bg_light": "#FFFFFF",
        "border_light": "#C0C0C0",
        "button_bg_light": "#E0E0E0",
        "button_hover_light": "#D0D0D0",
        "highlight_bg_light": "#A0C0E0",
        "text_highlight_light": "#000000",
        "accent1": "#0078D7",
        "accent2": "#B0D0F0",
    }
}

CURRENT_THEME = "经典默认" # 默认主题名称，使用中文

def get_current_theme_colors():
    return MORANDI_COLORS.get(CURRENT_THEME, MORANDI_COLORS["经典默认"]) # 确保默认值也用中文key

def set_current_theme(theme_name):
    global CURRENT_THEME
    if theme_name in MORANDI_COLORS:
        CURRENT_THEME = theme_name
        return True
    return False

def get_app_qss():
    colors = get_current_theme_colors()
    # QSS 内容保持不变，它引用的是 colors 字典的键（这些键名没有变）
    return f"""
        QWidget {{
            font-family: "Microsoft YaHei", "SimSun", sans-serif;
            font-size: 10pt; 
            color: {colors['foreground_light']};
        }}
        QMainWindow, QDialog {{
            background-color: {colors['background_light']};
        }}
        QMenuBar {{
            background-color: {colors.get('button_bg_light', colors['background_light'])};
            color: {colors['foreground_light']};
            border-bottom: 1px solid {colors['border_light']};
        }}
        QMenuBar::item:selected {{
            background-color: {colors['highlight_bg_light']};
            color: {colors.get('text_highlight_light', colors['foreground_light'])};
        }}
        QMenu {{
            background-color: {colors.get('widget_bg_light', colors['background_light'])};
            border: 1px solid {colors['border_light']};
        }}
        QMenu::item:selected {{
            background-color: {colors['highlight_bg_light']};
            color: {colors.get('text_highlight_light', colors['foreground_light'])};
        }}
        QStatusBar {{
            background-color: {colors.get('button_bg_light', colors['background_light'])};
            color: {colors['foreground_light']};
            border-top: 1px solid {colors['border_light']};
        }}
        QLabel {{
            background-color: transparent;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: {colors['widget_bg_light']};
            border: 1px solid {colors['border_light']};
            padding: 5px; /* 增加一点内边距 */
            border-radius: 4px; /* 圆角稍大一些 */
            selection-background-color: {colors['accent1']}; /* 选中文字背景色 */
            selection-color: {colors.get('text_highlight_light', '#FFFFFF')}; /* 选中文字颜色 */
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
            border: 1.5px solid {colors['accent1']}; /* 焦点边框加粗一点 */
        }}
        QComboBox::drop-down {{
            border-left: 1px solid {colors['border_light']};
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px; /* 略微加宽下拉按钮 */
        }}
        /* 移除了自定义箭头，让系统默认箭头显示，更统一，除非有好的图标资源
        QComboBox::down-arrow {{
            image: url(./icons/down_arrow.png); 
        }}
        */
        QListView {{ 
            background-color: {colors['widget_bg_light']};
            border: 1px solid {colors['border_light']};
            outline: 0px;
        }}
        QListView::item:selected {{
            background-color: {colors['highlight_bg_light']};
            color: {colors.get('text_highlight_light', colors['foreground_light'])};
        }}
        QPushButton {{
            background-color: {colors['button_bg_light']};
            border: 1px solid {colors['border_light']};
            padding: 7px 15px; /* 增加按钮内边距 */
            min-height: 20px; /* 确保按钮有一定高度 */
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {colors['button_hover_light']};
            border: 1px solid {colors.get('accent1', colors['border_light'])};
        }}
        QPushButton:pressed {{
            background-color: {colors['highlight_bg_light']};
        }}
        QPushButton:disabled {{
            background-color: #D0D0D0; 
            color: #808080;
        }}
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {colors['border_light']};
            border-radius: 5px; /* 增加圆角 */
            margin-top: 12px; 
            padding: 12px; /* 增加内边距 */
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 2px 8px; /* 增加标题内边距 */
            left: 10px;
            background-color: {colors['background_light']};
        }}
        QTabWidget::pane {{
            border: 1px solid {colors['border_light']};
            border-top: none;
            background-color: {colors['background_light']};
            padding: 15px; /* 增加Tab内容区域内边距 */
        }}
        QTabBar::tab {{
            background-color: {colors['button_bg_light']};
            border: 1px solid {colors['border_light']};
            border-bottom: none;
            padding: 10px 18px; /* 增加Tab标签内边距 */
            margin-right: 2px;
            border-top-left-radius: 5px; /* 增加圆角 */
            border-top-right-radius: 5px;
        }}
        QTabBar::tab:selected {{
            background-color: {colors['background_light']};
            border-bottom: 1px solid {colors['background_light']};
            font-weight: bold;
        }}
        QTabBar::tab:hover {{
            background-color: {colors['button_hover_light']};
        }}
        QProgressBar {{
            border: 1px solid {colors['border_light']};
            border-radius: 4px; /* 增加圆角 */
            text-align: center;
            background-color: {colors['widget_bg_light']};
            height: 24px; 
        }}
        QProgressBar::chunk {{
            background-color: {colors['accent1']};
            border-radius: 3px; 
            margin: 1px; 
        }}
        QScrollArea {{
            border: 1px solid {colors['border_light']};
            background-color: {colors['widget_bg_light']};
        }}
        QScrollBar:vertical {{
            border: none;
            background: {colors.get('widget_bg_light', '#E0E0E0')}; /* 确保有背景色 */
            width: 12px; /* 略微加宽滚动条 */
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {colors.get('border_light', '#A0A0A0')};
            min-height: 25px; /* 手柄最小高度 */
            border-radius: 6px; /* 更圆的滚动条手柄 */
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: {colors.get('widget_bg_light', '#E0E0E0')};
            height: 12px;
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {colors.get('border_light', '#A0A0A0')};
            min-width: 25px;
            border-radius: 6px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
            width: 0px;
        }}
        #QuestionTextLabel {{
            font-size: 11pt;
            font-weight: bold;
            padding-bottom: 5px; /* 问题文本下方增加一点间距 */
        }}
        #StatusLog {{ 
            font-family: "Consolas", "Courier New", monospace;
            font-size: 9pt; /* 日志字体可以小一点 */
        }}
        /* 可以为对话框也指定一些样式 */
        QDialog QLabel {{ /* 对话框中的标签默认左对齐 */
            text-align: left;
        }}
        QDialog QPushButton {{ /* 对话框中的按钮可以有统一边距 */
            margin-top: 5px;
        }}
    """

