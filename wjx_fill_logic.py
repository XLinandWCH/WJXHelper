# wjx_fill_logic.py
# 本文件包含问卷星单个题目填写操作的逻辑实现。

import time
import random
import numpy # 用于概率计算 (虽然计算逻辑可能在其他地方)，这里可能还需要 random
import re
from PIL import Image
import os
import io

# Selenium 相关的导入，这些是执行具体填充动作所必需的库和类
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (NoSuchElementException, TimeoutException,
                                        ElementClickInterceptedException, StaleElementReferenceException,
                                        WebDriverException)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 导入填空题分隔符和格式标记常量
# IMPORTANT: 为了解决循环导入问题，这些常量应该被定义在一个独立的模块中，例如 constants.py
# 请确保您创建了 constants.py 文件并将以下常量定义在其中。
try:
    # 尝试从 constants 模块导入常量
    from constants import (_FILL_IN_BLANK_FORMAT_SEQUENTIAL,
                           _FILL_IN_BLANK_FORMAT_RANDOM)
    # 如果需要，也可以在这里导入 _FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM
    # from constants import _FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM
except ImportError:
    # 如果 constants 模块不存在或常量未定义，使用默认值或打印错误
    # 在实际应用中，应确保 constants.py 存在且包含这些定义
    print("WARNING: Failed to import fill-in-blank format constants from constants.py. Using default values.")
    _FILL_IN_BLANK_FORMAT_SEQUENTIAL = "sequential_default" # 使用一个默认值，尽管这可能不是最优解
    _FILL_IN_BLANK_FORMAT_RANDOM = "random_default"


# 导入共享状态和锁（虽然 Worker 管理它们，但这里的逻辑需要访问）
from PyQt5.QtCore import QMutex # 只导入类型提示，实际对象由 Worker 传入

