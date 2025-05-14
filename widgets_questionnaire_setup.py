# widgets_questionnaire_setup.py
import random
import os # 导入os模块
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTextEdit, QScrollArea, QFrame, QGroupBox,
                             QSpinBox, QSpacerItem, QSizePolicy, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QIntValidator

# 导入解析器
from questionnaire_parser import fetch_questionnaire_structure
# 导入工具函数
from utils import parse_weights_from_string, calculate_choice_from_weights, calculate_multiple_choices_from_percentages


# 定义一个 QThread 用于后台解析问卷
class ParserThread(QThread):
    finished_signal = pyqtSignal(object)  # 解析结果 (列表或含error的字典)

    def __init__(self, url, driver_path):
        super().__init__()
        self.url = url
        self.driver_path = driver_path # 这个路径会传递给 fetch_questionnaire_structure

    def run(self):
        # 将 driver_path 传递给解析函数
        result = fetch_questionnaire_structure(self.url, msedgedriver_path_arg=self.driver_path)
        self.finished_signal.emit(result)


class QuestionnaireSetupWidget(QWidget):
    def __init__(self, parent=None):  # parent 通常是 MainWindow
        super().__init__(parent)
        self.main_window_ref = parent # 指向主窗口的引用，方便访问全局设置等
        self.parsed_data = None  # 存储解析后的问卷结构
        self.question_widgets_map = {}  # 存储动态生成的题目控件，key是题目ID，value是相关控件字典
        self._init_ui() # 初始化用户界面

    def _init_ui(self):
        # 主布局为垂直布局
        main_layout = QVBoxLayout(self)

        # --- URL输入和加载区域 ---
        url_group = QGroupBox("问卷链接") # 使用GroupBox美化
        url_layout = QHBoxLayout() # 水平布局放置URL输入框和加载按钮
        url_layout.addWidget(QLabel("问卷URL:")) # 标签
        self.url_input = QLineEdit() # URL输入框
        self.url_input.setPlaceholderText("请输入完整的问卷星链接 (例如: https://www.wjx.cn/vm/xxxx.aspx)")
        # self.url_input.setText("https://www.wjx.cn/vm/Y7Eps4P.aspx#") # 测试用URL，方便调试
        url_layout.addWidget(self.url_input, 1)  # 输入框占据更多空间
        self.load_button = QPushButton("加载问卷") # 加载按钮
        self.load_button.clicked.connect(self._load_questionnaire) # 连接点击事件到加载函数
        url_layout.addWidget(self.load_button)
        url_group.setLayout(url_layout) # 设置GroupBox的布局
        main_layout.addWidget(url_group) # 将GroupBox添加到主布局

        # --- 问卷题目配置区域 (可滚动) ---
        self.scroll_area = QScrollArea(self) # 创建滚动区域
        self.scroll_area.setWidgetResizable(True)  # 允许滚动区域内的控件自动调整大小
        self.scroll_area.setFrameShape(QFrame.StyledPanel)  # 设置边框样式

        self.questions_container_widget = QWidget()  # 作为滚动区域的内容承载控件
        self.questions_layout = QVBoxLayout(self.questions_container_widget)  # 题目将在此垂直排列
        self.questions_layout.setAlignment(Qt.AlignTop)  # 题目从顶部开始排列，避免垂直居中

        self.scroll_area.setWidget(self.questions_container_widget) # 将内容控件放入滚动区域
        main_layout.addWidget(self.scroll_area, 1)  # 滚动区域占据剩余大部分垂直空间

        # --- 状态/日志显示标签 ---
        self.status_label = QLabel("请先输入问卷URL并点击“加载问卷”。") # 初始提示信息
        self.status_label.setAlignment(Qt.AlignCenter) # 文本居中
        main_layout.addWidget(self.status_label) # 添加到主布局

        self.parser_thread = None # 初始化解析线程变量

    def _load_questionnaire(self):
        # 获取用户输入的URL并去除首尾空格
        url = self.url_input.text().strip()
        if not url: # 如果URL为空
            QMessageBox.warning(self, "提示", "请输入问卷URL。")
            return

        # 如果解析线程已在运行，则提示用户等待
        if self.parser_thread and self.parser_thread.isRunning():
            QMessageBox.information(self, "提示", "正在解析中，请稍候...")
            return

        # 禁用加载按钮，更新状态标签和主窗口状态栏
        self.load_button.setEnabled(False)
        self.status_label.setText(f"正在加载和解析问卷: {url} ... 请耐心等待。")
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage("问卷解析中...")

        # 清空之前动态生成的题目控件和已解析数据
        self._clear_question_widgets()
        self.parsed_data = None
        self.question_widgets_map = {}

        # 从主窗口的QSettings实例获取EdgeDriver的路径
        driver_path = None
        if self.main_window_ref and hasattr(self.main_window_ref, 'settings'):
            driver_path = self.main_window_ref.settings.value("msedgedriver_path", None)
            if driver_path == "": # 如果设置的是空字符串，也视为None
                driver_path = None
            # print(f"QuestionnaireSetupWidget: 获取到的驱动路径为: {driver_path}") # 调试信息
        # else:
            # print("QuestionnaireSetupWidget: 无法从主窗口获取 QSettings 来读取驱动路径。") # 调试信息

        # 创建并启动解析线程
        self.parser_thread = ParserThread(url, driver_path)
        self.parser_thread.finished_signal.connect(self._on_parsing_finished) # 连接线程完成信号到处理函数
        self.parser_thread.start() # 启动线程

    def _on_parsing_finished(self, result):
        # 解析完成后，恢复加载按钮的可用状态
        self.load_button.setEnabled(True)
        status_bar_available = self.main_window_ref and hasattr(self.main_window_ref, 'statusBar')

        if isinstance(result, dict) and "error" in result: # 如果返回的是包含错误的字典
            error_message = result['error']
            self.status_label.setText(f"问卷解析失败: {error_message}")
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage(f"问卷解析失败")
            QMessageBox.critical(self, "解析错误", f"解析问卷时发生错误：\n{error_message}")
            self.parsed_data = result # 保存错误信息
        elif result and isinstance(result, list): # 如果返回的是非空列表（成功解析）
            self.parsed_data = result
            self.status_label.setText(f"成功解析到 {len(result)} 个问题。请在下方配置各项答案权重。")
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage(f"问卷解析成功，共 {len(result)} 个问题。")
            self._display_questions(result) # 显示问题配置界面
        else: # 其他情况（如返回None或空列表）
            default_error_msg = "未能从问卷中解析出任何问题结构，或驱动启动失败。"
            self.status_label.setText(default_error_msg)
            if status_bar_available:
                self.main_window_ref.statusBar().showMessage("问卷解析结果为空或失败。")
            QMessageBox.warning(self, "解析结果", default_error_msg)
            self.parsed_data = {"error": "解析结果为空或驱动启动失败"} # 记录错误状态

        self.parser_thread = None # 清理线程对象，以便下次使用

    def _clear_question_widgets(self):
        """清除动态生成的题目配置控件，释放资源"""
        while self.questions_layout.count(): # 遍历布局中的所有项目
            child = self.questions_layout.takeAt(0) # 取出并移除项目
            if child.widget(): # 如果项目是一个控件
                child.widget().deleteLater() # 安全地删除控件
        self.question_widgets_map.clear() # 清空存储控件引用的字典

    def _display_questions(self, questions_data):
        """根据解析到的问卷数据，动态创建题目配置UI"""
        self._clear_question_widgets() # 先清空旧的UI

        # 用于为同类型题目编号，例如 "单选题 - 第1个此类题"
        type_counters = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "11": 0}

        for q_idx, q_data in enumerate(questions_data): # 遍历每个解析到的问题数据
            q_id = q_data['id'] # 问题div的ID
            q_topic = q_data['topic_num'] # 问卷中的原始题号
            q_type = q_data['type_code'] # 问题类型代码
            q_text = q_data['text'] # 问题文本
            q_options = q_data.get('options', []) # 问题的选项列表
            q_sub_questions = q_data.get('sub_questions', []) # 矩阵题的子问题列表

            type_counters[q_type] = type_counters.get(q_type, 0) + 1 # 更新该类型题目的计数器
            # 构建GroupBox的标题
            q_groupbox_title = (
                f"题目 {q_data.get('question_index_overall', q_idx + 1)} "
                f"(原始题号: {q_topic}, 类型: {self._get_question_type_name(q_type)} - 第{type_counters[q_type]}个此类题)"
            )
            q_groupbox = QGroupBox(q_groupbox_title) # 为每个问题创建一个GroupBox
            q_group_layout = QVBoxLayout() # GroupBox内部使用垂直布局
            q_text_label = QLabel(q_text) # 显示问题文本的标签
            q_text_label.setWordWrap(True) # 允许文本换行
            q_text_label.setObjectName("QuestionTextLabel") # 设置对象名，用于QSS样式
            q_group_layout.addWidget(q_text_label)

            # 初始化存储该问题UI控件的字典
            self.question_widgets_map[q_id] = {
                "type": q_type, # 问题类型
                "q_data": q_data,  # 保存原始解析数据，方便后续使用
                "options_controls": [], # 用于存储选项相关的控件（如果需要单独控制）
                "sub_questions_controls": [] # 用于存储矩阵题子问题相关的控件
            }

            # 根据问题类型创建不同的配置控件
            if q_type in ["1", "2"]: # 填空题、多行填空题
                text_input_label = QLabel("请输入填空内容:")
                text_input = QLineEdit()
                text_input.setPlaceholderText("填写的答案内容")
                # 将输入控件存入map，键名清晰表示是原始文本输入
                self.question_widgets_map[q_id]["raw_text_input_widget"] = text_input
                q_group_layout.addWidget(text_input_label)
                q_group_layout.addWidget(text_input)

            elif q_type in ["3", "5", "7"]: # 单选题、量表题、下拉选择题
                if not q_options: # 如果没有解析到选项
                    q_group_layout.addWidget(QLabel("警告: 此选择题未解析到任何选项，无法配置。"))
                else:
                    q_group_layout.addWidget(QLabel("请为每个选项设置权重 (整数，用英文逗号隔开，例如: 30,70,0):"))
                    options_layout = QVBoxLayout() # 垂直布局显示选项文本
                    for opt_idx, option_data in enumerate(q_options):
                        opt_label = QLabel(f"  选项 {opt_idx + 1}: {option_data['text']}")
                        options_layout.addWidget(opt_label)
                    weight_input = QLineEdit() # 权重输入框
                    default_weights = ",".join(["1"] * len(q_options)) # 默认等权重
                    weight_input.setPlaceholderText(f"例如: {default_weights}")
                    weight_input.setText(default_weights) # 设置默认值
                    # 将输入控件存入map
                    self.question_widgets_map[q_id]["raw_weight_input_widget"] = weight_input
                    options_layout.addWidget(weight_input)
                    q_group_layout.addLayout(options_layout)

            elif q_type == "4": # 多选题
                if not q_options:
                    q_group_layout.addWidget(QLabel("警告: 此多选题未解析到任何选项，无法配置。"))
                else:
                    q_group_layout.addWidget(QLabel("请为每个选项设置被选中的概率 (0-100的整数，用英文逗号隔开):"))
                    options_layout = QVBoxLayout()
                    default_probs = [] # 存储默认概率
                    for opt_idx, option_data in enumerate(q_options):
                        opt_label = QLabel(f"  选项 {opt_idx + 1}: {option_data['text']}")
                        options_layout.addWidget(opt_label)
                        default_probs.append("50") # 默认选中概率50%
                    prob_input_line = QLineEdit() # 概率输入框
                    prob_input_line.setPlaceholderText(f"例如: {','.join(['50'] * len(q_options))}")
                    prob_input_line.setText(",".join(default_probs))
                    # 将输入控件存入map
                    self.question_widgets_map[q_id]["raw_prob_input_widget"] = prob_input_line
                    options_layout.addWidget(prob_input_line)
                    q_group_layout.addLayout(options_layout)

            elif q_type == "6": # 矩阵题
                # 检查子问题列表和第一个子问题是否有选项，以此判断矩阵结构是否完整
                if not q_sub_questions or not q_sub_questions[0].get("options"):
                    q_group_layout.addWidget(QLabel("警告: 此矩阵题未解析到足够的子问题或选项结构，无法配置。"))
                else:
                    q_group_layout.addWidget(QLabel("请为每个子问题的选项设置权重 (类似单选题，每行一个配置):"))
                    sub_q_controls_list = []  # 临时列表存储子问题控件及其数据
                    for sub_q_idx, sub_q_data in enumerate(q_sub_questions): # 遍历每个子问题
                        sub_q_label = QLabel(f"  子问题 {sub_q_idx + 1}: {sub_q_data['text']}")
                        q_group_layout.addWidget(sub_q_label)
                        sub_q_options_list = sub_q_data.get('options', []) # 获取子问题的选项
                        if not sub_q_options_list: # 如果子问题没有选项
                            q_group_layout.addWidget(QLabel(f"    警告: 子问题 {sub_q_idx + 1} 未解析到选项。"))
                            continue
                        # 显示子问题的可选答案
                        options_display_text = "    可选答案: " + " | ".join(
                            [f"{opt['text']}" for opt in sub_q_options_list])
                        q_group_layout.addWidget(QLabel(options_display_text))
                        sub_q_weight_input = QLineEdit() # 子问题权重输入框
                        default_sub_q_weights = ",".join(["1"] * len(sub_q_options_list)) # 默认等权重
                        sub_q_weight_input.setPlaceholderText(f"例如: {default_sub_q_weights}")
                        sub_q_weight_input.setText(default_sub_q_weights)
                        q_group_layout.addWidget(sub_q_weight_input)
                        # 存储子问题的原始解析数据和UI输入控件
                        sub_q_controls_list.append({
                            "sub_q_data": sub_q_data,  # 保存子问题的原始解析数据
                            "raw_weight_input_widget": sub_q_weight_input, # 保存输入控件
                        })
                    # 将子问题控件列表存入map
                    self.question_widgets_map[q_id]["sub_questions_controls"] = sub_q_controls_list


            elif q_type == "8": # 滑块题
                q_group_layout.addWidget(
                    QLabel("请输入滑块的值 (通常是1-100的整数，或用英文逗号分隔多个值及权重，如 60,70,80 和 1,2,1):"))
                slider_value_input = QLineEdit()
                slider_value_input.setPlaceholderText("例如: 75  或者  60,80:1,1 (值:权重)")
                slider_value_input.setText("75") # 默认值
                # 将输入控件存入map
                self.question_widgets_map[q_id]["raw_slider_input_widget"] = slider_value_input
                q_group_layout.addWidget(slider_value_input)

            elif q_type == "11": # 排序题
                q_group_layout.addWidget(QLabel("排序题将自动进行随机排序，无需配置。"))
                if q_options: # 如果有可排序项，显示它们
                    q_group_layout.addWidget(QLabel("可排序项:"))
                    for opt_data in q_options:
                        q_group_layout.addWidget(QLabel(f"  - {opt_data['text']}"))
            else: # 其他未知或未支持的题型
                q_group_layout.addWidget(
                    QLabel(f"此题型 ({self._get_question_type_name(q_type)}) 目前不支持详细配置，将尝试默认处理或跳过。"))

            q_groupbox.setLayout(q_group_layout) # 设置GroupBox的布局
            self.questions_layout.addWidget(q_groupbox) # 将GroupBox添加到题目显示区域
        self.questions_layout.addStretch(1) # 添加一个弹性空间到底部，避免控件间距过大

    def _get_question_type_name(self, type_code):
        """根据类型代码返回问题类型的中文名称"""
        names = {
            "1": "填空题", "2": "多行填空题", "3": "单选题", "4": "多选题",
            "5": "量表题", "6": "矩阵题", "7": "下拉选择题", "8": "滑块题",
            "11": "排序题"
        }
        return names.get(type_code, f"未知类型({type_code})")

    def get_parsed_questionnaire_data(self):
        """返回解析后的原始问卷数据"""
        return self.parsed_data

    def get_user_raw_configurations_template(self):
        """
        收集用户在UI上为每个问题设置的原始配置信息（权重字符串、填空文本等），
        但不进行随机选择。返回一个“配置模板”列表，供 FillerWorker 在每次填写前进行随机化。
        """
        if not self.parsed_data or (isinstance(self.parsed_data, dict) and "error" in self.parsed_data):
            # 如果没有解析数据或解析出错，则返回None
            return None

        raw_configs_template = [] # 用于存储配置模板的列表
        # 遍历存储UI控件的map，基于每个问题的原始解析数据和用户输入构建配置模板
        for q_id, ui_control_data in self.question_widgets_map.items():
            q_data_parsed = ui_control_data["q_data"]  # 获取该问题的原始解析数据
            q_type = q_data_parsed['type_code'] # 问题类型

            # 构建配置模板的基础项
            template_item = {
                "id": q_data_parsed['id'], # 问题div的ID
                "topic_num": q_data_parsed['topic_num'], # 原始题号
                "type_code": q_type, # 问题类型代码
                "options_parsed": q_data_parsed.get('options', []),  # 原始选项数据
                "sub_questions_parsed": q_data_parsed.get('sub_questions', [])  # 原始子问题数据（矩阵题）
            }

            # 根据问题类型，从对应的UI控件获取用户输入的原始配置
            if q_type in ["1", "2"]:  # 填空题
                widget = ui_control_data.get("raw_text_input_widget")
                template_item["raw_text_input"] = widget.text() if widget else "" # 获取文本，若无控件则为空
            elif q_type == "8":  # 滑块题
                widget = ui_control_data.get("raw_slider_input_widget")
                template_item["raw_slider_input"] = widget.text() if widget else "50" # 获取文本，若无控件则为默认值 "50"
            elif q_type in ["3", "5", "7"]:  # 单选、量表、下拉
                widget = ui_control_data.get("raw_weight_input_widget")
                num_opts = len(template_item["options_parsed"])
                default_val = ",".join(["1"] * num_opts) if num_opts > 0 else "" # 默认等权重
                template_item["raw_weight_input"] = widget.text() if widget else default_val
            elif q_type == "4":  # 多选题
                widget = ui_control_data.get("raw_prob_input_widget")
                num_opts = len(template_item["options_parsed"])
                default_val = ",".join(["50"] * num_opts) if num_opts > 0 else "" # 默认50%概率
                template_item["raw_prob_input"] = widget.text() if widget else default_val
            elif q_type == "6":  # 矩阵题
                template_item["sub_questions_raw_configs"] = [] # 初始化子问题配置列表
                sub_q_controls = ui_control_data.get("sub_questions_controls", [])
                # *** 修改点：在这里迭代 sub_q_controls 时获取 sub_q_idx ***
                for sub_q_idx_loop, sub_control in enumerate(sub_q_controls): # 使用 enumerate 获取索引
                    sub_q_parsed_data = sub_control["sub_q_data"] # 子问题的原始解析数据
                    widget = sub_control.get("raw_weight_input_widget") # 子问题的权重输入控件
                    num_sub_opts = len(sub_q_parsed_data.get("options", [])) # 子问题的选项数量
                    default_sub_val = ",".join(["1"] * num_sub_opts) if num_sub_opts > 0 else "" # 默认等权重
                    raw_input_text = widget.text() if widget else default_sub_val

                    # 构建子问题的配置项
                    sub_q_config_item = {
                        # 使用循环中的 sub_q_idx_loop 而不是外部的 q_idx 或可能不存在的 sub_q_idx
                        "sub_q_id_prefix": sub_q_parsed_data.get("id_prefix", f"matrix_{q_data_parsed['topic_num']}_sub_{sub_q_idx_loop + 1}"),
                        "sub_q_original_index": sub_q_parsed_data.get("original_index"), # 子问题在其矩阵中的原始行索引
                        "sub_q_options_parsed": sub_q_parsed_data.get("options", []), # 子问题的选项（通常是共享的）
                        "raw_weight_input": raw_input_text # 用户输入的原始权重字符串
                    }
                    template_item["sub_questions_raw_configs"].append(sub_q_config_item)

            elif q_type == "11":  # 排序题
                template_item["is_sortable"] = True # 标记为可排序，Worker会处理

            raw_configs_template.append(template_item) # 将构建好的配置模板项添加到列表

        # 如果没有收集到任何配置，但确实解析到了问题，则发出警告
        if not raw_configs_template and self.parsed_data and isinstance(self.parsed_data, list) and len(self.parsed_data) > 0 :
            QMessageBox.warning(self, "配置警告", "未能收集到任何用户配置信息，但解析到了题目。请检查UI逻辑。")
            return None
        return raw_configs_template

    def get_current_questionnaire_config(self):
        """
        [旧逻辑/备用] 此方法现在主要用于演示或快速获取一个已随机化的配置。
        主流程应使用 get_user_raw_configurations_template() 并由 FillerWorker 内部进行随机化。
        此函数会执行一次随机化选择，生成具体的填写指令。
        """
        template = self.get_user_raw_configurations_template() # 获取原始配置模板
        if not template: # 如果模板为空，则无法生成指令
            return None

        fill_instructions = [] # 用于存储最终的填写指令列表
        # 遍历配置模板，根据用户输入和随机化规则生成具体指令
        for q_template in template:
            q_id = q_template['id']
            q_topic_num = q_template['topic_num']
            q_type = q_template['type_code']
            options_parsed = q_template.get('options_parsed', [])
            instruction_base = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type}

            if q_type in ["1", "2"]: # 填空题
                instruction = instruction_base.copy()
                instruction["action"] = "fill" # 动作：填充
                instruction["text_answer"] = q_template.get("raw_text_input", "") # 答案文本
                fill_instructions.append(instruction)
            elif q_type == "8": # 滑块题
                instruction = instruction_base.copy()
                instruction["action"] = "fill"
                raw_slider_text = q_template.get("raw_slider_input", "50").strip() # 获取原始输入，默认为"50"
                try:
                    if ':' in raw_slider_text and ',' in raw_slider_text.split(':')[0]: # 权重格式 "值1,值2:权重1,权重2"
                        values_str, weights_str = raw_slider_text.split(':')
                        values = [int(v.strip()) for v in values_str.split(',')]
                        weights_list = [int(w.strip()) for w in weights_str.split(',')]
                        if len(values) == len(weights_list) and sum(weights_list) > 0: # 确保值和权重数量匹配且权重和大于0
                            chosen_value_idx = calculate_choice_from_weights(weights_list) # 按权重选择
                            instruction["text_answer"] = str(values[chosen_value_idx])
                        else: # 格式错误或权重和为0，取第一个值或默认值
                            instruction["text_answer"] = str(values[0]) if values else "50"
                    elif ',' in raw_slider_text: # 纯逗号分隔的值列表 "值1,值2,值3"
                        values = [int(v.strip()) for v in raw_slider_text.split(',')]
                        instruction["text_answer"] = str(random.choice(values)) if values else "50" # 随机选择一个值
                    else: # 单个值
                        instruction["text_answer"] = str(int(raw_slider_text))
                except ValueError: instruction["text_answer"] = "50" # 解析失败用默认值
                except Exception: instruction["text_answer"] = "50"  # 其他异常也用默认值
                fill_instructions.append(instruction)

            elif q_type in ["3", "5", "7"]: # 单选、量表、下拉
                instruction = instruction_base.copy()
                raw_weights_str = q_template.get("raw_weight_input", "") # 获取原始权重字符串
                if options_parsed: # 必须有选项才能进行选择
                    num_opts = len(options_parsed)
                    weights = parse_weights_from_string(raw_weights_str, num_opts) # 解析权重字符串为列表
                    chosen_option_idx_in_list = calculate_choice_from_weights(weights) # 按权重选择选项索引
                    if chosen_option_idx_in_list != -1: # 如果成功选择
                        selected_option_data = options_parsed[chosen_option_idx_in_list] # 获取选中的选项数据
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select" # 动作类型
                        instruction["target_original_index"] = selected_option_data["original_index"] # 目标选项的原始HTML索引
                        fill_instructions.append(instruction)
                    elif options_parsed: # 如果权重选择失败但有选项，则随机选一个
                        selected_option_data = random.choice(options_parsed)
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select"
                        instruction["target_original_index"] = selected_option_data["original_index"]
                        fill_instructions.append(instruction)

            elif q_type == "4": # 多选题
                raw_probs_str = q_template.get("raw_prob_input", "") # 获取原始概率字符串
                if options_parsed:
                    try:
                        percentages = [int(p.strip()) for p in raw_probs_str.split(',')] # 解析概率字符串
                        if len(percentages) != len(options_parsed): # 如果概率数量与选项数量不匹配
                             # 简单处理：随机选1到N/2个选项
                            num_to_select = random.randint(1, (len(options_parsed) + 1) // 2 if options_parsed else 1)
                            selected_options_data = random.sample(options_parsed, min(num_to_select, len(options_parsed)))
                            for selected_opt_data in selected_options_data: # 为每个选中的选项创建指令
                                multi_choice_instruction = instruction_base.copy()
                                multi_choice_instruction["action"] = "click"
                                multi_choice_instruction["target_original_index"] = selected_opt_data["original_index"]
                                fill_instructions.append(multi_choice_instruction)
                        else: # 概率数量与选项数量匹配
                            selected_indices_in_list = calculate_multiple_choices_from_percentages(percentages) # 按百分比选择
                            for selected_idx in selected_indices_in_list:
                                multi_choice_instruction = instruction_base.copy()
                                multi_choice_instruction["action"] = "click"
                                multi_choice_instruction["target_original_index"] = options_parsed[selected_idx]["original_index"]
                                fill_instructions.append(multi_choice_instruction)
                    except ValueError: # 解析概率失败，则随机选一个
                        if options_parsed:
                            selected_option_data = random.choice(options_parsed)
                            multi_choice_instruction = instruction_base.copy()
                            multi_choice_instruction["action"] = "click"
                            multi_choice_instruction["target_original_index"] = selected_option_data["original_index"]
                            fill_instructions.append(multi_choice_instruction)
            elif q_type == "6": # 矩阵题
                sub_questions_raw_configs = q_template.get("sub_questions_raw_configs", [])
                for sub_q_config in sub_questions_raw_configs: # 遍历每个子问题的配置
                    sub_q_options_parsed = sub_q_config.get("sub_q_options_parsed", []) # 子问题的选项
                    raw_sub_q_weights_str = sub_q_config.get("raw_weight_input", "") # 子问题的权重字符串
                    if sub_q_options_parsed: # 必须有选项
                        num_sub_opts = len(sub_q_options_parsed)
                        sub_q_weights = parse_weights_from_string(raw_sub_q_weights_str, num_sub_opts) # 解析权重
                        chosen_sub_q_opt_idx = calculate_choice_from_weights(sub_q_weights) # 按权重选择
                        if chosen_sub_q_opt_idx != -1: # 如果成功选择
                            selected_sub_q_opt_data = sub_q_options_parsed[chosen_sub_q_opt_idx]
                            matrix_sub_instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                                      "action": "matrix_click", # 动作：矩阵点击
                                                      "sub_q_id_prefix": sub_q_config["sub_q_id_prefix"], # 子问题行ID前缀
                                                      "sub_q_original_index": sub_q_config.get("sub_q_original_index"), # 子问题原始行索引
                                                      "target_original_index": selected_sub_q_opt_data["original_index"]} # 目标选项的原始列索引
                            fill_instructions.append(matrix_sub_instruction)
                        elif sub_q_options_parsed: # 权重选择失败，随机选
                            selected_sub_q_opt_data = random.choice(sub_q_options_parsed)
                            matrix_sub_instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                                      "action": "matrix_click",
                                                      "sub_q_id_prefix": sub_q_config["sub_q_id_prefix"],
                                                      "sub_q_original_index": sub_q_config.get("sub_q_original_index"),
                                                      "target_original_index": selected_sub_q_opt_data["original_index"]}
                            fill_instructions.append(matrix_sub_instruction)
            elif q_type == "11": # 排序题
                instruction = instruction_base.copy()
                instruction["action"] = "sort_random" # 动作：随机排序
                instruction["sortable_options_parsed"] = options_parsed # 传递可排序项的原始数据给Worker
                fill_instructions.append(instruction)

        # 如果没有生成任何指令，但模板存在，说明配置可能有问题（通常Worker内部会处理，这里不弹窗）
        if not fill_instructions and template:
            pass
        return fill_instructions
