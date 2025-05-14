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
            self._emit_progress("error", f"初始化EdgeDriver失败: {e}")
            return False

    def _emit_progress(self, msg_type, message):
        self.progress_signal.emit(self.worker_id, self.fills_completed_by_this_worker,
                                  self.num_fills_to_complete_by_worker, msg_type, message)

    def _generate_randomized_instructions(self, raw_configs_template):
        if not raw_configs_template:
            self._emit_progress("error", "_generate_randomized_instructions: 原始配置模板为空。")
            return None
        fill_instructions = []
        for q_template in raw_configs_template:
            q_id = q_template['id']
            q_topic_num = q_template['topic_num']
            q_type = q_template['type_code']
            options_parsed = q_template.get('options_parsed', [])
            instruction_base = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type}

            if q_type in ["1", "2"]:
                instruction = instruction_base.copy()
                instruction["action"] = "fill"
                instruction["text_answer"] = q_template.get("raw_text_input", "")
                fill_instructions.append(instruction)
            elif q_type == "8":
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
            elif q_type in ["3", "5", "7"]:
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
                    elif options_parsed:
                        selected_option_data = random.choice(options_parsed)
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select"
                        instruction["target_original_index"] = selected_option_data["original_index"]
                        fill_instructions.append(instruction)
            elif q_type == "4":
                raw_probs_str = q_template.get("raw_prob_input", "")
                if options_parsed:
                    try:
                        percentages = [int(p.strip()) for p in raw_probs_str.split(',')]
                        if len(percentages) != len(options_parsed):
                            self._emit_progress("warn", f"题目 {q_topic_num} 多选概率数量与选项不符，将随机选1-N个。")
                            num_to_select = random.randint(1, (len(options_parsed) + 1) // 2 if options_parsed else 1)
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
                        self._emit_progress("warn", f"题目 {q_topic_num} 多选概率配置错误，将随机选择1个。")
                        if options_parsed:
                            selected_option_data = random.choice(options_parsed)
                            multi_choice_instruction = instruction_base.copy()
                            multi_choice_instruction["action"] = "click"
                            multi_choice_instruction["target_original_index"] = selected_option_data["original_index"]
                            fill_instructions.append(multi_choice_instruction)
            elif q_type == "6":
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
                        elif sub_q_options_parsed:
                            selected_sub_q_opt_data = random.choice(sub_q_options_parsed)
                            matrix_sub_instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                                      "action": "matrix_click",
                                                      "sub_q_id_prefix": sub_q_config["sub_q_id_prefix"],
                                                      "sub_q_original_index": sub_q_config.get("sub_q_original_index"),
                                                      "target_original_index": selected_sub_q_opt_data[
                                                          "original_index"]}
                            fill_instructions.append(matrix_sub_instruction)
            elif q_type == "11":  # 排序题
                instruction = instruction_base.copy()
                instruction["action"] = "sort_random"
                # 排序题的选项（可排序项）也需要传递，以便在执行时使用
                instruction["sortable_options_parsed"] = options_parsed
                fill_instructions.append(instruction)
        if not fill_instructions and raw_configs_template:
            self._emit_progress("warn", "未能根据配置模板生成任何填写指令。")
        return fill_instructions

    def run(self):
        self._emit_progress("info", f"线程 {self.worker_id} 启动。目标份数: {self.num_fills_to_complete_by_worker}")
        while self.fills_completed_by_this_worker < self.num_fills_to_complete_by_worker and self.is_running:
            if not self._initialize_driver():
                self.single_fill_finished_signal.emit(self.worker_id, False, "驱动初始化失败")
                break
            self.fill_config_instructions = self._generate_randomized_instructions(
                self.user_raw_configurations_template)
            if not self.fill_config_instructions:
                self._emit_progress("error", "无法为此填写尝试生成指令，跳过本次填写。")
                time.sleep(1)
                self.single_fill_finished_signal.emit(self.worker_id, False, "指令生成失败")
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = None
                continue
            current_fill_success = False
            final_message_or_url = "未知原因失败"
            initial_url = self.url
            try:
                self._emit_progress("info", f"开始第 {self.fills_completed_by_this_worker + 1} 次填写尝试...")
                self.driver.get(initial_url)
                WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "divQuestion")))
                time.sleep(random.uniform(1.0, 2.5))
                for instruction_index, instruction in enumerate(self.fill_config_instructions):
                    while self.is_paused and self.is_running: time.sleep(0.1)
                    if not self.is_running: break
                    q_div_id = instruction['id']
                    q_topic_num = instruction['topic_num']
                    q_type_code = instruction['type_code']
                    action = instruction['action']
                    self._emit_progress("info",
                                        f"指令 {instruction_index + 1}/{len(self.fill_config_instructions)}: 处理题目 {q_topic_num} ({q_div_id}), 类型 {q_type_code}, 动作: {action}")
                    target_element_for_js_click = None
                    try:
                        q_element_xpath = f"//div[@id='{q_div_id}' and @topic='{q_topic_num}']"
                        q_element = WebDriverWait(self.driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, q_element_xpath)))
                        if action == "fill":
                            text_to_fill = instruction.get('text_answer', '')
                            input_css_selector = f"#{q_div_id} input[id='q{q_topic_num}'], #{q_div_id} textarea[id='q{q_topic_num}']"
                            input_element = WebDriverWait(q_element, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, input_css_selector)))
                            input_element.clear()
                            input_element.send_keys(text_to_fill)
                        elif action == "click":
                            opt_original_idx = instruction['target_original_index']
                            css_selector_option = ""
                            if q_type_code == "3" or q_type_code == "4":
                                css_selector_option = f"#{q_div_id} div.ui-controlgroup > div:nth-child({opt_original_idx})"
                            elif q_type_code == "5":
                                css_selector_option = f"#{q_div_id} div.scale-div ul > li:nth-child({opt_original_idx})"
                            if css_selector_option:
                                target_element = WebDriverWait(q_element, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector_option)))
                                target_element_for_js_click = target_element
                                target_element.click()
                        elif action == "dropdown_select":
                            opt_original_idx = instruction['target_original_index']
                            dropdown_container_id = f"select2-q{q_topic_num}-container"
                            container_element = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.ID, dropdown_container_id)))
                            container_element.click()
                            time.sleep(0.5)
                            option_xpath = f"//ul[@id='select2-q{q_topic_num}-results']/li[{opt_original_idx}]"
                            option_element_to_click = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.XPATH, option_xpath)))
                            target_element_for_js_click = option_element_to_click
                            option_element_to_click.click()
                        elif action == "matrix_click":
                            sub_q_id_prefix = instruction['sub_q_id_prefix']
                            opt_original_idx = instruction['target_original_index']
                            matrix_option_css = f"#{sub_q_id_prefix} > td:nth-child({opt_original_idx})"
                            target_element = WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, matrix_option_css)))
                            target_element_for_js_click = target_element
                            # 尝试滚动到元素使其在视图内，如果需要
                            # self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", target_element)
                            # time.sleep(0.1)
                            target_element.click()

                        # !!! 核心修改：排序题处理逻辑 !!!
                        elif action == "sort_random":
                            self._emit_progress("info", f"正在处理排序题 {q_topic_num}...")
                            # 排序题的ul元素通常是 div[@id='{q_div_id}'] 下的第一个ul
                            # 或者更精确地，class可能包含 "sortable" 或 "rank"
                            # 对于您提供的问卷，其ul class为 "sort_data"
                            sortable_list_container_xpath = f"//div[@id='{q_div_id}']/ul[contains(@class,'sort_data') or contains(@class,'sortable') or contains(@class,'rank')]"

                            try:
                                # 等待排序列表容器加载
                                sortable_list_element = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.XPATH, sortable_list_container_xpath))
                                )
                                # 获取所有可排序的li项，它们通常有 draggable="true" 属性
                                # 或者直接取ul下的所有li
                                sortable_items_xpath = f"{sortable_list_container_xpath}/li"
                                all_list_items = sortable_list_element.find_elements(By.XPATH,
                                                                                     "./li[@draggable='true']")
                                if not all_list_items:  # 如果没有 draggable='true'，尝试所有li
                                    all_list_items = sortable_list_element.find_elements(By.XPATH, "./li")

                                num_items = len(all_list_items)
                                if num_items > 1:  # 至少需要2个项才能排序
                                    self._emit_progress("info", f"排序题 {q_topic_num} 找到 {num_items} 个可排序项。")
                                    actions = ActionChains(self.driver)

                                    # 执行多次随机拖拽来打乱顺序
                                    # 拖拽次数可以是项目数的1到2倍，或者一个固定次数
                                    num_drags = num_items * random.randint(1, 2)
                                    if num_items <= 3: num_drags = num_items * 2  # 对于少量项目，多拖几次

                                    for _ in range(num_drags):
                                        if not self.is_running: break
                                        try:
                                            # 每次都重新获取最新的元素列表，因为DOM可能在拖拽后改变
                                            current_items = self.driver.find_elements(By.XPATH, sortable_items_xpath)
                                            if len(current_items) < 2: break  # 少于两个无法拖拽了

                                            source_idx = random.randrange(len(current_items))
                                            target_idx = random.randrange(len(current_items))
                                            if source_idx == target_idx:  # 如果源和目标相同，尝试换一个目标
                                                target_idx = (target_idx + 1) % len(current_items)

                                            source_element = current_items[source_idx]
                                            target_element = current_items[target_idx]

                                            # 确保元素在视口内并可交互
                                            self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);",
                                                                       source_element)
                                            time.sleep(0.1)  # 等待滚动

                                            self._emit_progress("info",
                                                                f"拖拽项 '{source_element.text[:20]}...' 到 '{target_element.text[:20]}...' 之前/之后")

                                            # Selenium 的 drag_and_drop 有时对复杂的JS控件效果不好
                                            # 尝试 click_and_hold, move_to_element, release
                                            actions.click_and_hold(source_element).pause(0.2) \
                                                .move_to_element(target_element).pause(0.2) \
                                                .release().perform()

                                            time.sleep(random.uniform(0.5, 1.0))  # 每次拖拽后等待JS更新DOM

                                        except StaleElementReferenceException:
                                            self._emit_progress("warn", f"排序项元素已过时，重新尝试获取。")
                                            continue  # DOM变化了，外层循环会重新获取
                                        except Exception as e_drag:
                                            self._emit_progress("error",
                                                                f"排序题 {q_topic_num} 拖拽时出错: {type(e_drag).__name__} - {e_drag}")
                                            break  # 如果拖拽内部出错，跳出拖拽循环
                                    self._emit_progress("info", f"排序题 {q_topic_num} 随机拖拽完成。")
                                else:
                                    self._emit_progress("info",
                                                        f"排序题 {q_topic_num} 项目数不足 ({num_items})，无需排序。")
                            except TimeoutException:
                                self._emit_progress("error", f"排序题 {q_topic_num} 列表容器未找到或超时。")
                            except Exception as e_sort_setup:
                                self._emit_progress("error", f"排序题 {q_topic_num} 设置时出错: {e_sort_setup}")

                        time.sleep(random.uniform(0.2, 0.5))
                    except ElementClickInterceptedException:
                        self._emit_progress("warn", f"题目 {q_topic_num} 点击被拦截，尝试JS点击...")
                        try:
                            if target_element_for_js_click:
                                self.driver.execute_script("arguments[0].click();", target_element_for_js_click)
                                time.sleep(0.3)
                            else:
                                self._emit_progress("error", f"JS点击失败：未找到备用目标元素。")
                        except Exception as js_e:
                            self._emit_progress("error", f"JS点击也失败: {js_e}")
                    except TimeoutException:
                        self._emit_progress("error", f"操作超时: 题目 {q_topic_num}, ID {q_div_id}, 动作 {action}。")
                    except NoSuchElementException:
                        self._emit_progress("error", f"元素未找到: 题目 {q_topic_num}, ID {q_div_id}, 动作 {action}。")
                    except Exception as e:
                        self._emit_progress("error", f"处理题目 {q_topic_num} 时发生错误: {type(e).__name__} - {e}")

                # --- 后续的翻页、提交、成功/失败判断逻辑与您之前提供的版本保持一致 ---
                # ... (为了简洁，此处省略，请使用您之前最新的那部分代码) ...
                if not self.is_running: raise InterruptedError("用户中止操作")
                try:
                    next_page_button = self.driver.find_element(By.ID, "divNextPage")
                    if next_page_button.is_displayed() and next_page_button.is_enabled():
                        self._emit_progress("info", "所有已知指令完成，但发现“下一页”按钮，点击它...")
                        next_page_button.click()
                        WebDriverWait(self.driver, 15).until(EC.staleness_of(next_page_button))
                        time.sleep(random.uniform(1.0, 2.0))
                except NoSuchElementException:
                    pass
                self._emit_progress("info", "所有指令执行完毕，尝试提交问卷...")
                submit_button_xpath = '//*[@id="ctlNext"]'
                submit_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, submit_button_xpath))
                )
                submit_button.click()
                time.sleep(random.uniform(0.5, 1.0))
                try:
                    confirm_button_xpath = "//div[contains(@class,'layui-layer-btn')]/a[normalize-space()='确定' or normalize-space()='确认']"
                    confirm_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, confirm_button_xpath))
                    )
                    confirm_button.click()
                    self._emit_progress("info", "点击了提交确认弹窗。")
                    time.sleep(random.uniform(0.8, 1.2))
                except TimeoutException:
                    self._emit_progress("info", "未找到或超时等待提交确认弹窗。")
                except NoSuchElementException:
                    pass
                try:
                    verify_button_id = "SM_BTN_1"
                    verify_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.ID, verify_button_id))
                    )
                    verify_button.click()
                    self._emit_progress("info", "点击了智能验证按钮。")
                    time.sleep(random.uniform(2.5, 4.0))
                except TimeoutException:
                    self._emit_progress("info", "未找到或超时等待智能验证按钮。")
                except NoSuchElementException:
                    pass
                try:
                    slider_text_span_xpath = '//*[@id="nc_1__scale_text"]/span[contains(text(),"请按住滑块")]'
                    WebDriverWait(self.driver, 5).until(
                        EC.visibility_of_element_located((By.XPATH, slider_text_span_xpath))
                    )
                    slider_button = self.driver.find_element(By.XPATH, '//*[@id="nc_1_n1z"]')
                    self._emit_progress("captcha", "检测到滑块验证，尝试拖动...")
                    drag_distance = random.randint(258, 270)
                    actions = ActionChains(self.driver)
                    actions.click_and_hold(slider_button)
                    num_segments = random.randint(3, 5)
                    total_moved = 0
                    for i in range(num_segments):
                        if total_moved >= drag_distance: break
                        if i == num_segments - 1:
                            segment_dist = drag_distance - total_moved + random.randint(5, 15)
                        else:
                            segment_dist = drag_distance / num_segments + random.randint(-10, 10)
                        segment_dist = max(1, int(segment_dist))
                        if total_moved + segment_dist > drag_distance * 1.2: segment_dist = drag_distance * 1.2 - total_moved
                        if segment_dist <= 0: continue
                        actions.move_by_offset(segment_dist, random.randint(-6, 6))
                        actions.pause(random.uniform(0.03, (0.2 if i < num_segments - 1 else 0.08)))
                        total_moved += segment_dist
                    actions.release().perform()
                    self._emit_progress("info", f"滑块拖动完成，总距离约: {total_moved}px。")
                    time.sleep(random.uniform(2.0, 3.5))
                except TimeoutException:
                    self._emit_progress("info", "未检测到滑块验证（或超时）。")
                except NoSuchElementException:
                    pass
                except Exception as e_slider:
                    self._emit_progress("error", f"滑块验证时出错: {type(e_slider).__name__} - {e_slider}")
                self._emit_progress("info", "等待提交结果...")
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.any_of(
                            EC.url_contains("finished"), EC.url_contains("result"), EC.url_contains("completed"),
                            EC.presence_of_element_located((By.XPATH,
                                                            "//*[contains(text(),'提交成功') or contains(text(),'感谢您') or contains(text(),'已完成')]")),
                            EC.presence_of_element_located(
                                (By.XPATH, "//*[contains(text(),'提交失败') or contains(text(),'错误')]"))
                        )
                    )
                except TimeoutException:
                    self._emit_progress("warn", "等待最终结果超时，将基于当前页面状态判断。")
                final_url = self.driver.current_url
                final_title = self.driver.title.lower() if self.driver.title else ""
                page_source_lower = ""
                try:
                    page_source_lower = self.driver.page_source.lower()
                except:
                    self._emit_progress("warn", "无法获取最终页面的 page_source。")
                success_keywords_in_url = ["finished", "result", "complete", "thank", "success"]
                success_keywords_in_title = ["感谢", "完成", "成功", "提交成功", "谢谢"]
                success_keywords_in_page = ["提交成功", "感谢您", "问卷已提交", "已完成", "thank you", "completed",
                                            "submitted successfully"]
                error_keywords_in_page = ["提交失败", "验证码错误", "必填项", "网络超时", "重新提交", "滑块验证失败",
                                          "frequencylimit", "error", "fail", "invalid", "请稍后重试", "系统繁忙"]
                submission_successful = False
                if any(keyword in page_source_lower for keyword in error_keywords_in_page):
                    submission_successful = False
                    fail_reason = "页面包含明确的错误或失败提示。"
                    try:
                        error_elements = self.driver.find_elements(By.XPATH,
                                                                   "//*[self::p or self::span or self::div][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '失败') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '错误') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '验证')]")
                        if error_elements:
                            for err_el in error_elements:
                                if err_el.is_displayed() and err_el.text.strip():
                                    fail_reason += " 页面提示: " + err_el.text.strip()[:100]
                                    break
                    except:
                        pass
                    final_message_or_url = f"{fail_reason} 当前URL: {final_url}"
                else:
                    url_changed_significantly = initial_url.split('?')[0] != final_url.split('?')[0]
                    url_has_success_keyword = any(keyword in final_url.lower() for keyword in success_keywords_in_url)
                    title_has_success_keyword = any(keyword in final_title for keyword in success_keywords_in_title)
                    page_has_success_keyword = any(keyword in page_source_lower for keyword in success_keywords_in_page)
                    if url_changed_significantly and url_has_success_keyword:
                        submission_successful = True
                        final_message_or_url = f"成功提交，URL跳转至成功页: {final_url}"
                    elif title_has_success_keyword:
                        submission_successful = True
                        final_message_or_url = f"成功提交，页面标题为: '{self.driver.title}'。URL: {final_url}"
                    elif page_has_success_keyword:
                        submission_successful = True
                        final_message_or_url = f"成功提交，页面包含成功标识。URL: {final_url}"
                    elif url_changed_significantly and not any(
                            keyword in final_url.lower() for keyword in ["error", "fail", "login", "code="]):
                        submission_successful = True
                        final_message_or_url = f"提交后URL发生变化且无明显错误: {final_url} (请人工复核是否真成功)"
                    else:
                        submission_successful = False
                        final_message_or_url = f"提交后状态未知或无明确成功标识。URL: {final_url}, 标题: '{self.driver.title}'"
                current_fill_success = submission_successful
                if current_fill_success:
                    self._emit_progress("success_once", final_message_or_url)
                else:
                    self._emit_progress("error", final_message_or_url)
            except InterruptedError:
                final_message_or_url = "用户中止操作"
                self._emit_progress("info", final_message_or_url)
                self.is_running = False
            except TimeoutException as te:
                final_message_or_url = f"操作超时: {te}"
                self._emit_progress("error", final_message_or_url)
            except Exception as e:
                final_message_or_url = f"执行过程中发生未知错误: {type(e).__name__} - {e}"
                self._emit_progress("error", final_message_or_url)
            finally:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception as quit_e:
                        self._emit_progress("warn", f"关闭WebDriver时发生错误: {quit_e}")
                    self.driver = None
                if current_fill_success: self.fills_completed_by_this_worker += 1
                self.single_fill_finished_signal.emit(self.worker_id, current_fill_success, final_message_or_url)
                if not self.is_running or self.fills_completed_by_this_worker >= self.num_fills_to_complete_by_worker: break
                if self.is_running:
                    sleep_duration = random.uniform(3, 7)
                    self._emit_progress("info",
                                        f"线程 {self.worker_id} 本次填写结束，休息 {sleep_duration:.1f} 秒后继续...")
                    time.sleep(sleep_duration)

        if self.fills_completed_by_this_worker >= self.num_fills_to_complete_by_worker:
            self._emit_progress("info",
                                f"线程 {self.worker_id} 已完成全部分配的 {self.num_fills_to_complete_by_worker} 份问卷。")
        elif not self.is_running:
            self._emit_progress("info",
                                f"线程 {self.worker_id} 被中止，已完成 {self.fills_completed_by_this_worker}/{self.num_fills_to_complete_by_worker} 份。")
        else:
            self._emit_progress("warn",
                                f"线程 {self.worker_id} 提前结束，已完成 {self.fills_completed_by_this_worker}/{self.num_fills_to_complete_by_worker} 份。原因可能在先前日志。")
        self.worker_completed_all_fills_signal.emit(self.worker_id)

    def stop_worker(self):
        self._emit_progress("info", f"线程 {self.worker_id} 接收到停止信号。")
        self.is_running = False

    def pause_worker(self):
        if self.is_running:
            self._emit_progress("info", f"线程 {self.worker_id} 已暂停。")
            self.is_paused = True

    def resume_worker(self):
        if self.is_running:
            self.is_paused = False
            self._emit_progress("info", f"线程 {self.worker_id} 已恢复。")