class WJXFillLogic:
    """
    负责执行单个问卷题目填写操作的逻辑类。
    不持有 WebDriver 实例（通过参数传入），也不管理线程或信号。
    通过回调函数或返回结果与调用者（例如 FillerWorker 线程）交互。
    """

    def __init__(self, driver: WebDriver, worker_id: int, log_callback,
                 is_running_check, is_paused_check,
                 shared_sequential_indices: dict = None,
                 sequential_indices_mutex: QMutex = None,
                 slow_mode: bool = False,
                 human_like_mode_config: dict = None):
        """
        初始化问卷填写逻辑实例。

        Args:
            driver: 当前正在使用的 Selenium WebDriver 实例。
            worker_id: 调用此逻辑的工作线程ID，用于日志标识。
            log_callback: 用于发送日志消息的回调函数 (msg_type, message)。
            is_running_check: 检查Worker是否应继续运行的回调函数 (返回 bool)。
            is_paused_check: 检查Worker是否暂停的回调函数 (返回 bool)。
            shared_sequential_indices: 所有Worker共享的顺序填空索引字典，键是问题ID (q_div_id)，值是下一个要使用的索引。
            sequential_indices_mutex: 访问共享顺序填空索引字典时使用的互斥锁。
            slow_mode: 是否启用慢速稳定模式以应对反爬虫。
            human_like_mode_config: 包含“拟人工”模式配置的字典, e.g., {'enabled': True, 'min_delay': 0.5, 'max_delay': 2.0}
        """
        self.driver = driver
        self.worker_id = worker_id
        self._log = log_callback # 保存日志回调函数
        self._is_running = is_running_check # 保存运行状态检查回调
        self._is_paused = is_paused_check   # 保存暂停状态检查回调
        self.slow_mode = slow_mode

        # "拟人工" 模式配置
        self.human_like_mode_enabled = human_like_mode_config.get('enabled', False) if human_like_mode_config else False
        self.human_like_min_delay = human_like_mode_config.get('min_delay', 0.0) if human_like_mode_config else 0.0
        self.human_like_max_delay = human_like_mode_config.get('max_delay', 1.5) if human_like_mode_config else 1.5

        # 共享状态和锁的引用，用于顺序填写等需要全局状态的场景
        self._shared_sequential_indices = shared_sequential_indices
        self._sequential_indices_mutex = sequential_indices_mutex

        # 预编译一些常用的XPath/CSS选择器字符串格式，提高效率和代码可读性
        # 注意：这里存储的是格式字符串，实际使用时会用 format() 填充
        self._xpath_q_element = "//div[@id='{}' and @topic='{}']" # 定位问题主div
        self._css_input_textarea = "#{0} input[id='q{1}'], #{0} textarea[id='q{1}'], #{0} input.inputtext, #{0} textarea.inputtext" # 定位填空题/多行文本框/滑块题的输入框
        self._css_option_radio_checkbox = "#{0} div.ui-controlgroup > div:nth-child({1})" # 定位单选/多选选项容器 (通常是包含input和label的div)
        self._css_option_scale_item = "#{0} div.scale-div ul > li:nth-child({1})" # 定位量表题选项容器 (通常是li元素)
        self._xpath_matrix_option_td = "//*[@id='{0}']/td[{1}]" # 定位矩阵题选项 td (通过子问题行ID和td序号)
        self._css_matrix_option_td = "#{0} > td:nth-child({1})" # 备用：定位矩阵题选项 td CSS
        self._xpath_sortable_list = "//div[@id='{}']//ul[contains(@class,'sort_data') or contains(@class,'sortable') or contains(@class,'rank')]" # 定位排序题的列表容器
        self._xpath_sortable_items = "./li" # 定位排序项 li (相对于列表容器)

    def _emit_log(self, msg_type, message):
        """
        通过回调函数发送日志消息给调用者（通常是Worker或主线程）。
        """
        if self._log:
            self._log(msg_type, message)

    def process_instruction(self, instruction):
        """
        根据给定的填写指令处理单个题目。这是核心逻辑入口。

        Args:
            instruction: 单个题目的填写指令字典，包含题目ID、类型、动作、目标值等信息。

        Returns:
            bool: 如果指令成功处理（不代表问卷提交成功），返回 True；否则返回 False。
                  处理失败或收到停止信号时返回 False。
        """
        # 每次处理指令前检查全局状态 (运行/暂停)
        while self._is_paused() and self._is_running():
            # 如果暂停且未停止，则短时间休眠等待
            time.sleep(0.1)
        if not self._is_running():
            # 如果收到停止信号，则中止处理
            self._emit_log("info", f"线程 {self.worker_id}: 收到停止信号，中止处理指令。")
            return False # 如果需要停止，立即返回失败

        # 在处理每个题目指令前，检查是否有验证码
        if self._handle_captcha():
            self._emit_log("info", f"线程 {self.worker_id}: 已处理验证码，继续执行指令。")
        else:
            # 如果处理验证码失败（例如AI识别失败且需要人工干预），则认为当前指令处理失败
            self._emit_log("warn", f"线程 {self.worker_id}: 验证码处理失败或需要人工干预，暂停当前指令。")
            return False

        # 解析指令中的关键信息
        q_div_id = instruction.get('id');
        q_topic_num = instruction.get('topic_num');
        q_type_code = instruction.get('type_code');
        action = instruction.get('action')

        # 验证指令基本格式
        if not q_div_id or not q_topic_num or not q_type_code or not action:
            self._emit_log("error", f"线程 {self.worker_id}: 指令格式无效，跳过。指令: {instruction}")
            return False

        self._emit_log("debug",
                       f"线程 {self.worker_id}: 正在处理 题 {q_topic_num} ({q_div_id}), 类型 {q_type_code}, 动作: {action}")

        try:
            # 定位问题所在的区域元素（通常是一个div）
            # 使用 WebDriverWait 等待元素可见，增加鲁棒性
            q_element_xpath = self._xpath_q_element.format(q_div_id, q_topic_num)
            q_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, q_element_xpath)))
            # 滚动到问题元素，确保其在可视区域内以便交互
            self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded({behavior: 'auto', block: 'center'});",
                                       q_element)
            time.sleep(random.uniform(0.3, 0.8)) # 增加滚动后的等待时间

            if self.slow_mode:
                # 模拟用户在看题时的随机滚动
                scroll_offset = random.randint(-50, 50)
                self.driver.execute_script(f"window.scrollBy(0, {scroll_offset});")
                time.sleep(random.uniform(0.5, 1.2))

            # 根据指令的动作类型，调用不同的处理函数
            if action == "fill":
                # 处理填充文本框指令 (填空题/多行填空/滑块题)
                return self._fill_text_question(q_element, instruction)

            elif action == "click":
                # 处理点击选择指令 (单选/多选/量表题)
                return self._click_option_question(q_element, instruction)

            elif action == "dropdown_select":
                # 处理下拉选择指令 (下拉选择题)
                return self._dropdown_select_question(q_element, instruction)

            elif action == "matrix_click":
                # 处理矩阵题点击指令 (矩阵题)
                return self._matrix_click_question(q_element, instruction)

            elif action == "sort_random":
                # 处理排序题随机排序指令 (排序题)
                return self._sort_random_question(q_element, instruction)

            else:
                # 如果动作类型未知
                self._emit_log("warn",
                               f"线程 {self.worker_id}: 题 {q_topic_num}: 未知动作 '{action}'。跳过此指令。")
                return False

        # 捕获可能的 Selenium 异常和通用异常
        except TimeoutException:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 操作超时: 题 {q_topic_num}, ID {q_div_id}, 动作 {action}。问题元素未找到或不可交互。")
            return False
        except NoSuchElementException:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 元素未找到: 题 {q_topic_num}, ID {q_div_id}, 动作 {action}。问题元素未找到。")
            return False
        except Exception as e:
            # 捕获其他所有未预期的异常
            self._emit_log("error",
                           f"线程 {self.worker_id}: 处理 题 {q_topic_num} ({q_div_id}) 时发生错误: {type(e).__name__} - {str(e)[:150]}...") # 限制错误信息长度
            return False
        finally:
            # 每个操作成功或失败后，短暂等待，模拟用户行为间隔
            # 只有在未收到停止信号时才执行等待
            if self._is_running():
                base_sleep = 0.8 if self.slow_mode else 0.3
                time.sleep(random.uniform(base_sleep, base_sleep + 0.7))

    def _fill_text_question(self, q_element, instruction):
        """
        处理填空题 (类型 1)、多行填空题 (类型 2) 和滑块题 (类型 8) 的填充逻辑。
        根据填空格式 (随机/顺序) 或滑块值填写文本框。
        """
        q_div_id = instruction.get('id'); # 问题div ID
        q_topic_num = instruction.get('topic_num'); # 题目序号
        q_type_code = instruction.get('type_code'); # 题目类型代码
        text_to_fill = "" # 待填写的文本，默认为空字符串

        try:
            if q_type_code in ["1", "2"]: # 填空题 / 多行填空题
                answers_list = instruction.get("text_answers_list", [""]) # 获取可能包含多个答案的列表
                fill_format = instruction.get("fill_format", _FILL_IN_BLANK_FORMAT_RANDOM) # 获取填写格式，默认为随机

                # 检查答案列表是否有效
                if not answers_list or (len(answers_list) == 1 and not str(answers_list[0]).strip()):
                     # 如果答案列表为空，或者只包含一个空字符串/None
                     self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num}: 答案列表为空或无效，填空字符串。")
                     text_to_fill = "" # 填空字符串或保持默认空字符串
                elif fill_format == _FILL_IN_BLANK_FORMAT_RANDOM:
                    # 随机填写模式：从答案列表中随机选择一个
                    text_to_fill = random.choice(answers_list)
                    self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} (随机填写): 选定答案 '{text_to_fill}'")
                elif fill_format == _FILL_IN_BLANK_FORMAT_SEQUENTIAL:
                    # 顺序填写模式：使用共享索引确定答案
                    # 检查共享状态和锁是否已正确传递和初始化
                    if self._shared_sequential_indices is not None and self._sequential_indices_mutex is not None:
                        self._sequential_indices_mutex.lock() # 在访问共享字典前加锁
                        try:
                            # 使用 get() 方法安全地获取当前索引，如果字典中没有该题的记录，默认为 0
                            current_idx = self._shared_sequential_indices.get(q_div_id, 0)
                            # 使用模运算确保索引在答案列表的有效范围内，实现循环使用答案
                            text_to_fill = answers_list[current_idx % len(answers_list)]
                            # 更新该题 (由 q_div_id 标识) 在共享状态中的下一个要使用的索引
                            self._shared_sequential_indices[q_div_id] = current_idx + 1
                            self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 使用全局索引 {current_idx} 的答案 '{text_to_fill}'，全局下一份将使用索引 {self._shared_sequential_indices[q_div_id]}")
                        except Exception as e_lock:
                            # 访问共享索引或列表时发生异常
                            self._emit_log("error", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 访问共享索引时出错: {type(e_lock).__name__} - {e_lock}")
                            text_to_fill = "" # 出错时填空字符串作为回退
                        finally:
                            self._sequential_indices_mutex.unlock() # 无论是否发生异常，都尝试解锁
                    else:
                         # 如果共享状态或锁未正确传递，则无法执行顺序填写
                         self._emit_log("error", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 共享状态或互斥锁未正确传递，无法进行顺序填写。填空字符串。")
                         text_to_fill = "" # 无法顺序填写时填空字符串作为回退
                else:
                    # 未知的填空格式
                    self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num}: 未知填空格式 '{fill_format}'。填空字符串。")
                    text_to_fill = ""


            elif q_type_code == "8": # 滑块题
                # 滑块题的待填值通常直接存储在 instruction 的 text_answer 字段
                text_to_fill = instruction.get('text_answer', '')
                self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} (滑块): 目标值 '{text_to_fill}'")
                # 注意：这里的逻辑只是将滑块的目标值填入关联的文本框（如果存在）。
                # 问卷星的滑块通常还需要模拟拖拽滑块本身或点击滑块条上的位置，
                # 这部分逻辑可能需要更复杂的 ActionChains 操作，这里仅处理文本框填充。
                # 如果滑块没有关联的文本框，此处的填充操作将无效。

            else:
                # 未知 fill 动作对应的题目类型，这通常不应该发生如果parser逻辑正确
                self._emit_log("error", f"线程 {self.worker_id}: 题 {q_topic_num}: 未知类型 '{q_type_code}' 的 'fill' 动作。")
                return False

            # 定位文本输入框或多行文本框。使用 CSS 选择器。
            input_css_selector = self._css_input_textarea.format(q_div_id, q_topic_num)
            # 等待输入框元素出现并可交互 (尽管visibility_of_element_located可能更合适，但presence_of_element_located通常也够用)
            input_element = WebDriverWait(q_element, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, input_css_selector)))
            # 清空原有内容并填入新的文本
            input_element.clear();
            # 模拟打字效果，逐个字符输入并随机暂停
            for char in str(text_to_fill):
                input_element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15)) # 模拟打字间隔
            self._emit_log("debug",
                           f"线程 {self.worker_id}: 题 {q_topic_num} 填入: '{text_to_fill}'")
            return True # 填充成功
        except Exception as e:
            # 捕获填充文本框过程中发生的任何异常
            self._emit_log("error",
                           f"线程 {self.worker_id}: 填充文本框失败 题 {q_topic_num}: {type(e).__name__} - {e}")
            return False # 填充失败

    def _click_option_question(self, q_element, instruction):
        """
        处理单选题 (类型 3)、多选题 (类型 4) 和量表题 (类型 5) 的点击选择逻辑。
        根据目标选项的原始索引定位并点击选项元素。
        处理可能出现的“其他”选项文本框填充。
        """
        q_div_id = instruction.get('id')  # 获取问题div ID，用于定位选项容器
        q_topic_num = instruction.get('topic_num'); # 题目序号
        opt_original_idx = instruction.get('target_original_index');  # 获取目标选项的原始索引 (1-based，从1开始计数)
        q_type_code = instruction.get('type_code') # 题目类型代码

        css_selector_option = "" # 用于定位目标选项元素的 CSS 选择器
        if q_type_code in ["3", "4"]:
            # 单选/多选选项容器的CSS选择器。通常是包含 input/label 的 div 或 span。
            # 使用 nth-child() 根据原始索引定位。
            css_selector_option = self._css_option_radio_checkbox.format(q_div_id, opt_original_idx)
        elif q_type_code == "5":
            # 量表题选项容器的CSS选择器。通常是 li 元素。
            # 使用 nth-child() 根据原始索引定位。
            css_selector_option = self._css_option_scale_item.format(q_div_id, opt_original_idx)
        else:
            # 未知 click 动作对应的题目类型
            self._emit_log("warn",
                           f"线程 {self.worker_id}: 题 {q_topic_num}: 未知类型 '{q_type_code}' 的 'click' 动作。")
            return False # 无法处理此类型

        if not css_selector_option: return False  # 如果未能构建出选择器，直接返回失败

        try:
            # 等待目标选项元素变为可点击状态
            target_element = WebDriverWait(q_element, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector_option)))

            # 模拟鼠标悬停
            if self.slow_mode:
                ActionChains(self.driver).move_to_element(target_element).pause(random.uniform(0.3, 0.8)).perform()

            # "拟人工" 模式延迟
            if self.human_like_mode_enabled:
                delay = random.uniform(self.human_like_min_delay, self.human_like_max_delay)
                self._emit_log("debug", f"线程 {self.worker_id}: '拟人工'模式开启，延迟 {delay:.2f} 秒...")
                time.sleep(delay)

            # "拟人工" 模式延迟
            if self.human_like_mode_enabled:
                delay = random.uniform(self.human_like_min_delay, self.human_like_max_delay)
                self._emit_log("debug", f"线程 {self.worker_id}: '拟人工'模式开启，延迟 {delay:.2f} 秒...")
                time.sleep(delay)

            # 尝试直接点击元素
            try:
                target_element.click()
                self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 点击了选项 {opt_original_idx}.")
            except ElementClickInterceptedException:
                # 如果直接点击被其他元素拦截（例如有覆盖层），尝试使用 JavaScript 点击作为备用方案
                self._emit_log("warn",
                               f"线程 {self.worker_id}: 题目 {q_topic_num} 选项 {opt_original_idx} 点击被拦截，尝试JS点击...")
                self.driver.execute_script("arguments[0].click();", target_element)
                self._emit_log("debug", f"线程 {self.worker_id}: JS点击成功。")

            # 如果该选项需要填写“其他”文本，并且指令中包含了要填写的文本
            if instruction.get("requires_other_text_fill") and instruction.get("other_text_to_fill"):
                text_to_fill_for_other = instruction["other_text_to_fill"]  # 获取要填写的“其他”文本内容
                self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 选项 {opt_original_idx} 需要填写其他项文本。")
                try:
                    # 在选项容器内查找“其他”文本框。
                    # 需要重新定位选项容器，因为 target_element 可能不是容器本身，或者 DOM 在点击后发生了变化。
                    # 使用 presence_of_element_located 更稳定，因为它不要求元素可交互，只需存在于 DOM 中即可用于查找其子元素。
                    option_container_element = WebDriverWait(q_element, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector_option)))

                    other_text_field = None # 用于存储找到的“其他”文本框元素
                    # 尝试多种 XPath 定位“其他”文本框，以适应问卷星不同的 DOM 结构
                    # 这些 XPath 是相对于 option_container_element (即选项本身的 div/li 等容器)
                    # 尝试查找不是禁用、隐藏的 input 或 textarea
                    possible_other_input_xpaths = [
                        ".//input[@type='text'][not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))][1]",
                        ".//textarea[@type='text'][not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))][1]",
                        # 更通用的，查找当前选项容器的紧邻兄弟节点中的文本框
                        "./following-sibling::input[@type='text'][1][not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))]",
                        "./following-sibling::textarea[@type='text'][1][not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))]",
                        # 如果是 label 内嵌 input/checkbox 的情况，查找 label 的兄弟节点中的文本框
                        ".//label/following-sibling::input[@type='text'][1][not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))]",
                        ".//label/following-sibling::textarea[@type='text'][1][not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))]"
                        # 还可以添加其他可能的定位策略
                    ]

                    # 遍历尝试所有可能的 XPath
                    for xpath_attempt in possible_other_input_xpaths:
                        try:
                            # 使用 find_elements 查找，即使没找到也不会抛异常，返回空列表
                            candidates = option_container_element.find_elements(By.XPATH, xpath_attempt)
                            # 检查是否找到了元素，并且第一个元素是可见且启用的
                            if candidates and candidates[0].is_displayed() and candidates[0].is_enabled():
                                other_text_field = candidates[0] # 找到有效的文本框
                                break  # 找到即停止查找循环
                            # 如果找到了元素但不可用 (is_displayed() or is_enabled() 为 False)，则 other_text_field 保持 None，继续下一个 xpath
                        except Exception as e_find_other:
                            # 查找过程中可能出现的其他异常，例如 StaleElementReferenceException (虽然 find_elements 不抛出 NoSuchElement)
                             self._emit_log("debug",
                                           f"线程 {self.worker_id}: 题 {q_topic_num}, 选项 {opt_original_idx}(其他): 查找文本框尝试XPath '{xpath_attempt}' 失败或不可用: {type(e_find_other).__name__} - {str(e_find_other)[:100]}...")
                             pass # 继续尝试下一个 XPath

                    # 如果成功找到了有效的“其他”文本框元素
                    if other_text_field:
                        # 滚动到文本框以便交互
                        self.driver.execute_script(
                            "arguments[0].scrollIntoViewIfNeeded({behavior: 'auto', block: 'center'});",
                            other_text_field)
                        time.sleep(random.uniform(0.1, 0.3)) # 短暂等待滚动
                        other_text_field.clear();  # 清空原有内容
                        other_text_field.send_keys(text_to_fill_for_other)  # 填入指令中的文本
                        self._emit_log("debug",
                                       f"线程 {self.worker_id}: 题 {q_topic_num} 其他项填入: '{text_to_fill_for_other}'")
                        time.sleep(random.uniform(0.1, 0.3))  # 短暂等待填写完成
                    else:
                        # 如果遍历所有 XPath 都未找到可用的文本框
                        self._emit_log("warn",
                                       f"线程 {self.worker_id}: 题 {q_topic_num}, 选项 {opt_original_idx}(其他): 已勾选并有文本，但未找到对应文本框或文本框不可用。")

                except TimeoutException:  # 查找选项容器或“其他”文本框时超时
                    self._emit_log("error",
                                   f"线程 {self.worker_id}: 题 {q_topic_num} 选项 {opt_original_idx}: 查找选项容器或'其他'文本框超时。")
                except NoSuchElementException:  # 查找选项容器时未找到
                    self._emit_log("error",
                                   f"线程 {self.worker_id}: 题 {q_topic_num} 选项 {opt_original_idx}: 查找选项容器未找到。")
                except Exception as e_other_fill:  # 填写“其他”文本时发生其他错误
                    self._emit_log("error",
                                   f"线程 {self.worker_id}: 题 {q_topic_num} 填充'其他'项文本时出错: {type(e_other_fill).__name__} - {str(e_other_fill)[:150]}...")

            return True # 点击选项操作本身成功
        except TimeoutException:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 题 {q_topic_num} 选项 {opt_original_idx}: 等待选项元素可点击超时。")
            return False # 操作失败
        except NoSuchElementException:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 题 {q_topic_num} 选项 {opt_original_idx}: 未找到选项元素 (CSS: {css_selector_option})。")
            return False # 操作失败
        except Exception as e:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 点击选项失败 题 {q_topic_num}, 选项 {opt_original_idx}: {type(e).__name__} - {str(e)[:150]}...")
            return False # 操作失败

    def _dropdown_select_question(self, q_element, instruction):
        """
        处理下拉选择题 (类型 7) 逻辑。
        点击下拉框容器展开列表，然后点击目标选项。
        尝试处理可能出现的“其他”项文本框填充。
        """
        q_topic_num = instruction.get('topic_num'); # 题目序号
        opt_original_idx = instruction.get('target_original_index'); # 获取目标选项在下拉列表中的原始索引 (1-based)
        q_div_id = instruction.get('id') # 获取问题div ID (可能用于定位其他相关的元素，虽然下拉列表本身通常在 body 下)

        try:
            # 定位下拉框容器并点击展开。
            # 问卷星的下拉框常使用 select2 库，其容器通常有 ID 模式 select2-q<题号>-container
            dropdown_container_id = f"select2-q{q_topic_num}-container"
            container_element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, dropdown_container_id)))
            container_element.click();
            time.sleep(random.uniform(0.3, 0.7)) # 等待下拉列表动态出现

            # 定位下拉列表中的目标选项并点击。
            # 下拉列表本身通常有 ID select2-q<题号>-results，选项是其 li 子元素。
            # 重要：下拉列表元素通常挂载在 body 下，而不是在 q_element 内部，所以使用全局 XPath。
            option_xpath = f"//ul[@id='select2-q{q_topic_num}-results']/li[{opt_original_idx}]"
            # 等待选项元素可点击
            option_element_to_click = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, option_xpath)))

            # 尝试点击选项元素
            try:
                 option_element_to_click.click()
                 self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉选择了选项 {opt_original_idx}.")
            except ElementClickInterceptedException:
                 # 如果点击被拦截，尝试 JS 点击
                self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉选项 {opt_original_idx} 点击被拦截，尝试JS点击...")
                self.driver.execute_script("arguments[0].click();", option_element_to_click)
                self._emit_log("debug", f"线程 {self.worker_id}: JS点击成功。")

            # 处理下拉框的“其他”项自定义文本填写。
            # 这通常涉及到选中“其他”选项后，页面上会动态出现一个文本框，需要找到并填写。
            # 文本框的定位方式可能与 select 元素的 name/ID 相关，例如 q<topic_num>_other 或 q<topic_num>_text。
            # 并且只有在选中“其他”选项后才出现。
            # 需要检查 instruction 中是否有其他文本信息，并根据解析到的 other_input_locator 找到文本框。
            if instruction.get("requires_other_text_fill") and instruction.get("other_text_to_fill"):
                 text_to_fill_for_other = instruction["other_text_to_fill"] # 获取要填写的文本
                 self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 需要填写下拉其他项文本。")
                 try:
                     # 从 instruction 中获取其他文本框的定位器信息
                     # Parser 应该负责解析并提供这个信息
                     other_text_input_locator = instruction.get("other_input_locator")

                     other_text_field = None
                     if other_text_input_locator:
                          locator_type = other_text_input_locator.get("type")
                          locator_value = other_text_input_locator.get("value")

                          if locator_type == "id":
                               other_text_field = WebDriverWait(self.driver, 5).until(
                                  EC.presence_of_element_located((By.ID, locator_value)))
                          elif locator_type == "name":
                              other_text_field = WebDriverWait(self.driver, 5).until(
                                  EC.presence_of_element_located((By.NAME, locator_value)))
                          # 可以根据 parser 支持的定位类型添加更多 elif 分支 (如 css, xpath)
                          else:
                               self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉其他项定位器类型 '{locator_type}' 不支持或无效。")

                     if other_text_field and other_text_field.is_displayed() and other_text_field.is_enabled():
                          # 滚动到文本框
                          self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded({behavior: 'auto', block: 'center'});", other_text_field)
                          time.sleep(random.uniform(0.1, 0.3))
                          other_text_field.clear() # 清空
                          other_text_field.send_keys(text_to_fill_for_other) # 填入文本
                          self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉其他项填入: '{text_to_fill_for_other}'")
                          time.sleep(random.uniform(0.1, 0.3)) # 短暂等待
                     else:
                          self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉其他项需要文本，但未找到或文本框不可用。定位器: {other_text_input_locator}")

                 except TimeoutException:
                     self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉其他项文本框等待超时。")
                 except NoSuchElementException:
                      self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉其他项文本框未找到 (定位器可能错误: {other_text_input_locator})。")
                 except Exception as e_other_fill:
                     self._emit_log("error", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉填充其他项文本时出错: {type(e_other_fill).__name__} - {str(e_other_fill)[:150]}...")


            return True # 下拉选择操作本身成功
        except TimeoutException:
            self._emit_log("error", f"线程 {self.worker_id}: 题 {q_topic_num}: 等待下拉框容器或选项超时。")
            return False # 操作失败
        except NoSuchElementException:
            self._emit_log("error", f"线程 {self.worker_id}: 题 {q_topic_num}: 未找到下拉框容器或选项元素。")
            return False # 操作失败
        except Exception as e:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 下拉选择失败 题 {q_topic_num}: {type(e).__name__} - {str(e)[:150]}...")
            return False # 操作失败

    def _matrix_click_question(self, q_element, instruction):
        """
        处理矩阵题 (类型 6) 的点击选择逻辑。
        矩阵题包含多个子问题 (行)，每个子问题选择一个或多个选项 (列)。
        指令中会包含子问题行的 ID 前缀和要点击的选项在行内的索引。
        """
        q_topic_num = instruction.get('topic_num'); # 题目序号
        sub_q_id_prefix = instruction.get('sub_q_id_prefix'); # 子问题行元素的ID前缀 (例如：jq1_1, jq1_2 等)
        opt_original_idx = instruction.get('target_original_index') # 子问题选项在子问题行中的原始索引 (1-based)

        try:
            # 定位矩阵选项元素 (通常是 td 元素，包含 radio 或 checkbox)。
            # 尝试通过子问题行 ID (sub_q_id_prefix) 和 td 的序号 (opt_original_idx) 进行定位。
            matrix_option_xpath = self._xpath_matrix_option_td.format(sub_q_id_prefix, opt_original_idx)
            matrix_option_css = self._css_matrix_option_td.format(sub_q_id_prefix, opt_original_idx) # CSS 备用选择器

            target_element = None # 用于存储找到的目标元素
            try:
                # 优先尝试等待 XPath 定位的元素变为可点击
                target_element = WebDriverWait(self.driver, 10).until(
                   EC.element_to_be_clickable((By.XPATH, matrix_option_xpath))
                )
            except (TimeoutException, NoSuchElementException):
                # 如果 XPath 找不到元素或元素不可点击，尝试使用 CSS 选择器
                self._emit_log("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (ID前缀: {sub_q_id_prefix}) 选项 {opt_original_idx} 通过XPATH找不到或不可点击，尝试CSS...")
                target_element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, matrix_option_css))
                )

            # 矩阵题通常需要使用 JavaScript 进行点击，以绕过一些可能的校验或覆盖层。
            # 滚动到元素，提高点击成功率
            self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded({behavior: 'auto', block: 'center'});", target_element)
            time.sleep(random.uniform(0.1, 0.3))

            # 使用 JS 点击元素
            self.driver.execute_script("arguments[0].click();", target_element)
            self._emit_log("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (ID前缀: {sub_q_id_prefix}) 点击了选项 {opt_original_idx}.")
            return True # 点击成功
        except TimeoutException:
             self._emit_log("error",
                            f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (ID前缀: {sub_q_id_prefix}) 选项 {opt_original_idx}: 等待元素可点击超时。")
             return False # 操作失败
        except NoSuchElementException:
             self._emit_log("error",
                            f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (ID前缀: {sub_q_id_prefix}) 选项 {opt_original_idx}: 未找到选项元素。")
             return False # 操作失败
        except Exception as e:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 矩阵题点击失败 题 {q_topic_num}, 子问题 (ID前缀: {sub_q_id_prefix}) 选项 {opt_original_idx}: {type(e).__name__} - {str(e)[:150]}...")
            return False # 操作失败


    def _sort_random_question(self, q_element, instruction):
        """
        处理排序题 (类型 11) 的随机排序逻辑。
        通过模拟拖拽操作，随机打乱排序项的顺序。
        """
        q_div_id = instruction.get('id'); # 问题div ID
        q_topic_num = instruction.get('topic_num'); # 题目序号

        try:
            # 定位排序列表容器 (ul 元素)
            sortable_list_container_xpath = self._xpath_sortable_list.format(q_div_id)
            sortable_list_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, sortable_list_container_xpath)))

            # 定位所有可排序项 (li 元素)
            # 先尝试查找带有 draggable="true" 属性的 li，如果找不到，则查找所有 li
            sortable_items_xpath = self._xpath_sortable_items # "./li"
            all_list_items_elements = sortable_list_element.find_elements(By.XPATH, f"{sortable_items_xpath}[@draggable='true']")
            if not all_list_items_elements:
                 all_list_items_elements = sortable_list_element.find_elements(
                    By.XPATH, sortable_items_xpath) # 如果没找到 draggable 属性的，使用所有 li

            num_items = len(all_list_items_elements) # 获取项目数量
            if num_items > 1: # 只有当项目数大于1时，才需要进行排序操作
                self._emit_log("info",
                                f"线程 {self.worker_id}: 排序题 {q_topic_num} 找到 {num_items} 个可排序项，进行随机拖拽。")
                actions_chain = ActionChains(self.driver); # 创建 ActionChains 对象，用于模拟复杂用户交互 (拖拽)

                # 设定随机拖拽的次数。次数越多，随机性越强，但耗时越长。
                # 可以根据项目数量调整，例如项目越多，拖拽次数可以是项目数的1-2倍；项目少时适当增加次数。
                num_drags = num_items * random.randint(1, 2);
                if num_items <= 3:
                    num_drags = num_items * 3 # 项目较少时，增加拖拽次数以更充分打乱

                # 在循环外部再次获取完整的项目列表 XPath，以便在循环内重新定位元素
                full_items_xpath = f"{sortable_list_container_xpath}{sortable_items_xpath}"

                # 执行多次随机拖拽
                for i in range(num_drags):
                    # 每次拖拽前检查全局状态 (暂停/停止)
                    while self._is_paused() and self._is_running():
                        time.sleep(0.1) # 暂停时短时间休眠
                    if not self._is_running():
                         # 如果收到停止信号，中止拖拽循环
                         self._emit_log("info", f"线程 {self.worker_id}: 排序题 {q_topic_num}: 收到停止信号，中止拖拽。")
                         return False # 停止并标记指令处理失败

                    try:
                        # !! 关键步骤 !!
                        # 每次拖拽前重新获取元素列表，因为拖拽操作可能改变 DOM 结构，导致之前的元素引用失效 (StaleElementReferenceException)
                        current_items_elements = self.driver.find_elements(By.XPATH, full_items_xpath)
                        if len(current_items_elements) < 2:
                            # 如果在拖拽过程中项目数变少或不足以拖拽，提前退出
                            self._emit_log("warn", f"线程 {self.worker_id}: 排序题 {q_topic_num}: 项目数在拖拽过程中变为 {len(current_items_elements)}，停止拖拽。")
                            break # 跳出拖拽循环

                        # 随机选择源元素和目标元素（即拖拽到哪个元素的位置）的索引
                        source_idx = random.randrange(len(current_items_elements));
                        target_idx = random.randrange(len(current_items_elements))
                        # 确保源和目标索引不同，避免无效操作或潜在问题
                        if source_idx == target_idx:
                            # 如果相同，随机选择相邻位置作为新目标索引
                            target_idx = (target_idx + random.choice([-1, 1])) % len(current_items_elements)
                             # 确保索引在合法范围内 (模运算处理了超出上限，这里检查下限)
                            if target_idx < 0: target_idx += len(current_items_elements)

                        source_element = current_items_elements[source_idx]; # 源元素
                        target_element = current_items_elements[target_idx] # 目标元素

                        # 滚动源元素到可视区域中心，提高拖拽的成功率
                        self.driver.execute_script(
                            "arguments[0].scrollIntoViewIfNeeded({behavior: 'auto', block: 'center'});",
                            source_element);
                        time.sleep(random.uniform(0.1, 0.2)) # 短暂等待滚动完成

                        # 执行拖拽操作链：按住源元素 -> 短暂停顿 -> 移动到目标元素 -> 短暂停顿 -> 释放
                        actions_chain.click_and_hold(source_element).pause(
                            random.uniform(0.1, 0.3)).move_to_element(target_element).pause(
                            random.uniform(0.1, 0.3)).release().perform()
                        time.sleep(random.uniform(0.4, 0.8)) # 每次拖拽操作后的等待时间

                        self._emit_log("debug", f"线程 {self.worker_id}: 排序题 {q_topic_num}: 完成第 {i+1}/{num_drags} 次拖拽。")

                    except StaleElementReferenceException:
                        # 如果在拖拽过程中遇到元素过时异常，说明 DOM 变了，需要重新获取元素列表，然后继续下一次拖拽
                        self._emit_log("warn", f"线程 {self.worker_id}: 排序项元素已过时 (StaleElementReferenceException)，重新尝试获取元素列表。");
                        time.sleep(0.2); # 短暂等待后继续循环，会在下一轮重新获取元素
                        continue # 继续内层拖拽循环

                    except Exception as e_drag:
                        # 拖拽时发生其他未知错误
                        self._emit_log("error", f"线程 {self.worker_id}: 排序题 {q_topic_num} 拖拽时出错: {type(e_drag).__name__} - {str(e_drag)[:100]}");
                        break # 发生错误则跳出拖拽循环

                self._emit_log("info", f"线程 {self.worker_id}: 排序题 {q_topic_num} 随机拖拽完成。")
            else:
                # 项目数不足无需排序
                self._emit_log("info",
                                f"线程 {self.worker_id}: 排序题 {q_topic_num} 项目数不足 ({num_items})，无需排序。")
            return True # 排序操作（尝试）成功
        except TimeoutException:
            self._emit_log("error",
                            f"线程 {self.worker_id}: 排序题 {q_topic_num} 列表容器未找到或超时。")
            return False # 操作失败
        except NoSuchElementException:
             self._emit_log("error",
                            f"线程 {self.worker_id}: 排序题 {q_topic_num} 列表容器或项目元素未找到。")
             return False # 操作失败
        except Exception as e:
            self._emit_log("error",
                           f"线程 {self.worker_id}: 排序题处理失败 题 {q_topic_num}: {type(e).__name__} - {str(e)[:150]}...")
            return False # 操作失败

