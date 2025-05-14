# widgets_questionnaire_setup.py
import random
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
        self.driver_path = driver_path

    def run(self):
        result = fetch_questionnaire_structure(self.url, msedgedriver_path=self.driver_path)
        self.finished_signal.emit(result)


class QuestionnaireSetupWidget(QWidget):
    def __init__(self, parent=None):  # parent 通常是 MainWindow
        super().__init__(parent)
        self.main_window_ref = parent
        self.parsed_data = None  # 存储解析后的问卷结构
        self.question_widgets_map = {}  # 存储动态生成的题目控件，key是题目ID，value是相关控件字典
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- URL输入和加载 ---
        url_group = QGroupBox("问卷链接")
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("问卷URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入完整的问卷星链接 (例如: https://www.wjx.cn/vm/xxxx.aspx)")
        # self.url_input.setText("https://www.wjx.cn/vm/OM6GYNV.aspx#") # 测试用
        url_layout.addWidget(self.url_input, 1)  # 占据更多空间
        self.load_button = QPushButton("加载问卷")
        self.load_button.clicked.connect(self._load_questionnaire)
        url_layout.addWidget(self.load_button)
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)

        # --- 问卷题目配置区域 (可滚动) ---
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)  # 允许内容自动调整大小
        self.scroll_area.setFrameShape(QFrame.StyledPanel)  # 带边框

        self.questions_container_widget = QWidget()  # 滚动区域的内容控件
        self.questions_layout = QVBoxLayout(self.questions_container_widget)  # 题目将垂直排列
        self.questions_layout.setAlignment(Qt.AlignTop)  # 题目从顶部开始排列

        self.scroll_area.setWidget(self.questions_container_widget)
        main_layout.addWidget(self.scroll_area, 1)  # 占据剩余大部分空间

        # --- 状态/日志显示 (可选) ---
        self.status_label = QLabel("请先输入问卷URL并点击“加载问卷”。")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.parser_thread = None

    def _load_questionnaire(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入问卷URL。")
            return

        if self.parser_thread and self.parser_thread.isRunning():
            QMessageBox.information(self, "提示", "正在解析中，请稍候...")
            return

        self.load_button.setEnabled(False)
        self.status_label.setText(f"正在加载和解析问卷: {url} ... 请耐心等待。")
        self.main_window_ref.statusBar().showMessage("问卷解析中...")

        # 清空旧的题目控件
        self._clear_question_widgets()
        self.parsed_data = None
        self.question_widgets_map = {}

        # 获取 msedgedriver 路径
        driver_path = None
        if self.main_window_ref and hasattr(self.main_window_ref, 'basic_settings_panel'):
            driver_path = self.main_window_ref.basic_settings_panel.get_settings().get('msedgedriver_path')

        self.parser_thread = ParserThread(url, driver_path)
        self.parser_thread.finished_signal.connect(self._on_parsing_finished)
        self.parser_thread.start()

    def _on_parsing_finished(self, result):
        self.load_button.setEnabled(True)
        if isinstance(result, dict) and "error" in result:
            self.status_label.setText(f"问卷解析失败: {result['error']}")
            self.main_window_ref.statusBar().showMessage(f"问卷解析失败: {result['error']}")
            QMessageBox.critical(self, "解析错误", f"解析问卷时发生错误：\n{result['error']}")
            self.parsed_data = result  # 保存错误信息
        elif result:
            self.parsed_data = result
            self.status_label.setText(f"成功解析到 {len(result)} 个问题。请在下方配置各项答案权重。")
            self.main_window_ref.statusBar().showMessage(f"问卷解析成功，共 {len(result)} 个问题。")
            self._display_questions(result)
        else:
            self.status_label.setText("问卷解析未能返回任何问题结构。")
            self.main_window_ref.statusBar().showMessage("问卷解析结果为空。")
            QMessageBox.warning(self, "解析结果", "未能从问卷中解析出任何问题。")
            self.parsed_data = {"error": "解析结果为空"}

        self.parser_thread = None  # 清理线程对象

    def _clear_question_widgets(self):
        """清除动态生成的题目配置控件"""
        while self.questions_layout.count():
            child = self.questions_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.question_widgets_map.clear()

    def _display_questions(self, questions_data):
        """根据解析到的数据动态创建题目配置UI"""
        self._clear_question_widgets()

        type_counters = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "11": 0}

        for q_idx, q_data in enumerate(questions_data):
            q_id = q_data['id']
            q_topic = q_data['topic_num']
            q_type = q_data['type_code']
            q_text = q_data['text']
            q_options = q_data.get('options', [])
            q_sub_questions = q_data.get('sub_questions', [])

            type_counters[q_type] = type_counters.get(q_type, 0) + 1
            q_groupbox_title = (
                f"题目 {q_data.get('question_index_overall', q_idx + 1)} "
                f"(原始题号: {q_topic}, 类型: {self._get_question_type_name(q_type)} - 第{type_counters[q_type]}个此类题)"
            )
            q_groupbox = QGroupBox(q_groupbox_title)
            q_group_layout = QVBoxLayout()
            q_text_label = QLabel(q_text)
            q_text_label.setWordWrap(True)
            q_text_label.setObjectName("QuestionTextLabel")
            q_group_layout.addWidget(q_text_label)

            # 初始化存储该问题UI控件的字典
            self.question_widgets_map[q_id] = {
                "type": q_type,
                "q_data": q_data,  # 保存原始解析数据，方便后续使用
                "options_controls": [],
                "sub_questions_controls": []
            }

            if q_type in ["1", "2"]:
                text_input_label = QLabel("请输入填空内容:")
                text_input = QLineEdit()
                text_input.setPlaceholderText("填写的答案内容")
                self.question_widgets_map[q_id]["raw_text_input_widget"] = text_input  # 修改key名
                q_group_layout.addWidget(text_input_label)
                q_group_layout.addWidget(text_input)

            elif q_type in ["3", "5", "7"]:
                if not q_options:
                    q_group_layout.addWidget(QLabel("警告: 此选择题未解析到任何选项，无法配置。"))
                else:
                    q_group_layout.addWidget(QLabel("请为每个选项设置权重 (整数，用英文逗号隔开，例如: 30,70,0):"))
                    options_layout = QVBoxLayout()
                    for opt_idx, option_data in enumerate(q_options):
                        opt_label = QLabel(f"  选项 {opt_idx + 1}: {option_data['text']}")
                        options_layout.addWidget(opt_label)
                    weight_input = QLineEdit()
                    default_weights = ",".join(["1"] * len(q_options))
                    weight_input.setPlaceholderText(f"例如: {default_weights}")
                    weight_input.setText(default_weights)
                    self.question_widgets_map[q_id]["raw_weight_input_widget"] = weight_input  # 修改key名
                    options_layout.addWidget(weight_input)
                    q_group_layout.addLayout(options_layout)

            elif q_type == "4":
                if not q_options:
                    q_group_layout.addWidget(QLabel("警告: 此多选题未解析到任何选项，无法配置。"))
                else:
                    q_group_layout.addWidget(QLabel("请为每个选项设置被选中的概率 (0-100的整数，用英文逗号隔开):"))
                    options_layout = QVBoxLayout()
                    default_probs = []
                    for opt_idx, option_data in enumerate(q_options):
                        opt_label = QLabel(f"  选项 {opt_idx + 1}: {option_data['text']}")
                        options_layout.addWidget(opt_label)
                        default_probs.append("50")
                    prob_input_line = QLineEdit()
                    prob_input_line.setPlaceholderText(f"例如: {','.join(['50'] * len(q_options))}")
                    prob_input_line.setText(",".join(default_probs))
                    self.question_widgets_map[q_id]["raw_prob_input_widget"] = prob_input_line  # 修改key名
                    options_layout.addWidget(prob_input_line)
                    q_group_layout.addLayout(options_layout)

            elif q_type == "6":
                if not q_sub_questions:
                    q_group_layout.addWidget(QLabel("警告: 此矩阵题未解析到任何子问题或选项，无法配置。"))
                else:
                    q_group_layout.addWidget(QLabel("请为每个子问题的选项设置权重 (类似单选题，每行一个配置):"))
                    sub_q_controls_list = []  # 临时列表存储子问题控件
                    for sub_q_idx, sub_q_data in enumerate(q_sub_questions):
                        sub_q_label = QLabel(f"  子问题 {sub_q_idx + 1}: {sub_q_data['text']}")
                        q_group_layout.addWidget(sub_q_label)
                        sub_q_options_list = sub_q_data.get('options', [])
                        if not sub_q_options_list:
                            q_group_layout.addWidget(QLabel(f"    警告: 子问题 {sub_q_idx + 1} 未解析到选项。"))
                            continue
                        options_display_text = "    可选答案: " + " | ".join(
                            [f"{opt['text']}" for opt in sub_q_options_list])
                        q_group_layout.addWidget(QLabel(options_display_text))
                        sub_q_weight_input = QLineEdit()
                        default_sub_q_weights = ",".join(["1"] * len(sub_q_options_list))
                        sub_q_weight_input.setPlaceholderText(f"例如: {default_sub_q_weights}")
                        sub_q_weight_input.setText(default_sub_q_weights)
                        q_group_layout.addWidget(sub_q_weight_input)
                        # 存储子问题的原始解析数据和UI输入控件
                        sub_q_controls_list.append({
                            "sub_q_data": sub_q_data,  # 保存子问题的原始解析数据
                            "raw_weight_input_widget": sub_q_weight_input,
                        })
                    self.question_widgets_map[q_id]["sub_questions_controls"] = sub_q_controls_list


            elif q_type == "8":
                q_group_layout.addWidget(
                    QLabel("请输入滑块的值 (通常是1-100的整数，或用英文逗号分隔多个值及权重，如 60,70,80 和 1,2,1):"))
                slider_value_input = QLineEdit()
                slider_value_input.setPlaceholderText("例如: 75  或者  60,80:1,1 (值:权重)")
                slider_value_input.setText("75")
                self.question_widgets_map[q_id]["raw_slider_input_widget"] = slider_value_input  # 修改key名
                q_group_layout.addWidget(slider_value_input)

            elif q_type == "11":
                q_group_layout.addWidget(QLabel("排序题将自动进行随机排序，无需配置。"))
                if q_options:
                    q_group_layout.addWidget(QLabel("可排序项:"))
                    for opt_data in q_options:
                        q_group_layout.addWidget(QLabel(f"  - {opt_data['text']}"))
            else:
                q_group_layout.addWidget(
                    QLabel(f"此题型 ({self._get_question_type_name(q_type)}) 目前不支持详细配置，将尝试默认处理或跳过。"))

            q_groupbox.setLayout(q_group_layout)
            self.questions_layout.addWidget(q_groupbox)
        self.questions_layout.addStretch(1)

    def _get_question_type_name(self, type_code):
        names = {
            "1": "填空题", "2": "多行填空题", "3": "单选题", "4": "多选题",
            "5": "量表题", "6": "矩阵题", "7": "下拉选择题", "8": "滑块题",
            "11": "排序题"
        }
        return names.get(type_code, f"未知类型({type_code})")

    def get_parsed_questionnaire_data(self):
        return self.parsed_data

    def get_user_raw_configurations_template(self):  # 新方法名
        """
        收集用户在UI上为每个问题设置的原始配置信息（权重字符串、填空文本等），
        但不进行随机选择。返回一个“配置模板”列表，供 FillerWorker 在每次填写前进行随机化。
        """
        if not self.parsed_data or isinstance(self.parsed_data, dict) and "error" in self.parsed_data:
            return None

        raw_configs_template = []
        for q_id, ui_control_data in self.question_widgets_map.items():
            q_data_parsed = ui_control_data["q_data"]  # 获取保存的原始解析数据
            q_type = q_data_parsed['type_code']

            template_item = {
                "id": q_data_parsed['id'],
                "topic_num": q_data_parsed['topic_num'],
                "type_code": q_type,
                "options_parsed": q_data_parsed.get('options', []),  # 原始选项
                "sub_questions_parsed": q_data_parsed.get('sub_questions', [])  # 原始子问题（矩阵）
                # 注意：这里不包含action, text_answer, target_original_index等最终指令字段
                # 这些将在FillerWorker中根据下面的raw_inputs生成
            }

            if q_type in ["1", "2"]:  # 填空题
                widget = ui_control_data.get("raw_text_input_widget")
                if widget:
                    template_item["raw_text_input"] = widget.text()
                else:  # 如果没有对应控件，可能需要一个默认值或标记
                    template_item["raw_text_input"] = ""  # 默认空字符串

            elif q_type == "8":  # 滑块题
                widget = ui_control_data.get("raw_slider_input_widget")
                if widget:
                    template_item["raw_slider_input"] = widget.text()
                else:
                    template_item["raw_slider_input"] = "50"  # 默认值

            elif q_type in ["3", "5", "7"]:  # 单选、量表、下拉
                widget = ui_control_data.get("raw_weight_input_widget")
                if widget:
                    template_item["raw_weight_input"] = widget.text()
                else:  # 默认等权重
                    num_opts = len(template_item["options_parsed"])
                    template_item["raw_weight_input"] = ",".join(["1"] * num_opts) if num_opts > 0 else ""

            elif q_type == "4":  # 多选题
                widget = ui_control_data.get("raw_prob_input_widget")
                if widget:
                    template_item["raw_prob_input"] = widget.text()
                else:  # 默认50%
                    num_opts = len(template_item["options_parsed"])
                    template_item["raw_prob_input"] = ",".join(["50"] * num_opts) if num_opts > 0 else ""

            elif q_type == "6":  # 矩阵题
                template_item["sub_questions_raw_configs"] = []
                sub_q_controls = ui_control_data.get("sub_questions_controls", [])
                for sub_control in sub_q_controls:
                    sub_q_parsed_data = sub_control["sub_q_data"]  # 获取保存的子问题解析数据
                    widget = sub_control.get("raw_weight_input_widget")
                    raw_input_text = ""
                    if widget:
                        raw_input_text = widget.text()
                    else:  # 默认等权重
                        num_sub_opts = len(sub_q_parsed_data.get("options", []))
                        raw_input_text = ",".join(["1"] * num_sub_opts) if num_sub_opts > 0 else ""

                    template_item["sub_questions_raw_configs"].append({
                        "sub_q_id_prefix": sub_q_parsed_data["id_prefix"],
                        "sub_q_original_index": sub_q_parsed_data.get("original_index"),
                        "sub_q_options_parsed": sub_q_parsed_data.get("options", []),
                        "raw_weight_input": raw_input_text
                    })

            elif q_type == "11":  # 排序题 (通常不需要额外配置输入，但保持结构一致)
                template_item["is_sortable"] = True  # 标记为排序题

            else:  # 其他题型，可以简单传递原始解析数据
                pass  # 已经在template_item中包含了q_data_parsed的内容

            raw_configs_template.append(template_item)

        if not raw_configs_template and self.parsed_data:
            QMessageBox.warning(self, "配置警告", "未能收集到任何用户配置信息。")
            return None
        return raw_configs_template

    # 保留原来的 get_current_questionnaire_config，以防其他地方调用，但现在主要用上面的新方法
    # 或者可以移除它，如果确定主流程不再直接使用它来生成一次性配置
    def get_current_questionnaire_config(self):
        """
        [旧逻辑/备用] 根据用户在UI上的设置，生成用于 FillerWorker 的具体指令列表。
        注意：这个方法现在执行了随机化，如果每次填写都需要新的随机，
        那么这个方法不应该被外部一次性调用来获取配置。
        而是应该由 FillerWorker 内部根据 get_user_raw_configurations_template() 的结果，
        在每次填写前执行这里的随机化逻辑。
        为避免混淆，建议主流程使用 get_user_raw_configurations_template()。
        """
        if not self.parsed_data or isinstance(self.parsed_data, dict) and "error" in self.parsed_data:
            return None

        fill_instructions = []
        # 这里的逻辑与之前版本类似，包含了随机选择
        # 为了让新方案工作，这个函数应该被 get_user_raw_configurations_template() 替代
        # 或者它的随机化部分移到 FillerWorker._generate_randomized_instructions()
        # 为了演示，暂时保留其结构，但主流程不应依赖此版本进行多次不同随机填写

        # --- START OF PREVIOUS RANDOMIZATION LOGIC (for reference, will be moved) ---
        for q_data in self.parsed_data:  # q_data是原始解析数据
            q_id = q_data['id']
            q_topic_num = q_data['topic_num']
            q_type = q_data['type_code']
            q_options_parsed = q_data.get('options', [])

            ui_controls = self.question_widgets_map.get(q_id)
            if not ui_controls: continue

            instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type}

            if q_type in ["1", "2"]:
                widget = ui_controls.get("raw_text_input_widget")  # 使用新key名
                if widget:
                    instruction["action"] = "fill"
                    instruction["text_answer"] = widget.text()
                else:
                    continue

            elif q_type == "8":
                widget = ui_controls.get("raw_slider_input_widget")  # 使用新key名
                if widget:
                    instruction["action"] = "fill"
                    raw_slider_text = widget.text().strip()
                    try:  # (保持原来的滑块随机逻辑)
                        if ':' in raw_slider_text and ',' in raw_slider_text.split(':')[0]:
                            values_str, weights_str = raw_slider_text.split(':')
                            values = [int(v.strip()) for v in values_str.split(',')]
                            weights = [int(w.strip()) for w in weights_str.split(',')]
                            if len(values) == len(weights) and sum(weights) > 0:
                                chosen_value_idx = calculate_choice_from_weights(weights)
                                instruction["text_answer"] = str(values[chosen_value_idx])
                            else:
                                instruction["text_answer"] = str(values[0]) if values else "50"
                        elif ',' in raw_slider_text:
                            values = [int(v.strip()) for v in raw_slider_text.split(',')]
                            instruction["text_answer"] = str(random.choice(values)) if values else "50"
                        else:
                            instruction["text_answer"] = str(int(raw_slider_text))
                    except:
                        instruction["text_answer"] = "50"
                else:
                    continue

            elif q_type in ["3", "5", "7"]:
                widget = ui_controls.get("raw_weight_input_widget")  # 使用新key名
                if widget and q_options_parsed:
                    weights_str = widget.text()
                    num_opts = len(q_options_parsed)
                    weights = parse_weights_from_string(weights_str, num_opts)
                    chosen_option_idx_in_list = calculate_choice_from_weights(weights)
                    if chosen_option_idx_in_list != -1:
                        selected_option_data = q_options_parsed[chosen_option_idx_in_list]
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select"
                        instruction["target_original_index"] = selected_option_data["original_index"]
                    elif q_options_parsed:  # 随机
                        selected_option_data = random.choice(q_options_parsed)
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select"
                        instruction["target_original_index"] = selected_option_data["original_index"]
                    else:
                        continue
                else:
                    continue

            elif q_type == "4":
                widget = ui_controls.get("raw_prob_input_widget")  # 使用新key名
                if widget and q_options_parsed:
                    probs_str = widget.text()
                    try:
                        percentages = [int(p.strip()) for p in probs_str.split(',')]
                        if len(percentages) != len(q_options_parsed): raise ValueError("数量不匹配")
                        selected_indices_in_list = calculate_multiple_choices_from_percentages(percentages)
                        for selected_idx in selected_indices_in_list:
                            multi_choice_instruction = instruction.copy()
                            multi_choice_instruction["action"] = "click"
                            multi_choice_instruction["target_original_index"] = q_options_parsed[selected_idx][
                                "original_index"]
                            fill_instructions.append(multi_choice_instruction)
                        continue
                    except ValueError:
                        if q_options_parsed:
                            selected_option_data = random.choice(q_options_parsed)
                            instruction["action"] = "click"
                            instruction["target_original_index"] = selected_option_data["original_index"]
                        else:
                            continue
                else:
                    continue

            elif q_type == "6":
                sub_q_controls_ui_list = ui_controls.get("sub_questions_controls", [])
                # parsed_sub_questions_data = q_data.get("sub_questions", []) # 这应该从ui_controls的sub_q_data获取

                for sub_q_control_item in sub_q_controls_ui_list:
                    sub_q_parsed_data_item = sub_q_control_item["sub_q_data"]
                    sub_q_ui_widget = sub_q_control_item["raw_weight_input_widget"]
                    sub_q_options_list_parsed = sub_q_parsed_data_item.get("options", [])

                    if sub_q_ui_widget and sub_q_options_list_parsed:
                        weights_str = sub_q_ui_widget.text()
                        num_opts = len(sub_q_options_list_parsed)
                        weights = parse_weights_from_string(weights_str, num_opts)
                        chosen_option_idx_in_list = calculate_choice_from_weights(weights)
                        if chosen_option_idx_in_list != -1:
                            selected_option_data = sub_q_options_list_parsed[chosen_option_idx_in_list]
                            matrix_sub_instruction = {
                                "id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                "action": "matrix_click",
                                "sub_q_id_prefix": sub_q_parsed_data_item["id_prefix"],
                                "sub_q_original_index": sub_q_parsed_data_item.get("original_index"),
                                "target_original_index": selected_option_data["original_index"]
                            }
                            fill_instructions.append(matrix_sub_instruction)
                        elif sub_q_options_list_parsed:  # 随机
                            selected_option_data = random.choice(sub_q_options_list_parsed)
                            matrix_sub_instruction = {
                                "id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                "action": "matrix_click",
                                "sub_q_id_prefix": sub_q_parsed_data_item["id_prefix"],
                                "sub_q_original_index": sub_q_parsed_data_item.get("original_index"),
                                "target_original_index": selected_option_data["original_index"]
                            }
                            fill_instructions.append(matrix_sub_instruction)
                continue

            elif q_type == "11":
                instruction["action"] = "sort_random"

            else:
                continue

            fill_instructions.append(instruction)
        # --- END OF PREVIOUS RANDOMIZATION LOGIC ---

        if not fill_instructions and self.parsed_data:
            QMessageBox.warning(self, "配置警告", "未能根据当前设置生成任何有效的填写指令。请检查题目配置。")
            return None
        return fill_instructions

