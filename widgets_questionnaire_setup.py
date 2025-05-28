# widgets_questionnaire_setup.py
import random
import os
import json
import re  # 导入正则表达式模块
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTextEdit, QScrollArea, QFrame, QGroupBox,
                             QSpacerItem, QSizePolicy, QMessageBox,
                             QFileDialog, QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QIntValidator

# 从本地模块导入问卷解析和工具函数
from questionnaire_parser import fetch_questionnaire_structure
from utils import parse_weights_from_string, calculate_choice_from_weights, calculate_multiple_choices_from_percentages


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

        # 可滚动区域，用于显示问题配置项
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)  # 允许控件根据内容调整大小
        self.scroll_area.setFrameShape(QFrame.StyledPanel)  # 设置边框样式
        self.questions_container_widget = QWidget()
        self.questions_layout = QVBoxLayout(self.questions_container_widget)
        self.questions_layout.setAlignment(Qt.AlignTop)  # 控件靠顶部对齐
        self.scroll_area.setWidget(self.questions_container_widget)
        main_layout.addWidget(self.scroll_area, 1)  # 填满可用空间

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

    def _load_questionnaire(self):
        """
        根据用户输入的URL加载并解析问卷。
        """
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入问卷URL.")
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

        # 从主窗口获取浏览器配置信息，用于解析器线程
        browser_type_to_use = "edge"
        driver_path_to_use = None
        headless_for_parser_val = True
        base_user_data_dir_for_parser = None

        if self.main_window_ref:
            browser_type_to_use = getattr(self.main_window_ref, 'current_browser_type', "edge")
            driver_path_to_use = getattr(self.main_window_ref, 'current_driver_path', None)
            if hasattr(self.main_window_ref, 'settings'):
                headless_for_parser_val = self.main_window_ref.settings.value("headless_mode", True, type=bool)
            # 使用worker共享的基础用户数据目录路径，这样解析器和填报器可以使用相似的环境
            base_user_data_dir_for_parser = getattr(self.main_window_ref, 'base_user_data_dir_for_workers', None)
        else:
            # 兜底处理，理论上不应该发生，因为Main Window会传递自身引用
            print("警告: main_window_ref 未设置或缺少settings属性，使用默认浏览器配置。")

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
            error_message = result['error']
            self.status_label.setText(f"问卷解析失败: {error_message}")
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage(f"问卷解析失败")
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
            self.parsed_data = {"error": "解析结果为空或驱动启动失败或问卷无内容"}
        self.parser_thread = None  # 清空线程引用

    def _clear_question_widgets(self):
        """
        清空当前显示的所有问题配置控件。
        """
        while self.questions_layout.count():
            child = self.questions_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()  # 确保控件被正确销毁
        self.question_widgets_map.clear()  # 清空问题ID与控件的映射

    def _display_questions(self, questions_data):
        """
        根据解析出的问题数据动态生成配置UI。
        :param questions_data: 包含问卷所有问题的列表。
        """
        # 用于统计每种类型题目的序号，方便显示
        type_counters = {str(k): 0 for k in range(1, 12)}
        type_counters.update({"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "11": 0})

        for q_idx, q_data in enumerate(questions_data):
            q_id = q_data['id']
            q_topic = q_data['topic_num']
            q_type = q_data['type_code']
            q_text = q_data['text']
            q_options = q_data.get('options', [])
            q_sub_questions = q_data.get('sub_questions', [])

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
            elif q_type in ["3", "5", "7"]:  # 单选题 / 量表题 / 下拉选择题
                if not q_options:  # 如果没有解析到选项
                    q_group_layout.addWidget(QLabel("警告: 此选择题未解析到任何选项，无法配置。"))
                else:
                    # 权重输入提示
                    q_group_layout.addWidget(QLabel("请为每个选项设置权重 (整数，用英文逗号隔开，例如: 30,70,0):"))
                    options_layout = QVBoxLayout()
                    # 显示每个选项文本，并为“其他”选项添加自定义文本配置
                    for opt_idx, option_data in enumerate(q_options):
                        options_layout.addWidget(QLabel(f"  选项 {opt_idx + 1}: {option_data['text']}"))
                        # 为识别为“其他”选项的单选/量表题添加自定义文本输入控件
                        if option_data.get("is_other_specify") and q_type in ["3", "5"]:
                            other_option_layout = QHBoxLayout()
                            enable_other_text_checkbox = QCheckBox("自定义文本:")
                            enable_other_text_checkbox.setChecked(False)  # 默认不启用自定义文本

                            other_text_qlineedit = QLineEdit()
                            other_text_qlineedit.setPlaceholderText(f"多个用 \"{self.FILL_IN_BLANK_SEPARATOR_RANDOM}\" 分隔，随机选择")
                            other_text_qlineedit.setEnabled(False)  # 默认禁用

                            # 连接复选框状态与文本框的启用状态
                            enable_other_text_checkbox.toggled.connect(other_text_qlineedit.setEnabled)

                            other_option_layout.addWidget(enable_other_text_checkbox)
                            other_option_layout.addWidget(other_text_qlineedit, 1)
                            options_layout.addLayout(other_option_layout)

                            # 存储“其他”选项相关的UI控件
                            self.question_widgets_map[q_id]["options_controls"].append({
                                "type": "other_config_group",
                                "checkbox_widget": enable_other_text_checkbox,
                                "text_input_widget": other_text_qlineedit,
                                "option_original_index": option_data["original_index"]
                            })
                    # 权重输入控件
                    weight_input = QLineEdit()
                    default_weights = ",".join(["1"] * len(q_options))  # 默认等权重
                    weight_input.setPlaceholderText(f"例如: {default_weights}")
                    weight_input.setText(default_weights)
                    self.question_widgets_map[q_id]["raw_weight_input_widget"] = weight_input
                    options_layout.addWidget(weight_input)
                    q_group_layout.addLayout(options_layout)
            elif q_type == "4":  # 多选题
                if not q_options:  # 如果没有解析到选项
                    q_group_layout.addWidget(QLabel("警告: 此多选题未解析到任何选项，无法配置。"))
                else:
                    # 概率输入提示
                    q_group_layout.addWidget(QLabel("请为每个选项设置被选中的概率 (0-100的整数，用英文逗号隔开):"))
                    options_layout = QVBoxLayout()
                    default_probs = ["50"] * len(q_options)  # 默认50%概率
                    # 显示每个选项文本，并为“其他”选项添加自定义文本配置
                    for opt_idx, option_data in enumerate(q_options):
                        options_layout.addWidget(QLabel(f"  选项 {opt_idx + 1}: {option_data['text']}"))
                        # 为识别为“其他”选项的多选题添加自定义文本输入控件
                        if option_data.get("is_other_specify"):
                            other_option_layout = QHBoxLayout()
                            enable_other_text_checkbox = QCheckBox("自定义文本:")
                            enable_other_text_checkbox.setChecked(False)

                            other_text_qlineedit = QLineEdit()
                            other_text_qlineedit.setPlaceholderText(f"多个用 \"{self.FILL_IN_BLANK_SEPARATOR_RANDOM}\" 分隔，随机选择")
                            other_text_qlineedit.setEnabled(False)

                            enable_other_text_checkbox.toggled.connect(other_text_qlineedit.setEnabled)

                            other_option_layout.addWidget(enable_other_text_checkbox)
                            other_option_layout.addWidget(other_text_qlineedit, 1)
                            options_layout.addLayout(other_option_layout)

                            # 存储“其他”选项相关的UI控件
                            self.question_widgets_map[q_id]["options_controls"].append({
                                "type": "other_config_group",
                                "checkbox_widget": enable_other_text_checkbox,
                                "text_input_widget": other_text_qlineedit,
                                "option_original_index": option_data["original_index"]
                            })
                    # 概率输入控件
                    prob_input_line = QLineEdit()
                    prob_input_line.setPlaceholderText(f"例如: {','.join(default_probs)}")
                    prob_input_line.setText(",".join(default_probs))
                    self.question_widgets_map[q_id]["raw_prob_input_widget"] = prob_input_line
                    options_layout.addWidget(prob_input_line)
                    q_group_layout.addLayout(options_layout)
            elif q_type == "6":  # 矩阵题
                if not q_sub_questions or not q_sub_questions[0].get("options"):
                    q_group_layout.addWidget(QLabel("警告: 此矩阵题未解析到足够的子问题或选项结构，无法配置。"))
                else:
                    # 子问题权重输入提示
                    q_group_layout.addWidget(QLabel("请为每个子问题的选项设置权重 (类似单选题，每行一个配置):"))
                    sub_q_controls_list = []  # 存储子问题相关的UI控件
                    for sub_q_idx, sub_q_data in enumerate(q_sub_questions):
                        sub_q_label = QLabel(f"  子问题 {sub_q_idx + 1}: {sub_q_data['text']}")
                        q_group_layout.addWidget(sub_q_label)
                        sub_q_options_list = sub_q_data.get('options', [])
                        if not sub_q_options_list:
                            q_group_layout.addWidget(QLabel(f"    警告: 子问题 {sub_q_idx + 1} 未解析到选项。"))
                            continue
                        # 显示子问题的选项文本
                        options_display_text = "    可选答案: " + " | ".join(
                            [opt['text'] for opt in sub_q_options_list])
                        q_group_layout.addWidget(QLabel(options_display_text))
                        # 子问题权重输入控件
                        sub_q_weight_input = QLineEdit()
                        default_sub_q_weights = ",".join(["1"] * len(sub_q_options_list))
                        sub_q_weight_input.setPlaceholderText(f"例如: {default_sub_q_weights}")
                        sub_q_weight_input.setText(default_sub_q_weights)
                        q_group_layout.addWidget(sub_q_weight_input)
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
                    q_group_layout.addWidget(QLabel(f"  - {opt_data['text']}"))
            else:  # 其他不支持配置的题型
                q_group_layout.addWidget(
                    QLabel(f"此题型 ({self._get_question_type_name(q_type)}) 目前不支持详细配置，将尝试默认处理或跳过。"))

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
        这个模板包含了问题ID、类型、以及用户为每个问题设定的具体填写规则（如文本内容、权重、概率等）。
        对于填空题，会解析其填写格式（随机或顺序）。
        """
        if not self.parsed_data or (
                isinstance(self.parsed_data, dict) and "error" in self.parsed_data) or not isinstance(self.parsed_data,
                                                                                                      list):
            # 如果没有成功的解析数据，则无法生成配置模板
            return None

        raw_configs_template = []  # 用于存储每个问题的用户配置模板

        for q_id, ui_control_data in self.question_widgets_map.items():
            q_data_parsed = ui_control_data["q_data"]  # 获取原始解析数据
            q_type = q_data_parsed['type_code']

            # 构建基本模板项
            template_item = {
                "id": q_data_parsed['id'],
                "topic_num": q_data_parsed['topic_num'],
                "type_code": q_type,
                "sub_questions_parsed": q_data_parsed.get('sub_questions', [])  # 存储子问题原始解析数据
            }

            # 处理选项数据，特别是“其他”选项的自定义文本配置
            parsed_options_with_other_config = []
            original_options_from_parser = q_data_parsed.get('options', [])
            for opt_data_from_parser in original_options_from_parser:
                new_opt_data_for_template = opt_data_from_parser.copy()  # 复制原始选项数据

                # 如果是“其他”选项，查找并存储其自定义文本配置
                if opt_data_from_parser.get("is_other_specify") and q_type in ["3", "4", "5"]:
                    enable_other_text_input_val = False
                    raw_other_text_input_val = ""
                    # 查找该“其他”选项对应的UI控件组
                    for ctrl_group in ui_control_data.get("options_controls", []):
                        if ctrl_group.get("type") == "other_config_group" and \
                                ctrl_group.get("option_original_index") == opt_data_from_parser["original_index"]:
                            checkbox_widget = ctrl_group.get("checkbox_widget")
                            text_input_widget = ctrl_group.get("text_input_widget")
                            if checkbox_widget:
                                enable_other_text_input_val = checkbox_widget.isChecked()  # 获取是否启用自定义文本
                            if text_input_widget:
                                raw_other_text_input_val = text_input_widget.text().strip()  # 获取自定义文本内容
                            break  # 找到对应的控件组后退出内层循环
                    new_opt_data_for_template["enable_other_text_input"] = enable_other_text_input_val
                    new_opt_data_for_template["raw_other_text_input"] = raw_other_text_input_val

                parsed_options_with_other_config.append(new_opt_data_for_template)
            template_item["options_parsed"] = parsed_options_with_other_config  # 存储处理后的选项数据

            # 根据题型，从相应的UI控件获取用户输入并存储到模板
            if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                widget = ui_control_data.get("raw_text_input_widget")
                text_content = widget.text().strip() if widget else ""

                # --- 新增：解析填空题输入字符串，判断是随机还是顺序填写 ---
                if text_content.startswith(self.FILL_IN_BLANK_MARKER_SEQ_START) and \
                   text_content.endswith(self.FILL_IN_BLANK_MARKER_SEQ_END):
                    # 如果以[]开头和结尾，认为是顺序填写格式
                    # 使用正则表达式提取所有被[]包裹的内容
                    possible_answers = re.findall(r'\[(.*?)\]', text_content)
                    template_item["fill_format"] = "sequential"  # 标记为顺序填写
                    # 过滤掉提取出的空字符串，并存储
                    template_item["text_answers_list"] = [ans.strip() for ans in possible_answers if ans.strip()]
                    if not template_item["text_answers_list"]:
                        print(f"警告: 题目 {q_data_parsed['topic_num']} ({q_id}) 配置为顺序填写，但未解析到有效答案。将使用空字符串。")
                        template_item["text_answers_list"] = [""]  # 如果没有解析到有效答案，提供一个空字符串作为备选

                else:
                    # 否则认为是随机填写格式 (按 || 分割)
                    possible_answers = [ans.strip() for ans in text_content.split(self.FILL_IN_BLANK_SEPARATOR_RANDOM) if
                                        ans.strip()]
                    template_item["fill_format"] = "random"  # 标记为随机填写
                    template_item["text_answers_list"] = possible_answers if possible_answers else [""]

                # 无论哪种格式，都保存原始输入字符串，方便导出/导入
                template_item["raw_text_input"] = text_content

            elif q_type == "8":  # 滑块题
                template_item["raw_slider_input"] = ui_control_data.get(
                    "raw_slider_input_widget").text() if ui_control_data.get("raw_slider_input_widget") else "50"
            elif q_type in ["3", "5", "7"]:  # 单选 / 量表 / 下拉
                widget = ui_control_data.get("raw_weight_input_widget")
                num_opts = len(template_item["options_parsed"])
                default_val = ",".join(["1"] * num_opts) if num_opts > 0 else ""
                template_item["raw_weight_input"] = widget.text() if widget else default_val
            elif q_type == "4":  # 多选
                widget = ui_control_data.get("raw_prob_input_widget")
                num_opts = len(template_item["options_parsed"])
                default_val = ",".join(["50"] * num_opts) if num_opts > 0 else ""
                template_item["raw_prob_input"] = widget.text() if widget else default_val
            elif q_type == "6":  # 矩阵题
                template_item["sub_questions_raw_configs"] = []
                sub_q_controls = ui_control_data.get("sub_questions_controls", [])
                for sub_q_idx_loop, sub_control in enumerate(sub_q_controls):
                    sub_q_parsed_data_from_ui = sub_control["sub_q_data"]  # 获取原始解析数据
                    widget = sub_control.get("raw_weight_input_widget")
                    num_sub_opts = len(sub_q_parsed_data_from_ui.get("options", []))
                    default_sub_val = ",".join(["1"] * num_sub_opts) if num_sub_opts > 0 else ""
                    raw_input_text = widget.text() if widget else default_sub_val
                    sub_q_config_item = {  # 构建子问题配置项
                        "sub_q_id_prefix": sub_q_parsed_data_from_ui.get("id_prefix",
                                                                         f"matrix_{q_data_parsed['topic_num']}_sub_{sub_q_idx_loop + 1}"),
                        "sub_q_original_index": sub_q_parsed_data_from_ui.get("original_index"),
                        "sub_q_options_parsed": sub_q_parsed_data_from_ui.get("options", []),
                        "raw_weight_input": raw_input_text
                    }
                    template_item["sub_questions_raw_configs"].append(sub_q_config_item)
            elif q_type == "11":  # 排序题
                template_item["is_sortable"] = True
                # 排序题使用解析到的选项数据进行随机排序，无需额外的用户配置输入控件

            raw_configs_template.append(template_item)  # 将构建好的模板项添加到总列表

        # 检查是否成功收集到配置信息
        if not raw_configs_template and self.parsed_data and isinstance(self.parsed_data, list) and len(
                self.parsed_data) > 0:
            QMessageBox.warning(self, "配置警告", "未能收集到任何用户配置信息，但解析到了题目。请检查UI逻辑。")
            return []  # 如果解析到题目但未收集到配置，返回空列表而不是None
        return raw_configs_template  # 返回完整的用户配置模板列表

    def handle_save_weights(self):
        """
        将当前UI中的配置保存到JSON文件。
        """
        if not self.question_widgets_map:
            QMessageBox.information(self, "提示", "没有已加载的问卷或题目配置可供保存。")
            return

        configurations_to_save = {}  # 存储要保存的配置数据

        for q_id, q_controls in self.question_widgets_map.items():
            q_type = q_controls["q_data"]["type_code"]
            current_q_config = {}  # 当前问题的配置

            # 根据题型获取输入控件的值并存储
            if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                widget = q_controls.get("raw_text_input_widget")
                if widget:
                    current_q_config["raw_text_input"] = widget.text()  # 保存原始输入字符串
            elif q_type in ["3", "5", "7"]:  # 单选 / 量表 / 下拉
                widget = q_controls.get("raw_weight_input_widget")
                if widget:
                    current_q_config["raw_weight_input"] = widget.text()
            elif q_type == "4":  # 多选
                widget = q_controls.get("raw_prob_input_widget")
                if widget:
                    current_q_config["raw_prob_input"] = widget.text()
            elif q_type == "8":  # 滑块题
                widget = q_controls.get("raw_slider_input_widget")
                if widget:
                    current_q_config["raw_slider_input"] = widget.text()
            elif q_type == "6":  # 矩阵题
                sub_q_weights_list = []
                for sub_q_ctrl in q_controls.get("sub_questions_controls", []):
                    widget = sub_q_ctrl.get("raw_weight_input_widget")
                    if widget:
                        sub_q_weights_list.append(widget.text())
                if sub_q_weights_list:
                    current_q_config["sub_questions_weights"] = sub_q_weights_list

            # 保存“其他”选项的自定义文本配置
            if q_type in ["3", "4", "5"]:
                other_options_config_map = {}
                for opt_ctrl_group in q_controls.get("options_controls", []):
                    if opt_ctrl_group.get("type") == "other_config_group":
                        checkbox_widget = opt_ctrl_group.get("checkbox_widget")
                        text_input_widget = opt_ctrl_group.get("text_input_widget")
                        opt_original_idx = opt_ctrl_group.get("option_original_index")

                        if checkbox_widget is not None and text_input_widget is not None and opt_original_idx is not None:
                            other_options_config_map[str(opt_original_idx)] = {
                                "enable_text": checkbox_widget.isChecked(),
                                "text_value": text_input_widget.text()
                            }
                if other_options_config_map:
                    current_q_config["other_options_config"] = other_options_config_map

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
                    q_type = q_controls["q_data"]["type_code"]

                    # 根据题型找到对应的UI控件并设置值
                    if q_type in ["1", "2"]:  # 填空题 / 多行填空题
                        widget = q_controls.get("raw_text_input_widget")
                        if widget and "raw_text_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_text_input"])
                    elif q_type in ["3", "5", "7"]:  # 单选 / 量表 / 下拉
                        widget = q_controls.get("raw_weight_input_widget")
                        if widget and "raw_weight_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_weight_input"])
                    elif q_type == "4":  # 多选
                        widget = q_controls.get("raw_prob_input_widget")
                        if widget and "raw_prob_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_prob_input"])
                    elif q_type == "8":  # 滑块题
                        widget = q_controls.get("raw_slider_input_widget")
                        if widget and "raw_slider_input" in saved_q_config:
                            widget.setText(saved_q_config["raw_slider_input"])
                    elif q_type == "6":  # 矩阵题
                        saved_sub_weights = saved_q_config.get("sub_questions_weights", [])
                        ui_sub_q_ctrls = q_controls.get("sub_questions_controls", [])
                        for i, sub_weight_str in enumerate(saved_sub_weights):
                            if i < len(ui_sub_q_ctrls):
                                widget = ui_sub_q_ctrls[i].get("raw_weight_input_widget")
                                if widget:
                                    widget.setText(sub_weight_str)

                    # 应用“其他”选项的自定义文本配置
                    if q_type in ["3", "4", "5"]:
                        saved_other_options_map = saved_q_config.get("other_options_config", {})
                        if isinstance(saved_other_options_map, dict):
                            for opt_ctrl_group in q_controls.get("options_controls", []):
                                if opt_ctrl_group.get("type") == "other_config_group":
                                    checkbox_widget = opt_ctrl_group.get("checkbox_widget")
                                    text_input_widget = opt_ctrl_group.get("text_input_widget")
                                    opt_original_idx = opt_ctrl_group.get("option_original_index")

                                    if checkbox_widget and text_input_widget and opt_original_idx is not None:
                                        key = str(opt_original_idx)
                                        if key in saved_other_options_map:
                                            config_for_this_other = saved_other_options_map[key]
                                            enable_text = config_for_this_other.get("enable_text", False)
                                            text_val = config_for_this_other.get("text_value", "")

                                            checkbox_widget.setChecked(enable_text)
                                            text_input_widget.setText(text_val)

                    applied_count += 1
                else:
                    skipped_ids.append(q_id)  # 记录未找到的题目ID

            # 导入完成提示
            msg = f"成功应用了 {applied_count} 个题目的配置。"
            if skipped_ids:
                msg += f"\n以下题目ID在当前问卷中未找到，其配置已跳过: {', '.join(skipped_ids)}"
            QMessageBox.information(self, "导入完成", msg)