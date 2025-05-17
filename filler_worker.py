# filler_worker.py
import time
import random
import traceback
import numpy  # 确保导入
from PyQt5.QtCore import QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException, \
    StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 导入工具函数 (确保 utils.py 在同一目录或PYTHONPATH中)
from utils import parse_weights_from_string, calculate_choice_from_weights, calculate_multiple_choices_from_percentages

MSEDGEDRIVER_PATH_WORKER = None


class FillerWorker(QThread):
    progress_signal = pyqtSignal(int, int, int, str, str)
    single_fill_finished_signal = pyqtSignal(int, bool, str)
    worker_completed_all_fills_signal = pyqtSignal(int)

    def __init__(self, worker_id, url, user_raw_configurations_template,
                 num_fills_for_this_worker, total_target_fills, headless=True, proxy=None, msedgedriver_path=None):
        super().__init__()
        self.worker_id = worker_id
        self.url = url
        self.user_raw_configurations_template = user_raw_configurations_template
        self.num_fills_to_complete_by_worker = num_fills_for_this_worker
        self.total_target_fills_all_workers = total_target_fills
        self.fills_completed_by_this_worker = 0
        self.is_running = True
        self.is_paused = False
        self.headless = headless
        self.proxy = proxy
        self.fill_config_instructions = []

        global MSEDGEDRIVER_PATH_WORKER
        if msedgedriver_path:
            MSEDGEDRIVER_PATH_WORKER = msedgedriver_path
        self.driver = None

    def _initialize_driver(self):
        edge_options = EdgeOptions()
        edge_options.use_chromium = True
        if self.headless:
            edge_options.add_argument("--headless")
            edge_options.add_argument("--disable-gpu")
        if self.proxy:
            edge_options.add_argument(f"--proxy-server={self.proxy}")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option('useAutomationExtension', False)
        edge_options.add_argument('--disable-blink-features=AutomationControlled')
        edge_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36 Edg/100.0.1185.50")
        service = None
        if MSEDGEDRIVER_PATH_WORKER:
            service = EdgeService(executable_path=MSEDGEDRIVER_PATH_WORKER)
        try:
            if service:
                self.driver = webdriver.Edge(service=service, options=edge_options)
            else:
                self.driver = webdriver.Edge(options=edge_options)
            self.driver.set_page_load_timeout(45)
            self.driver.implicitly_wait(8)
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                """
            })
            return True
        except Exception as e:
            self._emit_progress("error", f"线程 {self.worker_id}: 初始化EdgeDriver失败: {e}")
            return False

    def _emit_progress(self, msg_type, message):
        self.progress_signal.emit(self.worker_id, self.fills_completed_by_this_worker,
                                  self.num_fills_to_complete_by_worker, msg_type, message)

    def _generate_randomized_instructions(self, raw_configs_template):
        if not raw_configs_template:
            self._emit_progress("error", f"线程 {self.worker_id}: _generate_randomized_instructions: 原始配置模板为空。")
            return None
        fill_instructions = []
        for q_template in raw_configs_template:
            q_id = q_template['id']
            q_topic_num = q_template['topic_num']
            q_type = q_template['type_code']
            options_parsed = q_template.get('options_parsed', [])
            instruction_base = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type}

            # --- MODIFICATION START ---
            if q_type in ["1", "2"]:  # 填空题
                instruction = instruction_base.copy()
                instruction["action"] = "fill"
                # 从 'raw_text_answers_list' 获取答案列表
                possible_answers = q_template.get("raw_text_answers_list", [""])  # 默认值是一个包含空字符串的列表
                if not possible_answers:  # 再次确保列表不为空，尽管 setup 模块会保证
                    possible_answers = [""]
                instruction["text_answer"] = random.choice(possible_answers)  # 随机选择一个答案
                # print(f"Debug Worker {self.worker_id}: Generated text_answer for q {q_topic_num}: '{instruction['text_answer']}' from {possible_answers}") # 调试打印
                fill_instructions.append(instruction)
            # --- MODIFICATION END ---
            elif q_type == "8":  # 滑块题 (保持不变)
                instruction = instruction_base.copy()
                instruction["action"] = "fill"
                raw_slider_text = q_template.get("raw_slider_input", "50").strip()
                try:
                    if ':' in raw_slider_text and ',' in raw_slider_text.split(':')[0]:
                        values_str, weights_str = raw_slider_text.split(':')
                        values = [int(v.strip()) for v in values_str.split(',')]
                        weights_list = [int(w.strip()) for w in weights_str.split(',')]
                        if len(values) == len(weights_list) and sum(weights_list) > 0:
                            chosen_value_idx = calculate_choice_from_weights(weights_list)
                            instruction["text_answer"] = str(values[chosen_value_idx])
                        else:
                            instruction["text_answer"] = str(values[0]) if values else "50"
                    elif ',' in raw_slider_text:
                        values = [int(v.strip()) for v in raw_slider_text.split(',')]
                        instruction["text_answer"] = str(random.choice(values)) if values else "50"
                    else:
                        instruction["text_answer"] = str(int(raw_slider_text))
                except ValueError:
                    instruction["text_answer"] = "50"
                except Exception:
                    instruction["text_answer"] = "50"
                fill_instructions.append(instruction)
            elif q_type in ["3", "5", "7"]:  # 单选、量表、下拉 (保持不变)
                instruction = instruction_base.copy()
                raw_weights_str = q_template.get("raw_weight_input", "")
                if options_parsed:
                    num_opts = len(options_parsed)
                    weights = parse_weights_from_string(raw_weights_str, num_opts)
                    chosen_option_idx_in_list = calculate_choice_from_weights(weights)
                    if chosen_option_idx_in_list != -1:
                        selected_option_data = options_parsed[chosen_option_idx_in_list]
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select"
                        instruction["target_original_index"] = selected_option_data["original_index"]
                        fill_instructions.append(instruction)
                    elif options_parsed:  # 权重选择失败则随机选
                        selected_option_data = random.choice(options_parsed)
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select"
                        instruction["target_original_index"] = selected_option_data["original_index"]
                        fill_instructions.append(instruction)
            elif q_type == "4":  # 多选题 (保持不变)
                raw_probs_str = q_template.get("raw_prob_input", "")
                if options_parsed:
                    try:
                        percentages = [int(p.strip()) for p in raw_probs_str.split(',')]
                        if len(percentages) != len(options_parsed):
                            self._emit_progress("warn",
                                                f"线程 {self.worker_id}: 题目 {q_topic_num} 多选概率数量与选项不符，将随机选1-(N/2)个。")
                            num_to_select = random.randint(1, max(1, len(options_parsed) // 2))  # 确保至少选1个
                            selected_options_data = random.sample(options_parsed,
                                                                  min(num_to_select, len(options_parsed)))
                            for selected_opt_data in selected_options_data:
                                multi_choice_instruction = instruction_base.copy()
                                multi_choice_instruction["action"] = "click"
                                multi_choice_instruction["target_original_index"] = selected_opt_data["original_index"]
                                fill_instructions.append(multi_choice_instruction)
                        else:
                            selected_indices_in_list = calculate_multiple_choices_from_percentages(percentages)
                            for selected_idx in selected_indices_in_list:
                                multi_choice_instruction = instruction_base.copy()
                                multi_choice_instruction["action"] = "click"
                                multi_choice_instruction["target_original_index"] = options_parsed[selected_idx][
                                    "original_index"]
                                fill_instructions.append(multi_choice_instruction)
                    except ValueError:
                        self._emit_progress("warn",
                                            f"线程 {self.worker_id}: 题目 {q_topic_num} 多选概率配置错误，将随机选择1个。")
                        if options_parsed:
                            selected_option_data = random.choice(options_parsed)
                            multi_choice_instruction = instruction_base.copy()
                            multi_choice_instruction["action"] = "click"
                            multi_choice_instruction["target_original_index"] = selected_option_data["original_index"]
                            fill_instructions.append(multi_choice_instruction)
            elif q_type == "6":  # 矩阵题 (保持不变)
                sub_questions_raw_configs = q_template.get("sub_questions_raw_configs", [])
                for sub_q_config in sub_questions_raw_configs:
                    sub_q_options_parsed = sub_q_config.get("sub_q_options_parsed", [])
                    raw_sub_q_weights_str = sub_q_config.get("raw_weight_input", "")
                    if sub_q_options_parsed:
                        num_sub_opts = len(sub_q_options_parsed)
                        sub_q_weights = parse_weights_from_string(raw_sub_q_weights_str, num_sub_opts)
                        chosen_sub_q_opt_idx = calculate_choice_from_weights(sub_q_weights)
                        if chosen_sub_q_opt_idx != -1:
                            selected_sub_q_opt_data = sub_q_options_parsed[chosen_sub_q_opt_idx]
                            matrix_sub_instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                                      "action": "matrix_click",
                                                      "sub_q_id_prefix": sub_q_config["sub_q_id_prefix"],
                                                      "sub_q_original_index": sub_q_config.get("sub_q_original_index"),
                                                      "target_original_index": selected_sub_q_opt_data[
                                                          "original_index"]}
                            fill_instructions.append(matrix_sub_instruction)
                        elif sub_q_options_parsed:  # 随机
                            selected_sub_q_opt_data = random.choice(sub_q_options_parsed)
                            matrix_sub_instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                                      "action": "matrix_click",
                                                      "sub_q_id_prefix": sub_q_config["sub_q_id_prefix"],
                                                      "sub_q_original_index": sub_q_config.get("sub_q_original_index"),
                                                      "target_original_index": selected_sub_q_opt_data[
                                                          "original_index"]}
                            fill_instructions.append(matrix_sub_instruction)
            elif q_type == "11":  # 排序题 (保持不变)
                instruction = instruction_base.copy()
                instruction["action"] = "sort_random"
                instruction["sortable_options_parsed"] = options_parsed
                fill_instructions.append(instruction)
        if not fill_instructions and raw_configs_template:
            self._emit_progress("warn", f"线程 {self.worker_id}: 未能根据配置模板生成任何填写指令。")
        return fill_instructions

    def run(self):
        self._emit_progress("info", f"线程 {self.worker_id} 启动。目标份数: {self.num_fills_to_complete_by_worker}")
        while self.fills_completed_by_this_worker < self.num_fills_to_complete_by_worker and self.is_running:
            # 每次循环都重新初始化driver和生成指令，确保是“干净”的开始
            if not self._initialize_driver():
                self.single_fill_finished_signal.emit(self.worker_id, False, f"线程 {self.worker_id}: 驱动初始化失败")
                # 如果驱动初始化失败，可能需要决定是否中止整个worker或仅跳过本次
                break  # 当前逻辑是中止worker

            self.fill_config_instructions = self._generate_randomized_instructions(
                self.user_raw_configurations_template)

            if not self.fill_config_instructions:
                self._emit_progress("error", f"线程 {self.worker_id}: 无法为此填写尝试生成指令，跳过本次填写。")
                self.single_fill_finished_signal.emit(self.worker_id, False, f"线程 {self.worker_id}: 指令生成失败")
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = None
                time.sleep(random.uniform(1, 3))  # 短暂休眠后尝试下一次（如果还有次数）
                continue

            current_fill_success = False
            final_message_or_url = "未知原因失败"
            initial_url = self.url  # 保存初始URL用于比较

            try:
                self._emit_progress("info",
                                    f"线程 {self.worker_id}: 开始第 {self.fills_completed_by_this_worker + 1} 次填写尝试...")
                self.driver.get(initial_url)
                # 等待问卷主要内容区域加载
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.ID, "divQuestion"))  # "divQuestion" 是问卷题目容器的通用ID
                )
                time.sleep(random.uniform(1.0, 2.5))  # 页面加载后短暂等待

                # --- 题目填写循环 ---
                for instruction_index, instruction in enumerate(self.fill_config_instructions):
                    while self.is_paused and self.is_running: time.sleep(0.1)  # 处理暂停
                    if not self.is_running: break  # 处理外部中止信号

                    q_div_id = instruction['id']
                    q_topic_num = instruction['topic_num']
                    q_type_code = instruction['type_code']
                    action = instruction['action']
                    self._emit_progress("info",
                                        f"线程 {self.worker_id}: 指令 {instruction_index + 1}/{len(self.fill_config_instructions)}: 题 {q_topic_num} ({q_div_id}), 类型 {q_type_code}, 动作: {action}")

                    target_element_for_js_click = None  # 用于JS点击的备选元素
                    try:
                        # 定位当前题目的大容器div
                        q_element_xpath = f"//div[@id='{q_div_id}' and @topic='{q_topic_num}']"
                        q_element = WebDriverWait(self.driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, q_element_xpath))
                        )
                        # 根据动作类型执行操作
                        if action == "fill":
                            text_to_fill = instruction.get('text_answer', '')  # 从指令获取要填写的文本
                            # 定位填空题的输入框 (input 或 textarea)
                            input_css_selector = f"#{q_div_id} input[id='q{q_topic_num}'], #{q_div_id} textarea[id='q{q_topic_num}']"
                            input_element = WebDriverWait(q_element, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, input_css_selector))
                            )
                            input_element.clear()
                            input_element.send_keys(text_to_fill)
                            self._emit_progress("debug",
                                                f"线程 {self.worker_id}: 题 {q_topic_num} 填入: '{text_to_fill}'")

                        elif action == "click":  # 单选、多选、量表题的点击
                            opt_original_idx = instruction['target_original_index']
                            css_selector_option = ""
                            if q_type_code == "3" or q_type_code == "4":  # 单选或多选
                                css_selector_option = f"#{q_div_id} div.ui-controlgroup > div:nth-child({opt_original_idx})"
                            elif q_type_code == "5":  # 量表题
                                css_selector_option = f"#{q_div_id} div.scale-div ul > li:nth-child({opt_original_idx})"

                            if css_selector_option:
                                target_element = WebDriverWait(q_element, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector_option))
                                )
                                target_element_for_js_click = target_element  # 保存以便JS备用
                                target_element.click()

                        elif action == "dropdown_select":  # 下拉选择题
                            opt_original_idx = instruction['target_original_index']
                            # 点击下拉框使其展开
                            dropdown_container_id = f"select2-q{q_topic_num}-container"  # 这是展开前显示的元素ID
                            container_element = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.ID, dropdown_container_id))
                            )
                            container_element.click()
                            time.sleep(random.uniform(0.3, 0.7))  # 等待选项列表加载
                            # 选择展开后的具体选项
                            option_xpath = f"//ul[@id='select2-q{q_topic_num}-results']/li[{opt_original_idx}]"
                            option_element_to_click = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.XPATH, option_xpath))
                            )
                            target_element_for_js_click = option_element_to_click
                            option_element_to_click.click()

                        elif action == "matrix_click":  # 矩阵题点击
                            sub_q_id_prefix = instruction['sub_q_id_prefix']  # 这是矩阵子问题行的 tr 的 id
                            opt_original_idx = instruction['target_original_index']  # 这是选项列的索引
                            # 定位到子问题行内具体的选项单元格 td
                            matrix_option_css = f"#{sub_q_id_prefix} > td:nth-child({opt_original_idx})"
                            target_element = WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, matrix_option_css))
                                # 改为 presence_of_element_located 因为有时元素可见但不可直接点击，后续用JS
                            )
                            target_element_for_js_click = target_element
                            # 对于矩阵题，直接使用JS点击可能更稳定
                            self.driver.execute_script("arguments[0].click();", target_element)


                        elif action == "sort_random":  # 排序题
                            self._emit_progress("info", f"线程 {self.worker_id}: 正在处理排序题 {q_topic_num}...")
                            sortable_list_container_xpath = f"//div[@id='{q_div_id}']/ul[contains(@class,'sort_data') or contains(@class,'sortable') or contains(@class,'rank')]"
                            try:
                                sortable_list_element = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.XPATH, sortable_list_container_xpath))
                                )
                                sortable_items_xpath = f"{sortable_list_container_xpath}/li"
                                all_list_items_elements = sortable_list_element.find_elements(By.XPATH,
                                                                                              "./li[@draggable='true']")
                                if not all_list_items_elements:
                                    all_list_items_elements = sortable_list_element.find_elements(By.XPATH, "./li")

                                num_items = len(all_list_items_elements)
                                if num_items > 1:
                                    self._emit_progress("info",
                                                        f"线程 {self.worker_id}: 排序题 {q_topic_num} 找到 {num_items} 个可排序项。")
                                    actions = ActionChains(self.driver)
                                    num_drags = num_items * random.randint(1, 2)
                                    if num_items <= 3: num_drags = num_items * 3  # 少量项多拖几次确保打乱

                                    for _ in range(num_drags):
                                        if not self.is_running: break
                                        try:
                                            current_items_elements = self.driver.find_elements(By.XPATH,
                                                                                               sortable_items_xpath)  # 重新获取
                                            if len(current_items_elements) < 2: break

                                            source_idx = random.randrange(len(current_items_elements))
                                            target_idx = random.randrange(len(current_items_elements))
                                            if source_idx == target_idx:
                                                target_idx = (target_idx + random.choice([-1, 1]) + len(
                                                    current_items_elements)) % len(current_items_elements)

                                            source_element = current_items_elements[source_idx]
                                            target_element = current_items_elements[target_idx]

                                            self.driver.execute_script(
                                                "arguments[0].scrollIntoViewIfNeeded({behavior: 'smooth', block: 'center'});",
                                                source_element)
                                            time.sleep(0.15)

                                            actions.click_and_hold(source_element).pause(random.uniform(0.1, 0.3)) \
                                                .move_to_element(target_element).pause(random.uniform(0.1, 0.3)) \
                                                .release().perform()
                                            time.sleep(random.uniform(0.4, 0.8))  # 等待JS更新
                                        except StaleElementReferenceException:
                                            self._emit_progress("warn",
                                                                f"线程 {self.worker_id}: 排序项元素已过时，重新尝试获取。")
                                            time.sleep(0.2)  # 等待DOM稳定
                                            continue
                                        except Exception as e_drag:
                                            self._emit_progress("error",
                                                                f"线程 {self.worker_id}: 排序题 {q_topic_num} 拖拽时出错: {type(e_drag).__name__} - {str(e_drag)[:100]}")
                                            break
                                    self._emit_progress("info",
                                                        f"线程 {self.worker_id}: 排序题 {q_topic_num} 随机拖拽完成。")
                                else:
                                    self._emit_progress("info",
                                                        f"线程 {self.worker_id}: 排序题 {q_topic_num} 项目数不足 ({num_items})，无需排序。")
                            except TimeoutException:
                                self._emit_progress("error",
                                                    f"线程 {self.worker_id}: 排序题 {q_topic_num} 列表容器未找到或超时。")
                            except Exception as e_sort_setup:
                                self._emit_progress("error",
                                                    f"线程 {self.worker_id}: 排序题 {q_topic_num} 设置时出错: {e_sort_setup}")

                        time.sleep(random.uniform(0.2, 0.5))  # 每个指令后的小延迟

                    except ElementClickInterceptedException:
                        self._emit_progress("warn",
                                            f"线程 {self.worker_id}: 题目 {q_topic_num} 点击被拦截，尝试JS点击...")
                        try:
                            if target_element_for_js_click:
                                self.driver.execute_script("arguments[0].click();", target_element_for_js_click)
                                time.sleep(0.3)
                            else:
                                self._emit_progress("error", f"线程 {self.worker_id}: JS点击失败：未找到备用目标元素。")
                        except Exception as js_e:
                            self._emit_progress("error", f"线程 {self.worker_id}: JS点击也失败: {js_e}")
                    except TimeoutException:
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 操作超时: 题目 {q_topic_num}, ID {q_div_id}, 动作 {action}。")
                    except NoSuchElementException:
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 元素未找到: 题目 {q_topic_num}, ID {q_div_id}, 动作 {action}。")
                    except Exception as e_instr:
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 处理题目 {q_topic_num} 时发生错误: {type(e_instr).__name__} - {str(e_instr)[:150]}")
                        # 如果单个题目处理出错，可以选择是否继续处理后续题目或中止本次填写
                        # break # 如果希望出错则中止本次填写

                if not self.is_running: raise InterruptedError("用户中止操作")  # 检查在所有指令完成后，提交前是否被中止

                # --- 尝试翻页 (如果存在) ---
                try:
                    next_page_button = self.driver.find_element(By.ID, "divNextPage")  # 通用下一页按钮ID
                    if next_page_button.is_displayed() and next_page_button.is_enabled():
                        self._emit_progress("info",
                                            f"线程 {self.worker_id}: 所有已知指令完成，但发现“下一页”按钮，点击它...")
                        next_page_button.click()
                        WebDriverWait(self.driver, 15).until(EC.staleness_of(next_page_button))  # 等待页面跳转
                        time.sleep(random.uniform(1.0, 2.0))
                        # TODO: 如果问卷有多页，且每页的题目结构不同，可能需要更复杂的配置和指令生成逻辑
                        # 目前假设所有题目都在第一页或通过配置模板提供了所有页的指令
                except NoSuchElementException:
                    self._emit_progress("info", f"线程 {self.worker_id}: 未找到“下一页”按钮，准备提交。")
                    pass  # 没有下一页按钮，正常

                # --- 提交问卷 ---
                self._emit_progress("info", f"线程 {self.worker_id}: 所有指令执行完毕，尝试提交问卷...")
                submit_button_xpath = '//*[@id="ctlNext"]'  # 提交按钮的 XPath
                submit_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, submit_button_xpath))
                )
                submit_button.click()
                time.sleep(random.uniform(0.5, 1.0))  # 点击后短暂等待

                # --- 处理可能的提交确认弹窗 ---
                try:
                    confirm_button_xpath = "//div[contains(@class,'layui-layer-btn')]/a[normalize-space()='确定' or normalize-space()='确认']"
                    confirm_button = WebDriverWait(self.driver, 5).until(  # 等待时间缩短，因为不一定有
                        EC.element_to_be_clickable((By.XPATH, confirm_button_xpath))
                    )
                    confirm_button.click()
                    self._emit_progress("info", f"线程 {self.worker_id}: 点击了提交确认弹窗。")
                    time.sleep(random.uniform(0.8, 1.2))
                except TimeoutException:
                    self._emit_progress("info", f"线程 {self.worker_id}: 未找到或超时等待提交确认弹窗。")
                except NoSuchElementException:
                    pass  # 没找到也正常

                # --- 处理可能的智能验证按钮 (如果存在) ---
                try:
                    verify_button_id = "SM_BTN_1"  # 智能验证按钮ID
                    verify_button = WebDriverWait(self.driver, 5).until(  # 等待时间缩短
                        EC.element_to_be_clickable((By.ID, verify_button_id))
                    )
                    self._emit_progress("info", f"线程 {self.worker_id}: 检测到智能验证按钮，点击。")
                    verify_button.click()
                    # 点击后，通常会加载滑块验证或直接通过，需要等待后续的滑块或成功/失败页面
                    time.sleep(random.uniform(2.5, 4.0))
                except TimeoutException:
                    self._emit_progress("info", f"线程 {self.worker_id}: 未找到或超时等待智能验证按钮。")
                except NoSuchElementException:
                    pass

                # --- 处理滑块验证 (如果出现) ---
                try:
                    # 等待滑块验证的文本提示出现
                    slider_text_span_xpath = '//*[@id="nc_1__scale_text"]/span[contains(text(),"请按住滑块")]'
                    WebDriverWait(self.driver, 7).until(  # 等待时间调整
                        EC.visibility_of_element_located((By.XPATH, slider_text_span_xpath))
                    )
                    slider_button = self.driver.find_element(By.XPATH, '//*[@id="nc_1_n1z"]')  # 滑块本身
                    self._emit_progress("captcha", f"线程 {self.worker_id}: 检测到滑块验证，尝试拖动...")

                    # 模拟拖动滑块
                    actions = ActionChains(self.driver)
                    actions.click_and_hold(slider_button)

                    # 模拟非匀速、略微抖动的拖动
                    # 问卷星滑块通常需要拖动到最右侧，容器宽度约260-300px，滑块宽度约50px
                    # 所以实际拖动距离在210-250px左右，但这里直接尝试一个较大固定值然后让它碰壁
                    # 或者可以动态获取容器宽度 - 滑块宽度
                    total_drag_distance_target = random.randint(258, 280)  # 目标拖动总距离
                    num_segments = random.randint(3, 6)  # 分成几段拖动
                    current_moved_distance = 0

                    for i in range(num_segments):
                        if current_moved_distance >= total_drag_distance_target * 0.95: break  # 接近目标就停止

                        if i == num_segments - 1:  # 最后一段，补足剩余距离
                            segment_dist = total_drag_distance_target - current_moved_distance + random.randint(5,
                                                                                                                20)  # 稍微多一点点
                        else:
                            segment_dist = (total_drag_distance_target / num_segments) + random.randint(-15, 15)

                        segment_dist = max(10, int(segment_dist))  # 每段至少拖一点

                        # 避免单次拖动过大导致总距离超出太多
                        if current_moved_distance + segment_dist > total_drag_distance_target * 1.15:
                            segment_dist = total_drag_distance_target * 1.15 - current_moved_distance
                            if segment_dist <= 0: break

                        actions.move_by_offset(segment_dist, random.randint(-7, 7))  # 带点Y轴抖动
                        actions.pause(random.uniform(0.02, (0.15 if i < num_segments - 1 else 0.05)))  # 每段后短暂停顿
                        current_moved_distance += segment_dist

                    actions.release().perform()
                    self._emit_progress("info",
                                        f"线程 {self.worker_id}: 滑块拖动完成，总距离约: {current_moved_distance}px。")
                    time.sleep(random.uniform(2.5, 4.0))  # 拖动后等待验证结果

                except TimeoutException:
                    self._emit_progress("info", f"线程 {self.worker_id}: 未检测到滑块验证（或超时）。")
                except NoSuchElementException:
                    pass  # 没有滑块也正常
                except Exception as e_slider:
                    self._emit_progress("error",
                                        f"线程 {self.worker_id}: 滑块验证时出错: {type(e_slider).__name__} - {e_slider}")

                # --- 判断提交结果 ---
                self._emit_progress("info", f"线程 {self.worker_id}: 等待提交结果...")
                try:
                    # 等待URL变化或页面出现成功/失败关键词
                    WebDriverWait(self.driver, 12).until(  # 增加等待时间
                        EC.any_of(
                            EC.url_contains("finished"), EC.url_contains("result"), EC.url_contains("completed"),
                            EC.url_contains("thank"), EC.url_contains("Success"),  # 增加一些成功URL关键词
                            EC.presence_of_element_located((By.XPATH,
                                                            "//*[contains(text(),'提交成功') or contains(text(),'感谢您') or contains(text(),'已完成') or contains(text(),'谢谢')]")),
                            EC.presence_of_element_located((By.XPATH,
                                                            "//*[contains(text(),'提交失败') or contains(text(),'错误') or contains(@class, 'wjx_error') or contains(@class, 'error_validator')]"))
                            # 增加错误类名检测
                        )
                    )
                except TimeoutException:
                    self._emit_progress("warn", f"线程 {self.worker_id}: 等待最终结果超时，将基于当前页面状态判断。")

                final_url = self.driver.current_url
                final_title = self.driver.title.lower() if self.driver.title else ""
                page_source_lower = ""
                try:
                    page_source_lower = self.driver.page_source.lower()
                except:
                    self._emit_progress("warn", f"线程 {self.worker_id}: 无法获取最终页面的 page_source。")

                # 定义成功和失败的关键词（可以根据实际情况调整）
                success_keywords_in_url = ["finished", "result", "complete", "thank", "success", "aspx"]  # aspx也算一种跳转
                success_keywords_in_title = ["感谢", "完成", "成功", "提交成功", "谢谢"]
                success_keywords_in_page = ["提交成功", "感谢您", "问卷已提交", "已完成", "thank you", "completed",
                                            "submitted successfully", "您的回答已提交"]

                error_keywords_in_page = ["提交失败", "验证码错误", "必填项", "网络超时", "重新提交", "滑块验证失败",
                                          "frequencylimit", "error", "fail", "invalid", "请稍后重试", "系统繁忙",
                                          "不允许提交", "答题时间过短"]  # 增加更多错误提示

                submission_successful = False
                extracted_error_message = ""

                # 优先检查页面是否明确包含错误提示
                if any(keyword in page_source_lower for keyword in error_keywords_in_page):
                    submission_successful = False
                    # 尝试提取更具体的错误信息
                    try:
                        # 通用的错误提示区域class: tip_wrapper, alert_error, layui-layer-content
                        # 问卷星特定错误提示: div.field_answer_tip, div.div_error_msg
                        error_selectors = [
                            "//div[contains(@class,'tip_wrapper') and (contains(.,'失败') or contains(.,'错误') or contains(.,'验证'))]",
                            "//div[contains(@class,'alert_error') or contains(@class,'error_validator') or contains(@class,'wjx_error')]",
                            "//div[@class='layui-layer-content' and (contains(.,'失败') or contains(.,'错误') or contains(.,'验证') or contains(.,'不允许'))]",
                            "//div[contains(@class,'field_answer_tip') or contains(@class,'div_error_msg')]"
                        ]
                        for selector in error_selectors:
                            error_elements = self.driver.find_elements(By.XPATH, selector)
                            for err_el in error_elements:
                                if err_el.is_displayed() and err_el.text.strip():
                                    extracted_error_message = err_el.text.strip()[:150]  # 取前150字符
                                    break
                            if extracted_error_message: break
                    except:
                        pass  # 提取错误信息失败就算了

                    final_message_or_url = f"页面包含明确的错误或失败提示。"
                    if extracted_error_message:
                        final_message_or_url += f" 页面提示: {extracted_error_message}"
                    else:  # 如果没有提取到具体错误，但关键词匹配了，给个通用提示
                        final_message_or_url += f" (关键词匹配，但未提取到具体文本). URL: {final_url}"
                else:  # 如果没有明确的错误提示，再判断是否成功
                    url_changed_significantly = initial_url.split('?')[0].split('#')[0] != \
                                                final_url.split('?')[0].split('#')[0]
                    url_has_success_keyword = any(keyword in final_url.lower() for keyword in success_keywords_in_url)
                    title_has_success_keyword = any(keyword in final_title for keyword in success_keywords_in_title)
                    page_has_success_keyword = any(keyword in page_source_lower for keyword in success_keywords_in_page)

                    if url_changed_significantly and url_has_success_keyword:
                        submission_successful = True
                        final_message_or_url = f"成功提交，URL跳转至成功页: {final_url}"
                    elif title_has_success_keyword:
                        submission_successful = True
                        final_message_or_url = f"成功提交，页面标题为: '{self.driver.title}'. URL: {final_url}"
                    elif page_has_success_keyword:
                        submission_successful = True
                        final_message_or_url = f"成功提交，页面包含成功标识。URL: {final_url}"
                    # 如果URL显著变化，且新的URL不包含常见的错误指示（如login, error, code=) 也可能视为成功
                    elif url_changed_significantly and not any(err_key in final_url.lower() for err_key in
                                                               ["error", "fail", "login", "code=", "Error", "Fail"]):
                        submission_successful = True
                        final_message_or_url = f"提交后URL发生有意义变化: {final_url} (请人工复核是否真成功)"
                    else:
                        submission_successful = False
                        final_message_or_url = f"提交后状态未知或无明确成功标识。URL: {final_url}, 标题: '{self.driver.title}'"

                current_fill_success = submission_successful
                if current_fill_success:
                    self._emit_progress("success_once", f"线程 {self.worker_id}: {final_message_or_url}")
                else:
                    self._emit_progress("error", f"线程 {self.worker_id}: {final_message_or_url}")

            except InterruptedError:  # 用户中止
                final_message_or_url = f"线程 {self.worker_id}: 用户中止操作"
                self._emit_progress("info", final_message_or_url)
                self.is_running = False  # 确保 is_running 被设置为 False
            except TimeoutException as te:
                final_message_or_url = f"线程 {self.worker_id}: 操作超时: {str(te).splitlines()[0]}"  # 取第一行错误信息
                self._emit_progress("error", final_message_or_url)
            except Exception as e_run:  # 其他所有未知错误
                tb_str = traceback.format_exc()
                final_message_or_url = f"线程 {self.worker_id}: 执行过程中发生未知错误: {type(e_run).__name__} - {str(e_run)[:200]}\nTraceback: {tb_str.splitlines()[-3:]}"  # 包含部分堆栈
                self._emit_progress("error", final_message_or_url)
            finally:
                if self.driver:  # 确保每次填写尝试后都关闭浏览器
                    try:
                        self.driver.quit()
                    except Exception as quit_e:
                        self._emit_progress("warn", f"线程 {self.worker_id}: 关闭WebDriver时发生错误: {quit_e}")
                    self.driver = None  # 置为None，下次循环会重新初始化

                if current_fill_success: self.fills_completed_by_this_worker += 1
                self.single_fill_finished_signal.emit(self.worker_id, current_fill_success, final_message_or_url)

                # 检查是否应该结束worker的循环
                if not self.is_running or self.fills_completed_by_this_worker >= self.num_fills_to_complete_by_worker:
                    break  # 跳出主 while 循环

                # 如果还需要继续，则进行短暂休眠
                if self.is_running:
                    sleep_duration = random.uniform(3, 7)  # 两轮填写间的间隔
                    self._emit_progress("info",
                                        f"线程 {self.worker_id} 本次填写结束，休息 {sleep_duration:.1f} 秒后继续...")
                    for _ in range(int(sleep_duration * 10)):  # 分段休眠以响应中止
                        if not self.is_running: break
                        time.sleep(0.1)

        # Worker 循环结束后的最终报告
        if self.fills_completed_by_this_worker >= self.num_fills_to_complete_by_worker:
            self._emit_progress("info",
                                f"线程 {self.worker_id} 已完成全部分配的 {self.num_fills_to_complete_by_worker} 份问卷。")
        elif not self.is_running:  # 被外部中止
            self._emit_progress("info",
                                f"线程 {self.worker_id} 被中止，已完成 {self.fills_completed_by_this_worker}/{self.num_fills_to_complete_by_worker} 份。")
        else:  # 其他原因提前结束
            self._emit_progress("warn",
                                f"线程 {self.worker_id} 提前结束（可能因多次错误），已完成 {self.fills_completed_by_this_worker}/{self.num_fills_to_complete_by_worker} 份。")

        self.worker_completed_all_fills_signal.emit(self.worker_id)

    def stop_worker(self):
        self._emit_progress("info", f"线程 {self.worker_id} 接收到停止信号。")
        self.is_running = False

    def pause_worker(self):
        if self.is_running:  # 只有在运行时暂停才有意义
            self._emit_progress("info", f"线程 {self.worker_id} 已暂停。")
            self.is_paused = True

    def resume_worker(self):
        if self.is_running:  # 只有在运行时恢复才有意义
            self.is_paused = False
            self._emit_progress("info", f"线程 {self.worker_id} 已恢复。")

