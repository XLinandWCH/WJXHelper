# widgets_questionnaire_setup.py
# 本文件包含问卷设置和配置的主界面部件。
# 负责加载问卷、显示题目、允许用户配置填写规则、以及导入/导出配置。

import random
import os
import json
import re  # 导入正则表达式模块
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTextEdit, QScrollArea, QFrame, QGroupBox,
                             QSpacerItem, QSizePolicy, QMessageBox, QApplication,
                             QFileDialog, QCheckBox, QSplitter) # 导入 QSplitter
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QIntValidator

# 从本地模块导入问卷解析和工具函数
from questionnaire_parser import fetch_questionnaire_structure
from utils import parse_weights_from_string, calculate_choice_from_weights, calculate_multiple_choices_from_percentages, decrypt_data
from ai_service import get_ai_suggestions


class AIConfigThread(QThread):
    """在后台线程中运行AI配置请求"""
    finished_signal = pyqtSignal(dict)

    def __init__(self, provider, api_key, user_prompt, structure, chat_history, model_name=None, proxy=None, base_url=None):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.user_prompt = user_prompt
        self.structure = structure
        self.chat_history = chat_history
        self.model_name = model_name
        self.proxy = proxy
        self.base_url = base_url

    def run(self):
        result = get_ai_suggestions(self.provider, self.api_key, self.user_prompt, self.structure, self.chat_history, self.model_name, self.proxy, self.base_url)
        self.finished_signal.emit(result)


class ParserThread(QThread):
    """
    一个独立的QThread，用于在后台执行问卷结构解析，避免UI卡顿。
    解析完成后通过信号将结果发射出去。
    """
    finished_signal = pyqtSignal(object)  # 可以发射任何类型的对象，这里是解析结果（列表或字典）

    def __init__(self, url, browser_type="edge", driver_path=None, headless_for_parser=True,
                 base_user_data_dir=None):
        """
        初始化解析线程。
        :param url: 待解析问卷的URL。
        :param browser_type: 使用的浏览器类型（如"edge", "chrome"）。
        :param driver_path: 浏览器驱动的路径。
        :param headless_for_parser: 是否以无头模式运行浏览器。
        :param base_user_data_dir: 用户数据目录的基础路径，用于创建独立的浏览器配置文件。
        """
        super().__init__()
        self.url = url
        self.browser_type = browser_type
        self.driver_path = driver_path
        self.headless_for_parser = headless_for_parser
        self.base_user_data_dir = base_user_data_dir

    def run(self):
        """
        线程的执行入口。在这里调用问卷结构解析函数。
        """
        # 在这里添加一个检查，确保当停止信号发出时，线程能够退出
        # 但对于 WebDriver 启动/get 等阻塞操作，线程内部很难响应。
        # 这主要依赖于外部在调用 start() 后管理线程生命周期。
        # 对于长时间解析，需要确保 fetch_questionnaire_structure 内部有超时或中断机制。
        # 目前假设 fetch_questionnaire_structure 内部已经有超时机制。
        result = fetch_questionnaire_structure(self.url, browser_type=self.browser_type,
                                               driver_executable_path=self.driver_path,
                                               headless=self.headless_for_parser,
                                               base_user_data_dir_path=self.base_user_data_dir)
        self.finished_signal.emit(result)  # 将解析结果通过信号发射出去