# 可以根据需要添加更多处理其他题型的函数

    def _handle_captcha(self) -> bool:
        """
        检测页面上是否出现人机验证弹窗，并尝试处理它。

        Returns:
            bool: 如果没有验证码或验证码处理成功，返回 True。
                  如果AI识别失败需要人工干预，返回 False。
        """
        try:
            # 尝试定位验证码的关键元素，例如包含验证图片的容器
            # 使用 XPath 查找，因为问卷星的验证码弹窗结构可能比较特定
            # 注意：这些选择器需要根据实际问卷星页面的HTML结构进行调整
            captcha_container_xpath = "//div[contains(@class, 'captcha-container')] | //div[contains(@id, 'captcha-popup')]"
            captcha_element = self.driver.find_element(By.XPATH, captcha_container_xpath)

            if captcha_element and captcha_element.is_displayed():
                self._emit_log("warn", f"线程 {self.worker_id}: 检测到人机验证弹窗！")

                # 1. 截图验证码区域
                # 定位验证码图片元素
                img_element_xpath = ".//img[contains(@class, 'captcha-img')]"
                img_element = captcha_element.find_element(By.XPATH, img_element_xpath)

                # 获取图片位置和大小
                location = img_element.location
                size = img_element.size
                
                # 确保截图目录存在
                screenshots_dir = os.path.join(os.getcwd(), "captcha_screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)

                # 生成唯一的截图文件名
                screenshot_path = os.path.join(screenshots_dir, f"captcha_{self.worker_id}_{int(time.time())}.png")

                # 截取整个页面的图
                full_screenshot = self.driver.get_screenshot_as_png()
                
                # 从完整截图中裁剪出验证码图片
                img = Image.open(io.BytesIO(full_screenshot))
                
                left = location['x']
                top = location['y']
                right = location['x'] + size['width']
                bottom = location['y'] + size['height']

                # 考虑到高分屏(HiDPI)显示器，截图的实际像素可能是坐标的两倍
                # 这是一个简单的处理方式，更精确的方式需要获取 window.devicePixelRatio
                try:
                    pixel_ratio = self.driver.execute_script("return window.devicePixelRatio;")
                except WebDriverException:
                    pixel_ratio = 1.0 # 默认为1
                
                left, top, right, bottom = [int(c * pixel_ratio) for c in [left, top, right, bottom]]

                cropped_img = img.crop((left, top, right, bottom))
                cropped_img.save(screenshot_path)
                self._emit_log("info", f"线程 {self.worker_id}: 验证码图片已保存至: {screenshot_path}")

                # 2. 调用AI视觉服务
                # 导入 captcha_solver 模块 (确保在文件顶部已导入)
                from captcha_solver import solve_captcha
                # 从主窗口或配置中获取API Key (此处为占位)
                captcha_api_key = "dummy_key"
                captcha_api_secret = "dummy_secret"
                captcha_result = solve_captcha(screenshot_path, captcha_api_key, captcha_api_secret)

                # 3. 根据AI结果执行操作或回退
                if captcha_result.get("status") == "success":
                    # 如果AI成功，根据结果模拟点击等操作
                    solution = captcha_result.get("solution")
                    if self._perform_captcha_actions(captcha_element, solution):
                        self._emit_log("info", f"线程 {self.worker_id}: AI 验证码操作执行成功。")
                        # 验证后通常需要点击一个确认按钮
                        try:
                            confirm_button = captcha_element.find_element(By.XPATH, ".//button[contains(text(), '确认')] | .//div[contains(@class, 'submit')]")
                            confirm_button.click()
                            time.sleep(2) # 等待验证结果
                        except NoSuchElementException:
                            self._emit_log("warn", f"线程 {self.worker_id}: 未找到验证码的确认按钮。")
                        return True
                    else:
                        self._emit_log("error", f"线程 {self.worker_id}: AI 验证码操作执行失败。")
                        return False
                else:
                    # 如果AI失败，暂停线程，等待人工处理
                    self._emit_log("error", f"线程 {self.worker_id}: AI 验证码识别失败: {captcha_result.get('reason')}. 线程将暂停，请手动处理后继续。")
                    # 这里不直接调用 self._is_paused()，而是通过worker的状态来控制
                    # Worker 应该捕获这个 False 返回值并暂停自己
                    return False

            return True # 没有找到显示的验证码弹窗

        except NoSuchElementException:
            # 没有找到验证码元素，这是正常情况，说明页面上没有验证码
            return True
        except Exception as e:
            self._emit_log("error", f"线程 {self.worker_id}: 在检查或处理验证码时发生未知错误: {type(e).__name__} - {e}")
            return False # 出现未知错误时，也暂停以供检查

    def _perform_captcha_actions(self, captcha_container_element, solution: dict) -> bool:
        """
        根据AI返回的解决方案，在验证码容器内执行模拟操作。

        Args:
            captcha_container_element: 验证码容器的WebDriver元素。
            solution: 从captcha_solver返回的包含操作类型和数据的字典。

        Returns:
            bool: 操作是否成功执行。
        """
        if not solution or not isinstance(solution, dict):
            self._emit_log("error", "无效的验证码解决方案格式。")
            return False

        action_type = solution.get("type")
        action_data = solution.get("data")

        try:
            actions = ActionChains(self.driver)
            if action_type == "text_click":
                # 按照坐标顺序点击文字
                if not isinstance(action_data, list): return False
                # 点击操作的参考点是验证码图片本身，而不是整个容器
                img_element = captcha_container_element.find_element(By.XPATH, ".//img[contains(@class, 'captcha-img')]")
                
                for item in action_data:
                    x = item.get("x")
                    y = item.get("y")
                    if x is not None and y is not None:
                        self._emit_log("debug", f"模拟点击坐标: ({x}, {y})")
                        # move_to_element_with_offset: 从元素的左上角开始计算偏移
                        actions.move_to_element_with_offset(img_element, x, y).click()
                        actions.pause(random.uniform(0.3, 0.7))
                actions.perform()
                return True

            elif action_type == "slider":
                # 模拟滑块拖拽
                if not isinstance(action_data, dict): return False
                distance = action_data.get("distance")
                if distance is None: return False

                # 定位滑块按钮
                slider_button = captcha_container_element.find_element(By.XPATH, ".//div[contains(@class, 'slider-button')] | .//div[contains(@class, 'slide-button')]")
                
                # 执行拖拽
                actions.click_and_hold(slider_button).pause(0.2)
                # 模拟非匀速拖拽
                steps = 10
                for i in range(steps):
                    dx = (distance / steps) * (i + 1)
                    actions.move_by_offset(dx, random.randint(-5, 5))
                    actions.pause(random.uniform(0.01, 0.05))
                actions.release().perform()
                self._emit_log("debug", f"模拟滑块拖拽距离: {distance}px")
                return True

            else:
                self._emit_log("error", f"不支持的验证码操作类型: {action_type}")
                return False

        except NoSuchElementException as e:
            self._emit_log("error", f"执行验证码操作时未找到元素: {e}")
            return False
        except Exception as e:
            self._emit_log("error", f"执行验证码操作时发生未知错误: {type(e).__name__} - {e}")
            return False