class QuestionnaireSetupWidget(QWidget):
    """
    问卷设置和配置的主界面部件。
    负责加载问卷、显示题目、允许用户配置填写规则、以及导入/导出配置。
    """
    # 定义填空题随机分隔符为类属性，方便统一管理
    FILL_IN_BLANK_SEPARATOR_RANDOM = "||"
    # 定义填空题顺序分隔符的起始和结束标记为类属性
    FILL_IN_BLANK_MARKER_SEQ_START = "["
    FILL_IN_BLANK_MARKER_SEQ_END = "]"

    def __init__(self, parent=None):
        """
        初始化问卷设置部件。
        :param parent: 父QObject，通常是主窗口。
        """
        super().__init__(parent)
        self.main_window_ref = parent  # 保存主窗口引用，以便获取浏览器配置和更新状态栏
        self.parsed_data = None  # 存储解析后的问卷结构数据
        self.question_widgets_map = {}  # 存储问题ID到其对应的UI控件的映射
        self._last_io_directory = os.path.expanduser("~")  # 记住上次文件对话框打开的目录，方便用户
        self.ai_chat_log = [] # Initialize chat history log
        self._init_ui()  # 初始化用户界面

    def _init_ui(self):
        """
        初始化用户界面布局和控件。
        """
        main_layout = QVBoxLayout(self)

        # 问卷链接输入区域
        url_group = QGroupBox("问卷链接")
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("问卷URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入完整的问卷星链接 (例如: https://www.wjx.cn/vm/xxxx.aspx)")
        url_layout.addWidget(self.url_input, 1)  # 填满可用空间
        self.load_button = QPushButton("加载问卷")
        self.load_button.clicked.connect(self._load_questionnaire)  # 连接加载问卷槽函数
        url_layout.addWidget(self.load_button)
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)

        # --- 主布局改造：使用 QSplitter ---
        self.main_splitter = QSplitter(Qt.Horizontal)

        # 左侧：问卷配置区域
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0,0,0,0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.StyledPanel)
        self.questions_container_widget = QWidget()
        self.questions_layout = QVBoxLayout(self.questions_container_widget)
        self.questions_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.questions_container_widget)
        left_layout.addWidget(self.scroll_area)

        # 右侧：AI 助手聊天窗口
        right_panel = self._create_ai_panel()

        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(right_panel)
        
        # 设置初始分割比例，让AI窗口默认隐藏
        self.main_splitter.setSizes([self.width(), 0])
        self.main_splitter.setCollapsible(1, True) # 允许第二个窗口完全折叠

        main_layout.addWidget(self.main_splitter, 1)

        # 导入/导出配置按钮布局
        io_button_layout = QHBoxLayout()
        self.import_weights_button = QPushButton("导入配置")
        self.import_weights_button.setObjectName("importConfigButton")
        self.import_weights_button.setToolTip("从JSON文件加载之前保存的问卷配置")
        self.import_weights_button.clicked.connect(self.handle_import_weights)  # 连接导入槽函数

        self.save_weights_button = QPushButton("保存配置")
        self.save_weights_button.setObjectName("saveConfigButton")
        self.save_weights_button.setToolTip("将当前问卷的所有题目配置保存到JSON文件")
        self.save_weights_button.clicked.connect(self.handle_save_weights)  # 连接保存槽函数

        io_button_layout.addStretch()  # 伸缩空间，将按钮推到右边
        io_button_layout.addWidget(self.import_weights_button)
        io_button_layout.addWidget(self.save_weights_button)
        main_layout.addLayout(io_button_layout)

        # 状态标签，显示操作提示或结果
        self.status_label = QLabel("请先输入问卷URL并点击“加载问卷”。")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.parser_thread = None  # 用于问卷解析的线程实例，避免UI卡顿
        self.ai_thread = None # 用于AI配置的线程实例

    def _create_ai_panel(self):
        """创建AI助手面板UI"""
        ai_panel = QWidget()
        ai_panel_layout = QVBoxLayout(ai_panel)
        ai_panel_layout.setContentsMargins(5, 5, 5, 5)
        ai_panel_layout.setSpacing(8)

        ai_group = QGroupBox("AI 助手")
        ai_group_layout = QVBoxLayout(ai_group)

        self.ai_chat_history = QTextEdit()
        self.ai_chat_history.setReadOnly(True)
        self.ai_chat_history.setPlaceholderText("与AI对话，让它帮你配置问卷。\n例如：\n- 帮我把所有单选题都设置成随机选择\n- 把关于“满意度”的题目都设置成偏向于“非常满意”\n- 帮我写5个关于“大学食堂”的建议")
        
        ai_input_layout = QHBoxLayout()
        self.ai_prompt_input = QLineEdit()
        self.ai_prompt_input.setPlaceholderText("输入你的要求...")
        self.ai_send_button = QPushButton("发送")

        ai_input_layout.addWidget(self.ai_prompt_input, 1)
        ai_input_layout.addWidget(self.ai_send_button)

        ai_group_layout.addWidget(self.ai_chat_history, 1)
        ai_group_layout.addLayout(ai_input_layout)
        
        ai_panel_layout.addWidget(ai_group)
        
        # 连接信号
        self.ai_send_button.clicked.connect(self._handle_ai_prompt)
        self.ai_prompt_input.returnPressed.connect(self._handle_ai_prompt)

        return ai_panel

    def _load_questionnaire(self):
        """
        根据用户输入的URL加载并解析问卷。
        """
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入问卷URL.")
            return
        # 检查URL格式是否大致正确
        if not url.startswith("http://") and not url.startswith("https://"):
             QMessageBox.warning(self, "提示", "请输入有效的问卷URL (以http或https开头)。")
             return

        if self.parser_thread and self.parser_thread.isRunning():
            QMessageBox.information(self, "提示", "正在解析中，请稍候...")
            return

        self.load_button.setEnabled(False)  # 禁用加载按钮，避免重复点击
        self.status_label.setText(f"正在加载和解析问卷: {url} ... 请耐心等待。")
        # 更新主窗口状态栏提示，如果主窗口存在
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage("问卷解析中...")

        self._clear_question_widgets()  # 清空之前加载的问题控件
        self.parsed_data = None
        self.question_widgets_map = {}
        self.ai_chat_log = [] # Clear chat history on new questionnaire
        self.ai_chat_history.clear() # Clear chat history display

        # 从主窗口获取浏览器配置信息，用于解析器线程
        browser_type_to_use = "edge"
        driver_path_to_use = None
        headless_for_parser_val = True
        base_user_data_dir_for_parser = None

        if self.main_window_ref:
            browser_type_to_use = getattr(self.main_window_ref, 'current_browser_type', "edge")
            driver_path_to_use = getattr(self.main_window_ref, 'current_driver_path', None)
            if hasattr(self.main_window_ref, 'settings'):
                # 解析器通常设置为无头模式更快
                headless_for_parser_val = self.main_window_ref.settings.value("headless_mode_parser", True, type=bool)
            # 使用worker共享的基础用户数据目录路径，这样解析器和填报器可以使用相似的环境
            base_user_data_dir_for_parser = getattr(self.main_window_ref, 'base_user_data_dir_for_workers', None)
        else:
            # 兜底处理
            print("警告: main_window_ref 未设置或缺少settings属性，使用默认浏览器配置进行解析。")
            # 默认使用无头
            headless_for_parser_val = True


        print(
            f"问卷设置: 解析器将使用浏览器 '{browser_type_to_use}', 驱动路径 '{driver_path_to_use}', 无头模式: {headless_for_parser_val}, 用户数据目录基础: {base_user_data_dir_for_parser}")

        # 创建并启动解析器线程
        self.parser_thread = ParserThread(url, browser_type_to_use, driver_path_to_use, headless_for_parser_val,
                                          base_user_data_dir_for_parser)
        self.parser_thread.finished_signal.connect(self._on_parsing_finished)  # 连接解析完成槽函数
        self.parser_thread.start()

    def _on_parsing_finished(self, result):
        """
        处理问卷解析线程完成后的结果。
        :param result: 解析线程返回的结果，可以是问题列表或包含“error”键的字典。
        """
        self.load_button.setEnabled(True)  # 重新启用加载按钮
        status_bar_available = self.main_window_ref and hasattr(self.main_window_ref, 'statusBar')

        if isinstance(result, dict) and "error" in result:  # 解析失败
            error_message = result.get('error', '未知错误'); # 获取错误信息，提供默认值
            self.status_label.setText(f"问卷解析失败: {error_message}")
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage(f"问卷解析失败: {error_message[:50]}...") # 状态栏显示部分错误信息
            QMessageBox.critical(self, "解析错误", f"解析问卷时发生错误：\n{error_message}")
            self.parsed_data = result  # 保存错误结果
        elif result and isinstance(result, list) and len(result) > 0:  # 解析成功并获取到问题列表
            self.parsed_data = result
            self.status_label.setText(f"成功解析到 {len(result)} 个问题。请在下方配置各项答案。")
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage(f"问卷解析成功，共 {len(result)} 个问题。")
            self._display_questions(result)  # 显示问题配置界面
        else:  # 解析结果为空或异常情况
            default_error_msg = "未能从问卷中解析出任何问题结构，或驱动启动失败，或问卷为空。"
            self.status_label.setText(default_error_msg)
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage("问卷解析结果为空或失败。")
            QMessageBox.warning(self, "解析结果", default_error_msg)
            self.parsed_data = {"error": default_error_msg} # 记录错误信息

        self.parser_thread = None  # 清空线程引用

    def _clear_question_widgets(self):
        """
        清空当前显示的所有问题配置控件。
        """
        # 销毁所有子控件
        while self.questions_layout.count():
            child = self.questions_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()  # 确保控件被正确销毁和释放内存
            # 如果是布局，也需要处理其中的控件，或者直接deleteLater子widget更直接
            # For simplicity and robustness with different child types (widgets, layouts),
            # directly deleting widgets using deleteLater() on retrieved item's widget
            # is generally preferred after taking them from layout.
        self.question_widgets_map.clear()  # 清空问题ID与控件的映射

    def _display_questions(self, questions_data):
        """
        根据解析出的问题数据动态生成配置UI。
        :param questions_data: 包含问卷所有问题的列表。
        """
        # 用于统计每种类型题目的序号，方便显示
        type_counters = {str(k): 0 for k in range(1, 12)}
        # 初始化常见题型计数器
        type_counters.update({str(k): 0 for k in [1, 2, 3, 4, 5, 6, 7, 8, 11]})

        for q_idx, q_data in enumerate(questions_data):
            q_id = q_data.get('id')
            q_topic = q_data.get('topic_num')
            q_type = q_data.get('type_code')
            q_text = q_data.get('text')
            q_options = q_data.get('options', [])
            q_sub_questions = q_data.get('sub_questions', [])

            # 如果缺少关键信息，跳过此问题
            if not q_id or not q_topic or not q_type:
                 print(f"警告: 跳过一个结构不完整的问题数据: {q_data}")
                 continue


            type_counters[str(q_type)] = type_counters.get(str(q_type), 0) + 1
            # 构建问题分组框标题
            q_groupbox_title = (
                f"题目 {q_data.get('question_index_overall', q_idx + 1)} (原始题号: {q_topic}, 类型: {self._get_question_type_name(q_type)} - 第{type_counters[str(q_type)]}个此类题)")
            q_groupbox = QGroupBox(q_groupbox_title)
            q_group_layout = QVBoxLayout()
            q_text_label = QLabel(q_text)
            q_text_label.setWordWrap(True)  # 允许文本换行
            q_text_label.setObjectName("QuestionTextLabel")
            q_group_layout.addWidget(q_text_label)

            # 存储问题ID与相关UI控件的映射，为保存/导入和获取配置做准备
            self.question_widgets_map[q_id] = {"type": q_type, "q_data": q_data, "options_controls": [],
                                               "sub_questions_controls": []}

            # 根据问题类型生成不同的配置控件
            if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                # 提示用户两种填写格式的语法
                text_input_label = QLabel(
                    f"请输入填空内容。<br/>"
                    f"- <b>随机选择</b> (多个备选答案用 \"{self.FILL_IN_BLANK_SEPARATOR_RANDOM}\" 分隔)<br/>"
                    f"  例如: 答案一{self.FILL_IN_BLANK_SEPARATOR_RANDOM}答案二<br/>"
                    f"- <b>顺序填写</b> (多个备选答案用 \"{self.FILL_IN_BLANK_MARKER_SEQ_START}答案{self.FILL_IN_BLANK_MARKER_SEQ_END}\" 包裹，填报时依序不重复)<br/>"
                    f"  例如: {self.FILL_IN_BLANK_MARKER_SEQ_START}张三{self.FILL_IN_BLANK_MARKER_SEQ_END}{self.FILL_IN_BLANK_MARKER_SEQ_START}李四{self.FILL_IN_BLANK_MARKER_SEQ_END}{self.FILL_IN_BLANK_MARKER_SEQ_START}王五{self.FILL_IN_BLANK_MARKER_SEQ_END}"
                )
                text_input_label.setTextFormat(Qt.RichText)  # 支持富文本（HTML标签）
                text_input = QLineEdit()
                text_input.setPlaceholderText(
                    f"例如: 随机答案一{self.FILL_IN_BLANK_SEPARATOR_RANDOM}随机答案二 或 {self.FILL_IN_BLANK_MARKER_SEQ_START}顺序答案一{self.FILL_IN_BLANK_MARKER_SEQ_END}{self.FILL_IN_BLANK_MARKER_SEQ_START}顺序答案二{self.FILL_IN_BLANK_MARKER_SEQ_END}"
                )
                self.question_widgets_map[q_id]["raw_text_input_widget"] = text_input  # 存储输入控件
                q_group_layout.addWidget(text_input_label)
                q_group_layout.addWidget(text_input)
            elif q_type in ["3", "5", "7"]:  # 单选题 / 量表题 / 下拉选择题 (权重选择)
                if not q_options:  # 如果没有解析到选项
                    q_group_layout.addWidget(QLabel("警告: 此选择题未解析到任何选项，无法配置。"))
                else:
                    # 权重输入提示
                    q_group_layout.addWidget(QLabel("请为每个选项设置权重 (整数，用英文逗号隔开，例如: 30,70,0):"))
                    options_layout = QVBoxLayout()
                    # 显示每个选项文本，并为“其他”选项添加自定义文本配置
                    for opt_idx, option_data in enumerate(q_options):
                        # 为每个选项创建一个水平布局，用于放置标签和可能的其他配置控件
                        option_config_layout = QHBoxLayout()
                        option_label = QLabel(f"选项 {opt_idx + 1}: {option_data['text']}")
                        option_config_layout.addWidget(option_label)
                        option_config_layout.addStretch(1) # 标签后添加伸缩空间

                        # 为识别为“其他”选项的单选/量表/下拉题添加自定义文本输入控件
                        if option_data.get("is_other_specify"): # 这里假设parser已正确标记“其他”项
                            other_text_checkbox = QCheckBox("自定义文本:")
                            other_text_checkbox.setChecked(False)  # 默认不启用自定义文本
                            other_text_qlineedit = QLineEdit()
                            other_text_qlineedit.setPlaceholderText(f"多个用 \"{self.FILL_IN_BLANK_SEPARATOR_RANDOM}\" 分隔，随机选择")
                            other_text_qlineedit.setEnabled(False)  # 默认禁用
                            other_text_checkbox.toggled.connect(other_text_qlineedit.setEnabled) # 连接复选框状态与文本框启用状态

                            option_config_layout.addWidget(other_text_checkbox)
                            option_config_layout.addWidget(other_text_qlineedit, 1) # 文本框填满剩余空间

                            # 存储“其他”选项相关的UI控件
                            self.question_widgets_map[q_id]["options_controls"].append({
                                "type": "other_config_group", # 标记控件组类型
                                "option_original_index": option_data["original_index"], # 关联回原始选项索引
                                "checkbox_widget": other_text_checkbox,
                                "text_input_widget": other_text_qlineedit,
                            })

                        options_layout.addLayout(option_config_layout) # 将选项配置水平布局添加到垂直选项布局中

                    # 权重输入控件
                    weight_input = QLineEdit()
                    default_weights = ",".join(["1"] * len(q_options))  # 默认等权重
                    weight_input.setPlaceholderText(f"例如: {default_weights}")
                    weight_input.setText(default_weights)
                    self.question_widgets_map[q_id]["raw_weight_input_widget"] = weight_input
                    options_layout.addWidget(weight_input)
                    q_group_layout.addLayout(options_layout)
            elif q_type == "4":  # 多选题 (概率选择 + 必选)
                if not q_options:  # 如果没有解析到选项
                    q_group_layout.addWidget(QLabel("警告: 此多选题未解析到任何选项，无法配置。"))
                else:
                    # 概率和必选输入提示
                    q_group_layout.addWidget(QLabel("请为每个选项设置被选中的概率 (0-100整数，用英文逗号隔开)。勾选“必选”则强制选中。"))
                    options_layout = QVBoxLayout()
                    default_probs = ["50"] * len(q_options)  # 默认50%概率
                    # 显示每个选项文本，并为“其他”选项添加自定义文本配置，同时添加“必选”复选框
                    for opt_idx, option_data in enumerate(q_options):
                        option_config_layout = QHBoxLayout() # 水平布局：标签 + [必选] + [自定义文本]
                        option_label = QLabel(f"选项 {opt_idx + 1}: {option_data['text']}")
                        option_config_layout.addWidget(option_label)
                        option_config_layout.addStretch(1) # 标签后添加伸缩空间

                        # 添加“必选”复选框
                        must_select_checkbox = QCheckBox("必选")
                        must_select_checkbox.setChecked(False) # 默认不必选
                        option_config_layout.addWidget(must_select_checkbox)

                        # 存储“必选”复选框控件，关联回原始选项索引
                        # 同时存储原始选项数据，方便后续获取original_index等信息
                        self.question_widgets_map[q_id]["options_controls"].append({
                            "type": "must_select_config", # 标记控件组类型
                            "option_data": option_data, # 存储原始选项数据
                            "checkbox_widget": must_select_checkbox,
                        })

                        # 为识别为“其他”选项的多选题添加自定义文本输入控件
                        if option_data.get("is_other_specify"):
                            other_text_checkbox = QCheckBox("自定义文本:")
                            other_text_checkbox.setChecked(False)
                            other_text_qlineedit = QLineEdit()
                            other_text_qlineedit.setPlaceholderText(f"多个用 \"{self.FILL_IN_BLANK_SEPARATOR_RANDOM}\" 分隔，随机选择")
                            other_text_qlineedit.setEnabled(False)
                            other_text_checkbox.toggled.connect(other_text_qlineedit.setEnabled)

                            option_config_layout.addWidget(other_text_checkbox)
                            option_config_layout.addWidget(other_text_qlineedit, 1)

                            # 存储“其他”选项相关的UI控件
                            # 注意：一个选项可能同时是“其他”项和有“必选”配置，所以这里可能添加到同一个options_controls列表中，
                            # 但需要通过type字段区分不同的配置组。
                            self.question_widgets_map[q_id]["options_controls"].append({
                                "type": "other_config_group", # 标记控件组类型
                                "option_original_index": option_data["original_index"], # 关联回原始选项索引
                                "checkbox_widget": other_text_checkbox,
                                "text_input_widget": other_text_qlineedit,
                            })

                        options_layout.addLayout(option_config_layout) # 将选项配置水平布局添加到垂直选项布局中

                    # 概率输入控件 (仍然需要，用于非必选选项的随机选择)
                    prob_input_line = QLineEdit()
                    prob_input_line.setPlaceholderText(f"例如: {','.join(default_probs)}")
                    prob_input_line.setText(",".join(default_probs))
                    self.question_widgets_map[q_id]["raw_prob_input_widget"] = prob_input_line
                    options_layout.addWidget(prob_input_line)
                    q_group_layout.addLayout(options_layout)
            elif q_type == "6":  # 矩阵题 (权重选择)
                if not q_sub_questions or not any(sub_q.get("options") for sub_q in q_sub_questions): # 检查是否有子问题且子问题有选项
                    q_group_layout.addWidget(QLabel("警告: 此矩阵题未解析到足够的子问题或选项结构，无法配置。"))
                else:
                    # 子问题权重输入提示
                    q_group_layout.addWidget(QLabel("请为每个子问题的选项设置权重 (类似单选题，每行一个配置):"))
                    sub_q_controls_list = []  # 存储子问题相关的UI控件
                    for sub_q_idx, sub_q_data in enumerate(q_sub_questions):
                        sub_q_label = QLabel(f"子问题 {sub_q_idx + 1}: {sub_q_data.get('text', '无文本')}") # 显示子问题文本
                        q_group_layout.addWidget(sub_q_label)
                        sub_q_options_list = sub_q_data.get('options', [])
                        if not sub_q_options_list:
                            q_group_layout.addWidget(QLabel(f"  警告: 子问题 {sub_q_idx + 1} 未解析到选项。"))
                            continue
                        # 显示子问题的选项文本
                        options_display_text = "  可选答案: " + " | ".join(
                            [opt.get('text', f'选项{i+1}') for i, opt in enumerate(sub_q_options_list)])
                        q_group_layout.addWidget(QLabel(options_display_text))
                        # 子问题权重输入控件
                        sub_q_weight_input = QLineEdit()
                        default_sub_q_weights = ",".join(["1"] * len(sub_q_options_list))
                        sub_q_weight_input.setPlaceholderText(f"例如: {default_sub_q_weights}")
                        sub_q_weight_input.setText(default_sub_q_weights)
                        q_group_layout.addWidget(sub_q_weight_input)
                        # 存储子问题控制信息，包括原始数据和权重输入控件
                        sub_q_controls_list.append(
                            {"sub_q_data": sub_q_data, "raw_weight_input_widget": sub_q_weight_input})
                    self.question_widgets_map[q_id]["sub_questions_controls"] = sub_q_controls_list
            elif q_type == "8":  # 滑块题
                # 滑块值输入提示
                q_group_layout.addWidget(QLabel("请输入滑块的值 (通常是1-100的整数，或用英文逗号分隔多个值及权重，如 值1,值2,...:权重1,权重2,...):"))
                slider_value_input = QLineEdit()
                slider_value_input.setPlaceholderText("例如: 75  或者  60,80:1,1")
                slider_value_input.setText("75")  # 默认值
                self.question_widgets_map[q_id]["raw_slider_input_widget"] = slider_value_input
                q_group_layout.addWidget(slider_value_input)
            elif q_type == "11":  # 排序题
                q_group_layout.addWidget(QLabel("排序题将自动进行随机排序，无需配置。"))
                # 显示可排序项
                if q_options:
                    q_group_layout.addWidget(QLabel("可排序项:"))
                    for opt_data in q_options:
                        q_group_layout.addWidget(QLabel(f"  - {opt_data.get('text', '无文本')}")) # 显示选项文本
                else:
                     q_group_layout.addWidget(QLabel("警告: 排序题未解析到任何选项，无法排序。")) # 如果没有选项，也给出提示
            else:  # 其他不支持配置的题型
                q_group_layout.addWidget(
                    QLabel(f"此题型 ({self._get_question_type_name(q_type)}) 目前不支持详细配置或无需配置，将尝试默认处理或跳过。"))

            q_groupbox.setLayout(q_group_layout)
            self.questions_layout.addWidget(q_groupbox)  # 将问题分组框添加到布局中
        self.questions_layout.addStretch(1)  # 在问题列表下方添加伸缩空间

    def _get_question_type_name(self, type_code):
        """
        根据问题类型代码获取对应的中文名称。
        """
        return {"1": "填空题", "2": "多行填空题", "3": "单选题", "4": "多选题", "5": "量表题", "6": "矩阵题",
                "7": "下拉选择题", "8": "滑块题", "11": "排序题"}.get(str(type_code), f"未知类型({type_code})")

    def get_parsed_questionnaire_data(self):
        """
        返回解析后的原始问卷结构数据。
        """
        return self.parsed_data

    def get_user_raw_configurations_template(self):
        """
        从UI控件中获取用户配置，并生成供工作线程使用的配置模板。
        这个模板包含了问题ID、类型、以及用户为每个问题设定的具体填写规则（如文本内容、权重、概率、必选标记等）。
        对于填空题，会解析其填写格式（随机或顺序）。
        """
        # 检查是否有成功的解析数据
        if not self.parsed_data or (
                isinstance(self.parsed_data, dict) and "error" in self.parsed_data) or not isinstance(self.parsed_data,
                                                                                                      list):
            # 如果没有成功的解析数据，则无法生成配置模板
            print("警告: 无解析数据或解析失败，无法生成配置模板。")
            return None

        raw_configs_template = []  # 用于存储每个问题的用户配置模板

        # 使用原始解析数据 questions_data 作为基础，并从 UI 控件中填充用户配置
        # 这样做可以确保模板结构完整，包含parser提供的所有信息，同时叠加用户配置
        questions_data_from_parser = self.parsed_data
        if not isinstance(questions_data_from_parser, list):
             print("错误: 内部解析数据格式错误，应为列表。")
             return None # 异常情况处理

        for q_data_parsed in questions_data_from_parser:
            q_id = q_data_parsed.get('id');
            q_topic_num = q_data_parsed.get('topic_num');
            q_type = q_data_parsed.get('type_code')

             # 再次检查基本数据完整性
            if not q_id or not q_topic_num or not q_type:
                 print(f"警告: 跳过一个结构不完整的问题数据 (来自parser): {q_data_parsed}")
                 continue

            # 获取此问题对应的 UI 控件数据映射
            ui_control_data = self.question_widgets_map.get(q_id)
            # 如果 UI 中没有此题的映射，说明解析时可能未处理或 UI 生成有问题，跳过此题
            if not ui_control_data:
                 print(f"警告: 问题 {q_topic_num} ({q_id}) 在 UI 控件映射中不存在，跳过配置获取。")
                 # 即使 UI 映射不存在，我们仍然可以将原始解析数据添加到模板中，
                 # 让 Worker 决定如何处理（例如，如果题型无需配置，直接使用原始数据）。
                 # 但为了简化，这里假设如果 UI 没有生成，说明该题在配置阶段被忽略或不支持，不添加到模板。
                 # 如果希望包含所有题，无论是否支持配置，可以去掉这个 if not ui_control_data 检查，
                 # 并在后续逻辑中对 None 的 ui_control_data 进行判断。
                 # 这里选择过滤掉没有 UI 映射的题目。
                 continue


            # 构建模板项，从原始解析数据开始复制
            template_item = q_data_parsed.copy()

            # 针对选项类题目，处理“其他”文本和“必选”配置
            # 注意：这里直接修改了 template_item 中的 options 列表
            options_parsed_with_config = []
            # 遍历原始解析到的选项数据
            for opt_data_from_parser in q_data_parsed.get('options', []):
                new_opt_data_for_template = opt_data_from_parser.copy() # 复制选项数据

                # 查找此选项对应的UI控件组（包括“其他”文本和“必选”）
                for ctrl_group in ui_control_data.get("options_controls", []):
                    # 检查是否是“其他”文本配置组，并且关联的选项索引匹配
                    if ctrl_group.get("type") == "other_config_group" and \
                       ctrl_group.get("option_original_index") == opt_data_from_parser.get("original_index"):
                        checkbox_widget = ctrl_group.get("checkbox_widget")
                        text_input_widget = ctrl_group.get("text_input_widget")
                        if checkbox_widget:
                            new_opt_data_for_template["enable_other_text_input"] = checkbox_widget.isChecked()
                        if text_input_widget:
                            new_opt_data_for_template["raw_other_text_input"] = text_input_widget.text().strip()
                        # 找到后继续查找是否有其他类型的配置组（如必选）
                        # break # 不能在这里 break，因为可能还有其他配置组（如必选）属于同一个选项

                    # 检查是否是“必选”配置组，并且关联的选项数据匹配 (通过original_index)
                    # 注意：这里存储控件时，为了方便关联必选，存了 option_data，所以要用 option_data 的 original_index 来匹配
                    if ctrl_group.get("type") == "must_select_config" and \
                       ctrl_group.get("option_data", {}).get("original_index") == opt_data_from_parser.get("original_index"):
                        checkbox_widget = ctrl_group.get("checkbox_widget")
                        if checkbox_widget:
                            new_opt_data_for_template["must_select"] = checkbox_widget.isChecked()
                        # 找到后继续查找是否有其他类型的配置组（如其他文本）
                        # break # 不能在这里 break

                options_parsed_with_config.append(new_opt_data_for_template) # 添加处理后的选项数据到列表

            # 更新模板项中的选项数据为带有配置的列表
            template_item["options_parsed"] = options_parsed_with_config


            # 根据题型，从相应的UI控件获取用户输入并存储到模板
            # 这些是问题级别的输入，如填空文本、权重、概率、滑块值等
            if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                widget = ui_control_data.get("raw_text_input_widget")
                text_content = widget.text().strip() if widget else ""

                # 解析填空题输入字符串，判断是随机还是顺序填写
                if text_content.startswith(self.FILL_IN_BLANK_MARKER_SEQ_START) and \
                   text_content.endswith(self.FILL_IN_BLANK_MARKER_SEQ_END):
                    # 顺序填写格式：提取被[]包裹的内容
                    possible_answers = re.findall(r'\[(.*?)\]', text_content)
                    template_item["fill_format"] = "sequential"
                    template_item["text_answers_list"] = [ans.strip() for ans in possible_answers if ans.strip()]
                    if not template_item["text_answers_list"]:
                         print(f"警告: 题目 {q_topic_num} ({q_id}) 配置为顺序填写，但未解析到有效答案。将使用空字符串。")
                         template_item["text_answers_list"] = [""]

                else:
                    # 默认随机填写格式 (按 || 分割)
                    possible_answers = [ans.strip() for ans in text_content.split(self.FILL_IN_BLANK_SEPARATOR_RANDOM) if
                                        ans.strip()]
                    template_item["fill_format"] = "random"
                    template_item["text_answers_list"] = possible_answers if possible_answers else [""]

                # 无论哪种格式，都保存原始输入字符串，方便导出/导入
                template_item["raw_text_input"] = text_content

            elif q_type == "8":  # 滑块题
                template_item["raw_slider_input"] = ui_control_data.get(
                    "raw_slider_input_widget").text() if ui_control_data.get("raw_slider_input_widget") else "75" # 默认值 75
            elif q_type in ["3", "5", "7"]:  # 单选 / 量表 / 下拉 (权重)
                widget = ui_control_data.get("raw_weight_input_widget")
                num_opts = len(template_item["options_parsed"]) # 使用带配置的选项列表长度
                default_val = ",".join(["1"] * num_opts) if num_opts > 0 else ""
                template_item["raw_weight_input"] = widget.text() if widget else default_val
            elif q_type == "4":  # 多选 (概率)
                widget = ui_control_data.get("raw_prob_input_widget")
                num_opts = len(template_item["options_parsed"]) # 使用带配置的选项列表长度
                default_val = ",".join(["50"] * num_opts) if num_opts > 0 else ""
                template_item["raw_prob_input"] = widget.text() if widget else default_val
            elif q_type == "6":  # 矩阵题 (子问题权重)
                template_item["sub_questions_raw_configs"] = []
                sub_q_controls = ui_control_data.get("sub_questions_controls", [])
                # 注意：这里需要确保子问题数量和顺序与原始解析数据中的 sub_questions 匹配
                # 遍历原始解析数据中的子问题，并查找其对应的UI控件获取配置
                sub_questions_parsed_data = q_data_parsed.get("sub_questions", [])
                for sub_q_idx_parser, sub_q_parsed_data_from_parser in enumerate(sub_questions_parsed_data):
                     # 查找 parser 子问题对应的 UI 控件数据
                    corresponding_ui_control = next(
                        (ctrl for ctrl in sub_q_controls if ctrl["sub_q_data"] == sub_q_parsed_data_from_parser),
                        None
                    )
                    if not corresponding_ui_control:
                        print(f"警告: 题目 {q_topic_num} 子问题 {sub_q_idx_parser + 1} 在 UI 控件中未找到，跳过其配置获取。")
                        # 可以选择在这里为这个子问题添加一个默认配置项，或者跳过。
                        # 这里选择跳过，如果 UI 没有生成，认为此子问题不需配置。
                        continue

                    widget = corresponding_ui_control.get("raw_weight_input_widget")
                    sub_q_options_parsed = sub_q_parsed_data_from_parser.get("options", [])
                    num_sub_opts = len(sub_q_options_parsed)
                    default_sub_val = ",".join(["1"] * num_sub_opts) if num_sub_opts > 0 else ""
                    raw_input_text = widget.text() if widget else default_sub_val

                    # 构建子问题配置项，包含原始解析数据和用户输入
                    sub_q_config_item = {
                        # 存储 parser 提供的原始子问题数据
                        "sub_q_parsed_data": sub_q_parsed_data_from_parser,
                         # 存储用户输入的原始权重字符串
                        "raw_weight_input": raw_input_text
                    }
                    template_item["sub_questions_raw_configs"].append(sub_q_config_item)

            elif q_type == "11":  # 排序题
                # 排序题无需额外用户配置输入控件，模板项中已包含 parser 提供的选项数据
                template_item["is_sortable"] = True # 标记为可排序题型


            # 将构建好的模板项添加到总列表
            raw_configs_template.append(template_item)

        # 返回完整的用户配置模板列表
        # 即使某些题型不支持配置，只要parser解析到了，并且在UI中生成了基础 GroupBox，
        # 它们也会被包含在 question_widgets_map 中，从而包含在 raw_configs_template 中。
        # 最终 Worker 会根据题型和配置决定如何处理。
        return raw_configs_template

    def handle_save_weights(self):
        """
        将当前UI中的配置保存到JSON文件。
        """
        if not self.question_widgets_map:
            QMessageBox.information(self, "提示", "没有已加载的问卷或题目配置可供保存。")
            return

        configurations_to_save = {}  # 存储要保存的配置数据

        # 遍历 question_widgets_map 来获取每个问题的 UI 控件信息
        for q_id, ui_control_data in self.question_widgets_map.items():
            q_type = ui_control_data["q_data"]["type_code"] # 从存储的原始数据中获取题型
            current_q_config = {}  # 当前问题的配置

            # 根据题型获取问题级别的输入控件的值并存储
            if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                widget = ui_control_data.get("raw_text_input_widget")
                if widget:
                    current_q_config["raw_text_input"] = widget.text()  # 保存原始输入字符串
            elif q_type in ["3", "5", "7"]:  # 单选 / 量表 / 下拉
                widget = ui_control_data.get("raw_weight_input_widget")
                if widget:
                    current_q_config["raw_weight_input"] = widget.text()
            elif q_type == "4":  # 多选
                widget = ui_control_data.get("raw_prob_input_widget")
                if widget:
                    current_q_config["raw_prob_input"] = widget.text()
            elif q_type == "8":  # 滑块题
                widget = ui_control_data.get("raw_slider_input_widget")
                if widget:
                    current_q_config["raw_slider_input"] = widget.text()
            elif q_type == "6":  # 矩阵题
                sub_q_weights_list = [] # 存储每个子问题的权重字符串列表
                sub_q_controls = ui_control_data.get("sub_questions_controls", [])
                # 遍历子问题控件列表，获取权重输入值
                for sub_q_ctrl in sub_q_controls:
                    widget = sub_q_ctrl.get("raw_weight_input_widget")
                    # 注意：即使子问题没有选项，这里也应该保存其权重字符串，或者判断是否需要保存
                    # 考虑到导入时需要按顺序匹配，即使没有选项的子问题，也可以保存一个空字符串占位
                    sub_q_weights_list.append(widget.text() if widget else "")
                if sub_q_weights_list:
                     current_q_config["sub_questions_weights"] = sub_q_weights_list

            # 保存选项级别的配置，如“其他”文本和“必选”状态
            option_specific_configs = {} # 字典，键是选项的原始索引，值是该选项的配置字典
            for opt_ctrl_group in ui_control_data.get("options_controls", []):
                opt_type = opt_ctrl_group.get("type") # 获取控件组类型
                # 获取关联的选项原始索引，用于作为保存配置的键
                # 对于 "must_select_config" 类型，原始索引存储在 option_data 里
                # 对于 "other_config_group" 类型，原始索引直接存储
                opt_original_idx = None
                if opt_type == "must_select_config":
                     opt_original_idx = opt_ctrl_group.get("option_data", {}).get("original_index")
                elif opt_type == "other_config_group":
                     opt_original_idx = opt_ctrl_group.get("option_original_index")

                if opt_original_idx is not None:
                    key = str(opt_original_idx) # 使用字符串键以便JSON序列化
                    if key not in option_specific_configs:
                         option_specific_configs[key] = {} # 如果是第一次遇到此选项，初始化其配置字典

                    # 如果是“必选”配置组
                    if opt_type == "must_select_config":
                        checkbox_widget = opt_ctrl_group.get("checkbox_widget")
                        if checkbox_widget:
                            option_specific_configs[key]["must_select"] = checkbox_widget.isChecked()

                    # 如果是“其他”文本配置组
                    elif opt_type == "other_config_group":
                        checkbox_widget = opt_ctrl_group.get("checkbox_widget")
                        text_input_widget = opt_ctrl_group.get("text_input_widget")
                        if checkbox_widget is not None and text_input_widget is not None:
                             option_specific_configs[key]["other_text_config"] = {
                                "enable_text": checkbox_widget.isChecked(),
                                "text_value": text_input_widget.text()
                             }

            # 如果有选项级别的配置，添加到问题配置中
            if option_specific_configs:
                current_q_config["option_settings"] = option_specific_configs


            # 如果当前问题有任何配置项需要保存，添加到总配置字典
            if current_q_config:
                configurations_to_save[q_id] = current_q_config

        if not configurations_to_save:
            QMessageBox.information(self, "提示", "未能收集到任何有效的题目配置。")
            return

        # 打开文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存问卷配置到JSON文件", self._last_io_directory,
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:  # 如果用户选择了文件路径
            # 确保文件扩展名正确
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
            self._last_io_directory = os.path.dirname(file_path)  # 更新上次保存目录
            try:
                # 写入JSON文件，使用UTF-8编码并格式化（缩进4个空格）
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(configurations_to_save, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "成功", f"问卷配置已成功保存到:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存错误", f"保存配置文件失败: {e}")

    def handle_import_weights(self):
        """
        从JSON文件导入配置并应用到UI。
        """
        if not self.question_widgets_map:
            QMessageBox.information(self, "提示", "请先加载问卷，然后再导入配置。")
            return

        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(
            self, "从JSON文件导入问卷配置", self._last_io_directory,
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:  # 如果用户选择了文件路径
            self._last_io_directory = os.path.dirname(file_path)  # 更新上次打开目录
            try:
                # 读取并解析JSON文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    loaded_configs = json.load(f)
            except json.JSONDecodeError:
                QMessageBox.critical(self, "导入错误", "文件不是有效的JSON格式。")
                return
            except FileNotFoundError:
                QMessageBox.critical(self, "导入错误", "选择的文件未找到。")
                return
            except Exception as e:
                QMessageBox.critical(self, "导入错误", f"读取配置文件失败: {e}")
                return

            if not isinstance(loaded_configs, dict):
                QMessageBox.critical(self, "导入错误", "JSON文件内容不是预期的字典格式 (顶层应为对象)。")
                return

            applied_count = 0  # 成功应用的题目计数
            skipped_ids = []  # 跳过的题目ID列表

            # 遍历加载的配置，尝试应用到UI控件
            for q_id, saved_q_config in loaded_configs.items():
                if q_id in self.question_widgets_map:  # 检查该题目ID是否存在于当前加载的问卷中
                    q_controls = self.question_widgets_map[q_id]
                    q_type = q_controls["q_data"]["type_code"] # 从存储的原始数据中获取题型

                    # 根据题型找到对应的问题级别UI控件并设置值
                    if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                        widget = q_controls.get("raw_text_input_widget")
                        if widget and "raw_text_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_text_input"])
                            applied_count += 1 # 算作一个成功应用的配置项
                    elif q_type in ["3", "5", "7"]:  # 单选 / 量表 / 下拉
                        widget = q_controls.get("raw_weight_input_widget")
                        if widget and "raw_weight_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_weight_input"])
                            applied_count += 1
                    elif q_type == "4":  # 多选
                        widget = q_controls.get("raw_prob_input_widget")
                        if widget and "raw_prob_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_prob_input"])
                            applied_count += 1
                    elif q_type == "8":  # 滑块题
                        widget = q_controls.get("raw_slider_input_widget")
                        if widget and "raw_slider_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_slider_input"])
                            applied_count += 1
                    elif q_type == "6":  # 矩阵题
                        saved_sub_weights = saved_q_config.get("sub_questions_weights", [])
                        ui_sub_q_ctrls = q_controls.get("sub_questions_controls", [])
                         # 注意：这里假设保存的子问题权重列表顺序与UI控件顺序一致
                        for i, sub_weight_str in enumerate(saved_sub_weights):
                            if i < len(ui_sub_q_ctrls):
                                widget = ui_sub_q_ctrls[i].get("raw_weight_input_widget")
                                if widget:
                                    widget.setText(sub_weight_str)
                                    applied_count += 1 # 每个子问题权重算一个应用项

                    # 应用选项级别的配置，如“其他”文本和“必选”状态
                    saved_option_settings_map = saved_q_config.get("option_settings", {})
                    if isinstance(saved_option_settings_map, dict):
                        # 遍历 UI 中此题目的所有选项控件组
                        for opt_ctrl_group in q_controls.get("options_controls", []):
                            opt_type = opt_ctrl_group.get("type")
                            opt_original_idx = None
                            if opt_type == "must_select_config":
                                opt_original_idx = opt_ctrl_group.get("option_data", {}).get("original_index")
                            elif opt_type == "other_config_group":
                                opt_original_idx = opt_ctrl_group.get("option_original_index")

                            if opt_original_idx is not None:
                                key = str(opt_original_idx)
                                # 如果加载的配置中包含了此选项的设置
                                if key in saved_option_settings_map:
                                     config_for_this_option = saved_option_settings_map[key]

                                     # 应用“必选”状态 (仅适用于多选题 Type 4)
                                     if opt_type == "must_select_config" and q_type == "4":
                                         checkbox_widget = opt_ctrl_group.get("checkbox_widget")
                                         if checkbox_widget and "must_select" in config_for_this_option:
                                             checkbox_widget.setChecked(config_for_this_option["must_select"])
                                             applied_count += 1

                                     # 应用“其他”文本配置 (适用于 Type 3, 4, 5, 7)
                                     elif opt_type == "other_config_group" and q_type in ["3", "4", "5", "7"]:
                                          checkbox_widget = opt_ctrl_group.get("checkbox_widget")
                                          text_input_widget = opt_ctrl_group.get("text_input_widget")
                                          saved_other_text_config = config_for_this_option.get("other_text_config", {})
                                          if checkbox_widget and text_input_widget and isinstance(saved_other_text_config, dict):
                                               enable_text = saved_other_text_config.get("enable_text", False)
                                               text_val = saved_other_text_config.get("text_value", "")
                                               checkbox_widget.setChecked(enable_text)
                                               text_input_widget.setText(text_val)
                                               applied_count += 1


                else:
                    # 如果没有找到此题目ID在当前加载的问卷中，记录并跳过
                    skipped_ids.append(q_id)

            # 导入完成提示
            msg = f"成功应用了 {applied_count} 个配置项。"
            if skipped_ids:
                msg += f"\n以下题目ID在当前问卷中未找到，其配置已跳过: {', '.join(skipped_ids)}"
            QMessageBox.information(self, "导入完成", msg)

    def _handle_ai_prompt(self):
        """处理用户发送给AI的请求"""
        user_prompt = self.ai_prompt_input.text().strip()
        if not user_prompt:
            return

        if not self.parsed_data or "error" in self.parsed_data:
            QMessageBox.warning(self, "AI 助手", "请先成功加载问卷，再使用AI助手进行配置。")
            return

        if self.ai_thread and self.ai_thread.isRunning():
            QMessageBox.information(self, "AI 助手", "AI正在处理上一个请求，请稍候。")
            return

        # 从主窗口的设置中获取AI配置
        if not self.main_window_ref or not hasattr(self.main_window_ref, 'settings'):
            QMessageBox.critical(self, "错误", "无法访问程序设置。")
            return
        
        settings = self.main_window_ref.settings
        provider = settings.value("ai_service_provider", "Gemini")
        model_name = None
        base_url = None
        if provider.lower() == 'gemini':
            model_name = settings.value("gemini_model", "gemini-2.5-pro")
        elif provider.lower() == 'openai':
            base_url = settings.value("openai_base_url", "")

        api_key_encrypted = settings.value(f"{provider.lower()}_api_key_encrypted", "")

        if not api_key_encrypted:
            QMessageBox.warning(self, "AI 助手", f"尚未配置 {provider} 的 API Key。\n请前往“程序设置”页面进行配置。")
            return

        api_key = decrypt_data(api_key_encrypted)
        
        # Get AI-specific proxy settings
        proxy = settings.value("ai_proxy_address", "")
        if not proxy.startswith("http://") and not proxy.startswith("https://") and proxy:
            proxy = f"http://{proxy}" # Assume http if no scheme is provided

        # 更新UI
        self.ai_prompt_input.clear()
        self.ai_chat_history.append(f"<b>你:</b> {user_prompt}")
        self.ai_chat_history.append("<i>API调用中...</i>")
        self.ai_send_button.setEnabled(False)
        self.ai_prompt_input.setEnabled(False)

        # 启动AI线程
        self.ai_thread = AIConfigThread(provider, api_key, user_prompt, self.parsed_data, self.ai_chat_log, model_name, proxy if proxy else None, base_url if base_url else None)
        self.ai_thread.finished_signal.connect(self._on_ai_finished)
        self.ai_thread.start()

    def _on_ai_finished(self, result):
        """处理AI线程返回的结果"""
        # 移除“思考中”的提示
        cursor = self.ai_chat_history.textCursor()
        cursor.movePosition(cursor.End)
        cursor.select(cursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.deletePreviousChar() # 删除多余的换行符
        self.ai_chat_history.setTextCursor(cursor)

        if result.get("success"):
            user_question = self.ai_prompt_input.text().strip()
            self.ai_chat_log.append({"role": "user", "content": user_question})

            if "config" in result:
                ai_response_config = result.get("config", [])
                self.ai_chat_log.append({"role": "assistant", "content": f"Successfully generated configuration for {len(ai_response_config)} questions."})
                self.ai_chat_history.append("<b>AI:</b> 我已生成配置，正在应用...")
                self._apply_ai_config(ai_response_config)
            elif "question" in result:
                ai_question = result.get("question")
                self.ai_chat_log.append({"role": "assistant", "content": ai_question})
                self.ai_chat_history.append(f"<b>AI:</b> {ai_question}")
            else:
                # Handle unexpected success format
                error_msg = "AI返回了未知格式的成功响应。"
                self.ai_chat_history.append(f"<font color='red'><b>程序错误:</b> {error_msg}</font>")
        else:
            error_msg = result.get("error", "未知错误")
            self.ai_chat_history.append(f"<font color='red'><b>AI 错误:</b> {error_msg}</font>")
            QMessageBox.critical(self, "AI 错误", f"与AI服务交互时发生错误:\n{error_msg}")

        self.ai_send_button.setEnabled(True)
        self.ai_prompt_input.setEnabled(True)
        self.ai_thread = None

    def _apply_ai_config(self, config_list):
        """将AI返回的配置应用到UI控件上"""
        if not isinstance(config_list, list):
            print(f"AI配置应用警告: 返回的配置不是一个列表: {config_list}")
            return

        self.ai_chat_history.append("<font color='red'><b>AI 正在应用配置到问卷...</b></font>")
        QApplication.processEvents() # Force UI update

        applied_count = 0
        for item in config_list:
            q_id = item.get("id")
            if not q_id or q_id not in self.question_widgets_map:
                continue

            q_controls = self.question_widgets_map[q_id]
            
            # 应用权重或概率
            if "raw_weight_input" in item and q_controls.get("raw_weight_input_widget"):
                q_controls["raw_weight_input_widget"].setText(str(item["raw_weight_input"]))
                applied_count += 1
            elif "raw_prob_input" in item and q_controls.get("raw_prob_input_widget"):
                q_controls["raw_prob_input_widget"].setText(str(item["raw_prob_input"]))
                applied_count += 1
            # 应用填空题文本
            elif "raw_text_input" in item and q_controls.get("raw_text_input_widget"):
                q_controls["raw_text_input_widget"].setText(str(item["raw_text_input"]))
                applied_count += 1
            # 应用滑块题
            elif "raw_slider_input" in item and q_controls.get("raw_slider_input_widget"):
                q_controls["raw_slider_input_widget"].setText(str(item["raw_slider_input"]))
                applied_count += 1
        
        self.status_label.setText(f"AI 助手成功应用了 {applied_count} 项配置。")
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage(f"AI 配置已应用。", 3000)
        
        # Update UI feedback
        cursor = self.ai_chat_history.textCursor()
        cursor.movePosition(cursor.End)
        cursor.select(cursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.deletePreviousChar()
        self.ai_chat_history.setTextCursor(cursor)
        self.ai_chat_history.append("<font color='green'><b>配置应用完成！</b></font>")

