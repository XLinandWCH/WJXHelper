# filler_worker.py
import time
import random
import traceback
import numpy  # 确保导入，用于随机选择、概率计算等
import os
import tempfile
import shutil
import re # 导入正则表达式模块，虽然主要解析在setup widget，worker里有时也可能用到

from PyQt5.QtCore import QThread, pyqtSignal, QMutex # 导入 QMutex 用于线程安全

# Selenium 相关的导入
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (NoSuchElementException, TimeoutException,
                                        ElementClickInterceptedException, StaleElementReferenceException,
                                        WebDriverException)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 导入工具函数，用于权重/概率解析和计算
from utils import parse_weights_from_string, calculate_choice_from_weights, calculate_multiple_choices_from_percentages

# 定义一些常量，虽然主要解析在setup widget完成，worker知道这些格式类型字符串即可
# 随机填空的分隔符（worker只在处理other text时可能用到）
_FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM = "||"
# 顺序填空的格式类型标记字符串 (worker需要知道这个字符串来判断格式)
_FILL_IN_BLANK_FORMAT_SEQUENTIAL = "sequential"
# 随机填空的格式类型标记字符串
_FILL_IN_BLANK_FORMAT_RANDOM = "random"


class FillerWorker(QThread):
    """
    负责在一个独立线程中驱动浏览器填写问卷的工作类。
    每个Worker实例负责完成指定数量的问卷填写任务。
    """
    # 定义信号，用于与主UI线程通信，报告进度、完成状态和消息
    # worker_id, 已完成份数(本线程), 目标份数(本线程), 消息类型(info,warn,error等), 消息内容
    progress_signal = pyqtSignal(int, int, int, str, str)
    # worker_id, 本次填写是否成功, 消息/最终URL
    single_fill_finished_signal = pyqtSignal(int, bool, str)
    # worker_id
    worker_completed_all_fills_signal = pyqtSignal(int)

    # 增加 shared_sequential_indices 和 sequential_indices_mutex 参数
    def __init__(self, worker_id, url, user_raw_configurations_template,
                 num_fills_for_this_worker, total_target_fills,
                 browser_type="edge",
                 driver_executable_path=None,
                 headless=True, proxy=None,
                 base_user_data_dir_path=None,
                 shared_sequential_indices=None,  # 新增参数：共享的顺序索引字典
                 sequential_indices_mutex=None):   # 新增参数：共享的互斥锁
        """
        初始化工作线程。
        :param worker_id: 工作线程的唯一ID。
        :param url: 待填写问卷的URL。
        :param user_raw_configurations_template: 从问卷设置界面获取的用户配置模板。
        :param num_fills_for_this_worker: 本线程需要完成的填写份数。
        :param total_target_fills: 所有线程的总填写目标份数（用于UI全局进度显示）。
        :param browser_type: 使用的浏览器类型（"edge", "chrome", "firefox"）。
        :param driver_executable_path: 浏览器驱动的可执行文件路径。
        :param headless: 是否以无头模式运行。
        :param proxy: 代理地址（格式如 "IP:PORT"）。
        :param base_user_data_dir_path: 用户数据目录的基础路径。
        :param shared_sequential_indices: 所有Worker共享的顺序填空索引字典 {q_div_id: current_index}。
        :param sequential_indices_mutex: 访问共享顺序填空索引字典时使用的互斥锁 (QMutex)。
        """
        super().__init__()
        # 初始化工作线程的各项属性
        self.worker_id = worker_id
        self.url = url
        self.user_raw_configurations_template = user_raw_configurations_template
        self.num_fills_to_complete_by_worker = num_fills_for_this_worker
        self.total_target_fills_all_workers = total_target_fills
        self.fills_completed_by_this_worker = 0
        # 运行状态控制标志
        self.is_running = True
        self.is_paused = False

        # 浏览器配置
        self.browser_type = browser_type.lower()
        self.driver_executable_path = driver_executable_path
        self.headless = headless
        self.proxy = proxy
        # 用户数据目录的基础路径
        self.base_user_data_dir_path = base_user_data_dir_path
        # 本次运行实际使用的用户数据目录 (每个worker一个独立目录)
        self.actual_user_data_dir = None

        # 存储为本次填写生成的具体指令列表
        self.fill_config_instructions = []
        # WebDriver 实例
        self.driver = None

        # --- 修改：用于追踪顺序填空题的当前索引 ---
        # 这个状态现在是共享的，由外部传入并保护
        # _sequential_fill_indices 不再是 Worker 实例属性，而是从外部传入共享的引用
        self._shared_sequential_indices = shared_sequential_indices  # 保存共享字典的引用
        self._sequential_indices_mutex = sequential_indices_mutex    # 保存共享互斥锁的引用


    def _initialize_driver(self):
        """
        初始化 WebDriver 实例。根据配置的浏览器类型、驱动路径、无头模式、代理和用户数据目录进行设置。
        :return: 初始化成功返回 True，失败返回 False。
        """
        try:
            # 定义常用User-Agent和CDP脚本用于反爬
            common_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36 Edg/100.0.1185.50"
            # CDP脚本用于修改 navigator 属性，使其看起来不像自动化工具
            common_cdp_script = """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """

            # 设置用户数据目录，用于保持session/cookie/缓存等（仅限Chromium内核浏览器）
            if self.browser_type in ["edge", "chrome"]:
                # 如果指定了基础路径且存在，则在该基础路径下创建worker专属子目录
                if self.base_user_data_dir_path and os.path.isdir(self.base_user_data_dir_path):
                    self.actual_user_data_dir = os.path.join(self.base_user_data_dir_path,
                                                             f"profile_w{self.worker_id}_{random.randint(10000, 99999)}")
                else: # 否则在系统临时目录下创建
                    self.actual_user_data_dir = os.path.join(tempfile.gettempdir(),
                                                             f"wjx_filler_profile_w{self.worker_id}_{random.randint(10000, 99999)}")
                # 确保目录存在，如果同名路径是文件则删除
                if os.path.exists(self.actual_user_data_dir) and not os.path.isdir(self.actual_user_data_dir):
                    try:
                        os.remove(self.actual_user_data_dir)
                    except OSError:
                        pass
                os.makedirs(self.actual_user_data_dir, exist_ok=True)
                self._emit_progress("debug", f"线程 {self.worker_id}: 使用用户数据目录: {self.actual_user_data_dir}")

            # 设置驱动服务（如果指定了驱动路径）
            service = None
            if self.driver_executable_path and os.path.isfile(self.driver_executable_path):
                if self.browser_type == "edge":
                    service = EdgeService(executable_path=self.driver_executable_path)
                elif self.browser_type == "chrome":
                    service = ChromeService(executable_path=self.driver_executable_path)
                elif self.browser_type == "firefox":
                    service = FirefoxService(executable_path=self.driver_executable_path)
                else: # 不支持的浏览器类型
                    self._emit_progress("error",
                                        f"线程 {self.worker_id}: 不支持的浏览器类型 '{self.browser_type}'"); return False
            elif self.driver_executable_path: # 如果只提供了文件名，Selenium会尝试从系统PATH中查找
                 # 这里保留原逻辑，但实际上可以更精确地判断driver_executable_path是否为绝对路径
                 # 不过Selenium内部已经做了查找PATH的逻辑
                if self.browser_type == "edge":
                    service = EdgeService(executable_path=self.driver_executable_path)
                elif self.browser_type == "chrome":
                    service = ChromeService(executable_path=self.driver_executable_path)
                elif self.browser_type == "firefox":
                    service = FirefoxService(executable_path=self.driver_executable_path)


            # 配置并创建浏览器实例
            if self.browser_type == "edge":
                edge_options = EdgeOptions();
                edge_options.use_chromium = True # 确保使用Chromium内核Edge
                # 设置无头模式和GPU禁用
                if self.headless: edge_options.add_argument("--headless"); edge_options.add_argument("--disable-gpu")
                # 设置代理
                if self.proxy: edge_options.add_argument(f"--proxy-server={self.proxy}")
                # 其他常用选项
                edge_options.add_argument("--no-sandbox"); # 禁用沙箱（在某些环境下需要）
                edge_options.add_argument("--disable-dev-shm-usage") # 解决Docker等环境下的 /dev/shm 问题
                # 反爬虫选项
                edge_options.add_experimental_option("excludeSwitches", ["enable-automation"]) # 排除自动化控制标志
                edge_options.add_experimental_option('useAutomationExtension', False) # 禁用自动化扩展
                edge_options.add_argument('--disable-blink-features=AutomationControlled') # 禁用 Blink 特性 AutomationControlled
                edge_options.add_argument(f"user-agent={common_user_agent}") # 设置User-Agent
                # 用户数据目录
                if self.actual_user_data_dir: edge_options.add_argument(f"--user-data-dir={self.actual_user_data_dir}")
                # 创建Edge WebDriver实例
                self.driver = webdriver.Edge(service=service, options=edge_options) if service else webdriver.Edge(
                    options=edge_options)
            elif self.browser_type == "chrome":
                # Chrome配置类似Edge
                chrome_options = ChromeOptions()
                if self.headless: chrome_options.add_argument("--headless"); chrome_options.add_argument(
                    "--disable-gpu")
                if self.proxy: chrome_options.add_argument(f"--proxy-server={self.proxy}")
                chrome_options.add_argument("--no-sandbox");
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument(f"user-agent={common_user_agent}")
                if self.actual_user_data_dir: chrome_options.add_argument(
                    f"--user-data-dir={self.actual_user_data_dir}")
                # 创建Chrome WebDriver实例
                self.driver = webdriver.Chrome(service=service,
                                               options=chrome_options) if service else webdriver.Chrome(
                    options=chrome_options)
            elif self.browser_type == "firefox":
                # Firefox配置
                firefox_options = FirefoxOptions()
                if self.headless: firefox_options.add_argument("--headless")
                # Firefox代理设置方式不同
                if self.proxy:
                    firefox_options.set_preference("network.proxy.type", 1) # 手动代理
                    proxy_host, proxy_port = self.proxy.split(":")
                    firefox_options.set_preference("network.proxy.http", proxy_host); # HTTP代理
                    firefox_options.set_preference("network.proxy.http_port", int(proxy_port))
                    firefox_options.set_preference("network.proxy.ssl", proxy_host); # HTTPS代理
                    firefox_options.set_preference("network.proxy.ssl_port", int(proxy_port))
                # 反爬虫选项
                firefox_options.set_preference("dom.webdriver.enabled", False) # 禁用 navigator.webdriver
                firefox_options.set_preference('useAutomationExtension', False) # 禁用自动化扩展
                firefox_options.profile.set_preference("general.useragent.override", common_user_agent) # 设置User-Agent
                # 创建Firefox WebDriver实例
                self.driver = webdriver.Firefox(service=service,
                                                options=firefox_options) if service else webdriver.Firefox(
                    options=firefox_options)
            else:
                # 不支持的浏览器类型，发送错误信号
                self._emit_progress("error",
                                    f"线程 {self.worker_id}: 初始化时遇到不支持的浏览器类型 '{self.browser_type}'"); return False

            # 设置页面加载和元素查找的超时时间
            self.driver.set_page_load_timeout(45); # 页面加载最长等待45秒
            self.driver.implicitly_wait(8) # 元素隐式等待8秒
            # 执行CDP脚本（仅限Chromium内核浏览器）
            if self.browser_type in ["edge", "chrome"] and self.driver:
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": common_cdp_script})
            return True # 初始化成功
        except WebDriverException as wde: # 捕获 WebDriver 相关的异常
            error_msg = (f"线程 {self.worker_id}: 初始化 {self.browser_type.capitalize()} Driver 失败 (WebDriverException)。\n"
                         f"请确保驱动程序版本与浏览器匹配，并在“程序设置”中指定正确路径或将其添加到系统PATH。\n"
                         f"尝试路径: {self.driver_executable_path if self.driver_executable_path else '系统PATH'}\n"
                         f"具体错误: {str(wde).splitlines()[0]}") # 提取错误的第一行
            self._emit_progress("error", error_msg);
            self._cleanup_user_data_dir(); # 清理可能创建的用户数据目录
            return False
        except Exception as e: # 捕获其他初始化错误
            error_msg = (f"线程 {self.worker_id}: 初始化 {self.browser_type.capitalize()} Driver 时发生未知错误。\n"
                         f"尝试路径: {self.driver_executable_path if self.driver_executable_path else '系统PATH'}\n"
                         f"具体错误: {type(e).__name__} - {e}")
            self._emit_progress("error", error_msg);
            self._cleanup_user_data_dir();
            return False

    def _cleanup_user_data_dir(self):
        """
        清理 worker 创建的临时用户数据目录。
        """
        if self.actual_user_data_dir and os.path.exists(self.actual_user_data_dir):
            try:
                # 只有当 driver 已经关闭时才清理，否则可能正在被使用
                if self.driver is None:
                    shutil.rmtree(self.actual_user_data_dir, ignore_errors=True)
                    self._emit_progress("debug",
                                        f"线程 {self.worker_id}: 已清理用户数据目录 {self.actual_user_data_dir}")
                else:
                    # 这种情况通常不发生，除非清理逻辑被在 driver.quit() 之前调用
                    self._emit_progress("warn",
                                        f"线程 {self.worker_id}: WebDriver仍在运行，未清理用户数据目录 {self.actual_user_data_dir}")
            except Exception as e_cleanup_parser: # 捕获清理时的错误
                self._emit_progress("warn",
                                    f"线程 {self.worker_id}: 清理用户数据目录 {self.actual_user_data_dir} 失败: {e_cleanup_parser}")
        self.actual_user_data_dir = None # 清空目录路径引用

    def _emit_progress(self, msg_type, message):
        """
        发射进度信号，将消息传递给UI线程更新日志和状态。
        :param msg_type: 消息类型 (如 "info", "warn", "error", "success_once", "captcha", "debug")。
        :param message: 消息内容字符串。
        """
        self.progress_signal.emit(self.worker_id, self.fills_completed_by_this_worker,
                                  self.num_fills_to_complete_by_worker, msg_type, message)

    def _generate_randomized_instructions(self, raw_configs_template):
        """
        根据用户配置模板生成本次填写尝试的具体操作指令列表。
        这个方法只负责生成“执行计划”，不实际执行。
        对于填空题，指令会包含答案列表和填写格式，实际选择答案在 run 方法中执行。
        :param raw_configs_template: 用户配置模板列表。
        :return: 生成的指令列表，失败返回 None。
        """
        if not raw_configs_template:
            self._emit_progress("error", f"线程 {self.worker_id}: _generate_randomized_instructions: 原始配置模板为空。")
            return None

        fill_instructions = [] # 存储生成的指令

        for q_template in raw_configs_template:
            # 提取模板中的问题信息
            q_id = q_template['id'];
            q_topic_num = q_template['topic_num'];
            q_type = q_template['type_code']
            # 获取解析后的选项数据（包含“其他”项的配置）
            options_parsed = q_template.get('options_parsed', [])
            # 构建指令的基础结构
            instruction_base = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type}

            # --- 处理填空题/多行填空题 (类型 1, 2) ---
            if q_type in ["1", "2"]:
                instruction = instruction_base.copy();
                instruction["action"] = "fill" # 操作是填充文本框
                # 从模板中获取解析后的答案列表和填写格式，直接存储到指令中
                instruction["text_answers_list"] = q_template.get("text_answers_list", [""])
                instruction["fill_format"] = q_template.get("fill_format", _FILL_IN_BLANK_FORMAT_RANDOM) # 默认随机格式

                # 对于填空题，指令只需包含答案列表和格式，实际选择/获取答案在 run 方法中进行
                fill_instructions.append(instruction)
            # --- 填空题处理结束 ---

            elif q_type == "8":  # 滑块题
                instruction = instruction_base.copy();
                instruction["action"] = "fill"
                raw_slider_text = q_template.get("raw_slider_input", "50").strip()
                try:
                    # 解析滑块配置字符串
                    if ':' in raw_slider_text and ',' in raw_slider_text.split(':')[0]:
                        # 支持 "值1,值2,...:权重1,权重2,..." 格式
                        values_str, weights_str = raw_slider_text.split(':')
                        values = [int(v.strip()) for v in values_str.split(',')]
                        weights_list = [int(w.strip()) for w in weights_str.split(',')]
                        # 根据权重选择一个值
                        chosen_value_idx = calculate_choice_from_weights(weights_list)
                        instruction["text_answer"] = str(values[chosen_value_idx]) if len(values) == len(weights_list) and sum(weights_list) > 0 and chosen_value_idx != -1 else (
                            str(values[0]) if values else "50") # 容错处理
                    elif ',' in raw_slider_text:
                        # 支持 "值1,值2,..." 格式 (等权重随机)
                        values = [int(v.strip()) for v in raw_slider_text.split(',')];
                        instruction["text_answer"] = str(random.choice(values)) if values else "50"
                    else:
                        # 支持单个整数值
                        instruction["text_answer"] = str(int(raw_slider_text))
                except: # 解析失败则使用默认值
                    instruction["text_answer"] = "50"
                fill_instructions.append(instruction)
            elif q_type in ["3", "5", "7"]:  # 单选题, 量表题, 下拉选择题
                instruction = instruction_base.copy();
                raw_weights_str = q_template.get("raw_weight_input", "")
                if options_parsed:
                    # 解析权重字符串，获取数字权重列表
                    weights = parse_weights_from_string(raw_weights_str, len(options_parsed));
                    # 根据权重选择一个选项的索引
                    chosen_option_idx_in_list = calculate_choice_from_weights(weights)
                    # 获取被选中的选项数据
                    selected_option_data = options_parsed[
                        chosen_option_idx_in_list] if chosen_option_idx_in_list != -1 else random.choice(options_parsed) # 容错处理，如果选择失败则随机选一个

                    # 设置操作类型和目标选项的原始索引
                    instruction["action"] = "click" if q_type != "7" else "dropdown_select";
                    instruction["target_original_index"] = selected_option_data["original_index"]

                    # 如果被选中的是“其他”选项，并且配置了自定义文本
                    if selected_option_data.get("is_other_specify") and \
                            selected_option_data.get("enable_other_text_input", False) and \
                            q_type in ["3", "5"]: # 目前仅支持单选/量表题的“其他”文本
                        raw_texts_for_other = selected_option_data.get("raw_other_text_input", "")
                        if raw_texts_for_other:
                            # 按||分隔自定义文本，随机选择一个
                            possible_other_texts = [ans.strip() for ans in
                                                    raw_texts_for_other.split(_FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM) if
                                                    ans.strip()]
                            if possible_other_texts:
                                instruction["other_text_to_fill"] = random.choice(possible_other_texts)
                                instruction["requires_other_text_fill"] = True # 标记需要填写“其他”文本
                    fill_instructions.append(instruction)
            elif q_type == "4":  # 多选题
                raw_probs_str = q_template.get("raw_prob_input", "");
                if options_parsed:
                    try:
                        # 解析概率字符串，获取数字概率列表
                        percentages = [int(p.strip()) for p in raw_probs_str.split(',') if p.strip().isdigit()] # 过滤非数字项
                        if len(percentages) != len(options_parsed): raise ValueError("Mismatch count")
                        # 根据概率列表计算被选中的选项索引列表
                        selected_indices = calculate_multiple_choices_from_percentages(percentages)
                    except: # 解析失败或数量不匹配，则随机选择一定数量的选项
                        self._emit_progress("warn",
                                            f"线程 {self.worker_id}: 题 {q_topic_num} 多选概率配置错误/不匹配，随机选。")
                        num_to_select = random.randint(1, max(1, len(options_parsed) // 2)); # 随机选择1到选项数一半的数量
                        selected_options_data_list = random.sample(options_parsed,
                                                                   min(num_to_select, len(options_parsed))) # 随机抽取选项数据
                        selected_indices = [options_parsed.index(opt) for opt in selected_options_data_list if
                                            opt in options_parsed] # 获取被抽中选项在原始列表中的索引

                    # 为每个被选中的选项生成一个点击指令
                    for selected_idx in selected_indices:
                        multi_choice_instruction = instruction_base.copy();
                        selected_option_data_for_multi = options_parsed[selected_idx]
                        multi_choice_instruction["action"] = "click"
                        multi_choice_instruction["target_original_index"] = selected_option_data_for_multi[
                            "original_index"]

                        # 如果被选中的是“其他”选项，并且配置了自定义文本
                        if selected_option_data_for_multi.get("is_other_specify") and \
                                selected_option_data_for_multi.get("enable_other_text_input", False):
                            raw_texts_for_other = selected_option_data_for_multi.get("raw_other_text_input", "")
                            if raw_texts_for_other:
                                # 按||分隔自定义文本，随机选择一个
                                possible_other_texts = [ans.strip() for ans in
                                                        raw_texts_for_other.split(_FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM)
                                                        if ans.strip()]
                                if possible_other_texts:
                                    multi_choice_instruction["other_text_to_fill"] = random.choice(possible_other_texts)
                                    multi_choice_instruction["requires_other_text_fill"] = True # 标记需要填写“其他”文本
                        fill_instructions.append(multi_choice_instruction) # 添加指令
            elif q_type == "6":  # 矩阵题
                sub_questions_raw_configs = q_template.get("sub_questions_raw_configs", [])
                for sub_q_config in sub_questions_raw_configs:
                    sub_q_options_parsed = sub_q_config.get("sub_q_options_parsed", []);
                    raw_sub_q_weights_str = sub_q_config.get("raw_weight_input", "")
                    if sub_q_options_parsed:
                        # 解析子问题权重，获取数字权重列表
                        sub_q_weights = parse_weights_from_string(raw_sub_q_weights_str, len(sub_q_options_parsed));
                        # 根据权重选择一个子问题选项的索引
                        chosen_sub_q_opt_idx = calculate_choice_from_weights(sub_q_weights)
                        # 获取被选中的子问题选项数据
                        selected_sub_q_opt_data = sub_q_options_parsed[
                            chosen_sub_q_opt_idx] if chosen_sub_q_opt_idx != -1 else random.choice(sub_q_options_parsed) # 容错处理

                        # 构建矩阵子问题点击指令
                        matrix_sub_instruction = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type,
                                                  "action": "matrix_click",
                                                  "sub_q_id_prefix": sub_q_config["sub_q_id_prefix"], # 子问题行元素的ID前缀
                                                  "sub_q_original_index": sub_q_config.get("sub_q_original_index"), # 子问题在列表中的原始索引
                                                  "target_original_index": selected_sub_q_opt_data["original_index"]} # 被选中的子问题选项的原始索引
                        fill_instructions.append(matrix_sub_instruction) # 添加指令
            elif q_type == "11":  # 排序题
                instruction = instruction_base.copy();
                instruction["action"] = "sort_random"; # 操作是随机排序
                # 存储解析到的排序项数据
                instruction["sortable_options_parsed"] = options_parsed  # options_parsed comes from q_template
                fill_instructions.append(instruction)

        # 如果没有生成任何填写指令，发送警告
        if not fill_instructions and raw_configs_template: self._emit_progress("warn",
                                                                               f"线程 {self.worker_id}: 未能根据配置模板生成任何填写指令。")
        return fill_instructions # 返回生成的指令列表

    def run(self):
        """
        工作线程的主执行循环，负责多次填写问卷。
        """
        self._emit_progress("info",
                            f"线程 {self.worker_id} ({self.browser_type}) 启动。目标份数: {self.num_fills_to_complete_by_worker}")

        # 外层循环：控制本线程要完成的填写份数
        while self.fills_completed_by_this_worker < self.num_fills_to_complete_by_worker and self.is_running:
            # 初始化 WebDriver
            if not self._initialize_driver():
                # Driver 初始化失败，无法继续，退出循环
                # 在 _initialize_driver 中已经发出了错误信号和清理了目录
                break # 退出主循环

            # 为本次填写生成具体的操作指令
            self.fill_config_instructions = self._generate_randomized_instructions(
                self.user_raw_configurations_template)

            # 如果指令生成失败，跳过本次填写
            if not self.fill_config_instructions:
                self._emit_progress("error", f"线程 {self.worker_id}: 无法为此填写尝试生成指令，跳过本次填写。")
                # 发射单次填写完成信号（失败）
                self.single_fill_finished_signal.emit(self.worker_id, False, f"线程 {self.worker_id}: 指令生成失败")
                # 关闭并清理 driver
                if self.driver:
                    try:
                        self.driver.quit()
                    except: # 忽略关闭时的错误
                        pass
                    self.driver = None
                self._cleanup_user_data_dir(); # 确保清理用户数据目录
                # 短暂休息后继续尝试下一份
                time.sleep(random.uniform(1, 3));
                continue # 继续外层循环，尝试下一份填写

            # 标记本次填写是否成功
            current_fill_success = False;
            final_message_or_url = "未知原因失败";
            initial_url = self.url # 保存初始URL用于对比判断提交结果

            try:
                self._emit_progress("info",
                                    f"线程 {self.worker_id}: 开始第 {self.fills_completed_by_this_worker + 1} 次填写...")
                # 打开问卷URL
                self.driver.get(initial_url)
                # 等待问卷核心区域加载，判断页面是否成功打开
                WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "divQuestion")))
                self._emit_progress("debug", f"线程 {self.worker_id}: 页面加载完成，开始填写...")
                # 短暂等待页面稳定
                time.sleep(random.uniform(1.0, 2.5))

                # 内层循环：执行生成的填写指令
                for instruction_index, instruction in enumerate(self.fill_config_instructions):
                    # 检查暂停和停止状态
                    while self.is_paused and self.is_running: time.sleep(0.1)
                    if not self.is_running: break # 如果收到停止信号，立即退出循环

                    # 提取指令信息
                    q_div_id = instruction['id'];
                    q_topic_num = instruction['topic_num'];
                    q_type_code = instruction['type_code'];
                    action = instruction['action']
                    self._emit_progress("info",
                                        f"线程 {self.worker_id}: 指令 {instruction_index + 1}/{len(self.fill_config_instructions)}: 题 {q_topic_num} ({q_div_id}), 类型 {q_type_code}, 动作: {action}")

                    # 用于存储需要JS点击的目标元素（部分情况下可能需要fallback到JS点击）
                    target_element_for_js_click = None

                    try:
                        # 定位问题所在的区域元素
                        q_element_xpath = f"//div[@id='{q_div_id}' and @topic='{q_topic_num}']"
                        q_element = WebDriverWait(self.driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, q_element_xpath)))

                        # --- 执行填充文本框指令 (类型 1, 2, 8) ---
                        if action == "fill":
                            text_to_fill = "" # 待填写的文本
                            # 根据题型获取要填写的具体内容
                            if q_type_code in ["1", "2"]: # 填空题 / 多行填空题
                                answers_list = instruction.get("text_answers_list", [""]) # 获取答案列表
                                fill_format = instruction.get("fill_format", _FILL_IN_BLANK_FORMAT_RANDOM) # 获取填写格式

                                if not answers_list: # 如果答案列表为空，填空字符串
                                     text_to_fill = ""
                                     self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num}: 答案列表为空，填空字符串。")
                                elif fill_format == _FILL_IN_BLANK_FORMAT_RANDOM:
                                    # 随机填写模式：从答案列表中随机选择一个
                                    text_to_fill = random.choice(answers_list)
                                    self._emit_progress("debug", f"线程 {self.worker_id}: 题 {q_topic_num} (随机填写): 选定答案 '{text_to_fill}'")
                                elif fill_format == _FILL_IN_BLANK_FORMAT_SEQUENTIAL:
                                    # 顺序填写模式：从共享状态获取当前索引，使用对应答案，然后更新共享状态中的索引
                                    # q_div_id 在循环开始时已从 instruction['id'] 中提取，作为共享字典的键
                                    text_to_fill = "" # 先初始化待填文本

                                    # 使用互斥锁保护对共享索引字典的访问
                                    # 检查共享状态和锁是否已正确传递
                                    if self._shared_sequential_indices is not None and self._sequential_indices_mutex is not None:
                                        self._sequential_indices_mutex.lock() # 加锁
                                        try:
                                            # 使用 get() 并提供默认值 0，确保字典中没有该 q_div_id 时不会出错
                                            current_idx = self._shared_sequential_indices.get(q_div_id, 0)
                                            # 使用模运算确保索引不会超出列表范围，实现循环使用
                                            if answers_list: # 确保答案列表不为空
                                                text_to_fill = answers_list[current_idx % len(answers_list)]
                                                # 更新该题 (由 q_div_id 标识) 在共享状态中的顺序索引
                                                self._shared_sequential_indices[q_div_id] = current_idx + 1
                                                self._emit_progress("debug", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 使用全局索引 {current_idx} 的答案 '{text_to_fill}'，全局下一份将使用索引 {self._shared_sequential_indices[q_div_id]}")
                                            else:
                                                 self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 答案列表为空，填空字符串。")
                                        except Exception as e_lock: # 捕获锁内部可能的错误
                                            self._emit_progress("error", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 访问共享索引时出错: {type(e_lock).__name__} - {e_lock}")
                                        finally:
                                            self._sequential_indices_mutex.unlock() # 解锁 (即使发生异常也尝试解锁)
                                    else:
                                         # 如果共享状态或锁没有正确传递，发出警告
                                         self._emit_progress("error", f"线程 {self.worker_id}: 题 {q_topic_num} (顺序填写): 共享状态或互斥锁未正确传递，无法进行顺序填写。请检查Worker创建参数。")
                                         # 此时 text_to_fill 仍然是空字符串 ""


                            elif q_type_code == "8": # 滑块题
                                text_to_fill = instruction.get('text_answer', '') # 从指令中获取解析好的滑块值
                                self._emit_progress("debug", f"线程 {self.worker_id}: 题 {q_topic_num} (滑块): 目标值 '{text_to_fill}'")
                            else: # 未知fill类型，不应该发生
                                self._emit_progress("error", f"线程 {self.worker_id}: 题 {q_topic_num}: 未知类型 '{q_type_code}' 的 'fill' 动作。")
                                continue # 跳过此指令

                            # 定位文本输入框或多行文本框
                            # 问卷星通常输入框的ID是 q+题号 或者类名包含inputtext
                            input_css_selector = f"#{q_div_id} input[id='q{q_topic_num}'], #{q_div_id} textarea[id='q{q_topic_num}'], #{q_div_id} input.inputtext, #{q_div_id} textarea.inputtext"
                            input_element = WebDriverWait(q_element, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, input_css_selector)))
                            # 清空并填入文本
                            input_element.clear();
                            input_element.send_keys(text_to_fill)
                            self._emit_progress("debug",
                                                f"线程 {self.worker_id}: 题 {q_topic_num} 填入: '{text_to_fill}'")

                        # --- 执行点击选择指令 (类型 3, 4, 5) ---
                        elif action == "click":
                            # 获取目标选项的原始索引 (1-based)
                            opt_original_idx = instruction['target_original_index'];
                            css_selector_option = ""
                            if q_type_code == "3" or q_type_code == "4":
                                # 单选/多选选项容器的CSS选择器 (通常是包含input和label的div)
                                css_selector_option = f"#{q_div_id} div.ui-controlgroup > div:nth-child({opt_original_idx})"
                            elif q_type_code == "5":
                                # 量表题选项容器的CSS选择器 (通常是li元素)
                                css_selector_option = f"#{q_div_id} div.scale-div ul > li:nth-child({opt_original_idx})"
                            # 可以根据需要添加更多题型的CSS选择器

                            if css_selector_option:
                                # 等待选项元素可点击
                                target_element = WebDriverWait(q_element, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector_option)))
                                target_element_for_js_click = target_element; # 记录备用JS点击元素
                                # 执行点击操作
                                target_element.click()
                                self._emit_progress("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 点击了选项 {opt_original_idx}.")

                                # 如果该选项需要填写“其他”文本，并且指令中包含了要填写的文本
                                if instruction.get("requires_other_text_fill") and instruction.get(
                                        "other_text_to_fill"):
                                    text_to_fill_for_other = instruction["other_text_to_fill"] # 获取要填写的“其他”文本
                                    try:
                                        # 在选项容器内查找“其他”文本框
                                        option_container_element = q_element.find_element(By.CSS_SELECTOR,
                                                                                          css_selector_option)
                                        other_text_field = None
                                        # 尝试多种XPath定位“其他”文本框
                                        try:
                                            other_text_field = option_container_element.find_element(By.XPATH,
                                                                                                     ".//input[@type='text' and (contains(@class, 'othertext') or contains(@class, 'inputtext'))]")
                                        except NoSuchElementException:
                                            try: # 尝试更通用的、查找任何非禁用的文本输入框
                                                other_text_field = option_container_element.find_element(By.XPATH,
                                                                                                         ".//input[@type='text' and not(@disabled) and not(contains(@style,'display:none')) and not(contains(@class,'hide'))][1]")
                                            except NoSuchElementException:
                                                self._emit_progress("warn",
                                                                    f"线程 {self.worker_id}: 题 {q_topic_num}, 选项 {opt_original_idx}(其他): 已勾选并有文本，但未找到对应文本框。")

                                        # 如果找到了“其他”文本框
                                        if other_text_field:
                                            other_text_field.clear(); # 清空原有内容
                                            other_text_field.send_keys(text_to_fill_for_other) # 填入文本
                                            self._emit_progress("debug",
                                                                f"线程 {self.worker_id}: 题 {q_topic_num} 其他项填入: '{text_to_fill_for_other}'")
                                            time.sleep(random.uniform(0.1, 0.3)) # 短暂等待
                                    except NoSuchElementException: # 查找“其他”文本框时发生NoSuchElementException
                                        self._emit_progress("warn",
                                                            f"线程 {self.worker_id}: 题 {q_topic_num}, 选项 {opt_original_idx}(其他): 文本输入框未找到(NoSuchElement)。")
                                    except Exception as e_other_fill: # 填写“其他”文本时发生其他错误
                                        self._emit_progress("error",
                                                            f"线程 {self.worker_id}: 题 {q_topic_num} 填充'其他'项文本时出错: {e_other_fill}")
                        # --- 点击选择指令处理结束 ---

                        # --- 执行下拉选择指令 (类型 7) ---
                        elif action == "dropdown_select":
                            opt_original_idx = instruction['target_original_index']; # 获取目标选项的原始索引 (1-based)
                            # 定位下拉框容器并点击展开
                            # 问卷星下拉框通常使用select2库，容器ID模式是 select2-q<题号>-container
                            dropdown_container_id = f"select2-q{q_topic_num}-container"
                            container_element = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.ID, dropdown_container_id)))
                            container_element.click();
                            time.sleep(random.uniform(0.3, 0.7)) # 等待下拉列表出现
                            # 定位下拉列表中的目标选项并点击
                            # 下拉列表本身通常有ID select2-q<题号>-results，选项是其li子元素
                            option_xpath = f"//ul[@id='select2-q{q_topic_num}-results']/li[{opt_original_idx}]"
                            option_element_to_click = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.XPATH, option_xpath)))
                            target_element_for_js_click = option_element_to_click; # 记录备用JS点击元素
                            option_element_to_click.click()
                            self._emit_progress("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 下拉选择了选项 {opt_original_idx}.")
                            # TODO: 下拉框的“其他”项自定义文本填写逻辑可能需要额外的处理，通常是选中后动态出现文本框
                            # 需要根据问卷星的实际DOM结构找到动态出现的文本框进行填写。

                        # --- 执行矩阵题点击指令 (类型 6) ---
                        elif action == "matrix_click":
                            sub_q_id_prefix = instruction['sub_q_id_prefix']; # 子问题行元素的ID前缀
                            opt_original_idx = instruction['target_original_index'] # 子问题选项在子问题行中的原始索引 (1-based)
                            # 定位矩阵选项元素 (通常是td，包含radio或checkbox)
                            # 尝试通过子问题行ID和td的序号定位
                            matrix_option_xpath = f"//*[@id='{sub_q_id_prefix}']/td[{opt_original_idx}]"
                            try:
                                # 优先等待元素可点击，更稳定
                                target_element = WebDriverWait(self.driver, 10).until(
                                   EC.element_to_be_clickable((By.XPATH, matrix_option_xpath))
                                )
                            except TimeoutException:
                                # 如果不可点击，则等待元素存在，再尝试JS点击
                                matrix_option_css = f"#{sub_q_id_prefix} > td:nth-child({opt_original_idx})"
                                target_element = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, matrix_option_css))
                                )
                                self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (ID前缀: {sub_q_id_prefix}) 选项 {opt_original_idx} 不直接可点击，尝试JS点击。")

                            target_element_for_js_click = target_element; # 记录备用JS点击元素
                            # 矩阵题通常需要JS点击以绕过一些校验或覆盖层
                            self.driver.execute_script("arguments[0].click();", target_element)
                            self._emit_progress("debug", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (ID前缀: {sub_q_id_prefix}) 点击了选项 {opt_original_idx}.")

                        # --- 执行排序题随机排序指令 (类型 11) ---
                        elif action == "sort_random":
                            self._emit_progress("info", f"线程 {self.worker_id}: 正在处理排序题 {q_topic_num}...")
                            # 定位排序列表容器
                            sortable_list_container_xpath = f"//div[@id='{q_div_id}']//ul[contains(@class,'sort_data') or contains(@class,'sortable') or contains(@class,'rank')]"
                            try:
                                sortable_list_element = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.XPATH, sortable_list_container_xpath)))
                                # 定位所有可排序项 (li元素)
                                sortable_items_xpath = f"{sortable_list_container_xpath}/li"
                                # 尝试获取可拖拽的li元素，如果找不到则获取所有li
                                all_list_items_elements = sortable_list_element.find_elements(By.XPATH,
                                                                                              "./li[@draggable='true']")
                                if not all_list_items_elements: all_list_items_elements = sortable_list_element.find_elements(
                                    By.XPATH, "./li") # Fallback if draggable=true not found

                                num_items = len(all_list_items_elements)
                                if num_items > 1: # 至少需要两个项才能排序
                                    self._emit_progress("info",
                                                        f"线程 {self.worker_id}: 排序题 {q_topic_num} 找到 {num_items} 个可排序项，进行随机拖拽。")
                                    actions_chain = ActionChains(self.driver); # 创建 ActionChains
                                    # 拖拽次数设定，项目越多或项目少时增加拖拽次数以提高随机性
                                    num_drags = num_items * random.randint(1, 2);
                                    if num_items <= 3: num_drags = num_items * 3 # Fewer items might need more shuffles
                                    for _ in range(num_drags):
                                        if not self.is_running: break # 检查停止信号
                                        try:
                                            # 每次拖拽前重新获取元素，因为DOM可能在拖拽后变化，避免StaleElementReferenceException
                                            current_items_elements = self.driver.find_elements(By.XPATH,
                                                                                               sortable_items_xpath)
                                            if len(current_items_elements) < 2: break # 项目数不足以拖拽

                                            # 随机选择源和目标索引
                                            source_idx = random.randrange(len(current_items_elements));
                                            target_idx = random.randrange(len(current_items_elements))
                                            # 确保源和目标不同，避免无效操作
                                            if source_idx == target_idx:
                                                # 如果源和目标相同，随机选择相邻位置作为新目标
                                                target_idx = (target_idx + random.choice([-1, 1])) % len(current_items_elements)
                                                # 确保索引在合法范围内
                                                if target_idx < 0: target_idx += len(current_items_elements)


                                            source_element = current_items_elements[source_idx];
                                            target_element = current_items_elements[target_idx]

                                            # 滚动源元素到可视区域（中心），提高拖拽成功率
                                            self.driver.execute_script(
                                                "arguments[0].scrollIntoViewIfNeeded({behavior: 'auto', block: 'center'});",
                                                source_element);
                                            time.sleep(random.uniform(0.1, 0.2)) # 短暂等待滚动完成

                                            # 执行拖拽操作链：按住源元素 -> 移动到目标元素 -> 释放
                                            actions_chain.click_and_hold(source_element).pause(
                                                random.uniform(0.1, 0.3)).move_to_element(target_element).pause(
                                                random.uniform(0.1, 0.3)).release().perform()
                                            time.sleep(random.uniform(0.4, 0.8)) # 拖拽后等待

                                        except StaleElementReferenceException:
                                            # 元素过时，重新获取列表，然后继续下一次拖拽
                                            self._emit_progress("warn",
                                                                f"线程 {self.worker_id}: 排序项元素已过时，重新尝试获取。"); time.sleep(
                                                0.2); continue # 继续内层拖拽循环
                                        except Exception as e_drag:
                                            # 拖拽时发生其他错误
                                            self._emit_progress("error",
                                                                f"线程 {self.worker_id}: 排序题 {q_topic_num} 拖拽时出错: {type(e_drag).__name__} - {str(e_drag)[:100]}"); break # 跳出拖拽循环
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
                        # --- 排序题随机排序指令处理结束 ---

                        # 每个操作后短暂等待，模拟用户行为
                        time.sleep(random.uniform(0.2, 0.5))

                    except ElementClickInterceptedException:
                        # 如果点击被其他元素（如覆盖层、广告等）拦截，尝试使用JS点击作为备用方案
                        self._emit_progress("warn",
                                            f"线程 {self.worker_id}: 题目 {q_topic_num} 点击被拦截，尝试JS点击...")
                        try:
                            if target_element_for_js_click: # 如果之前成功定位到了目标元素
                                self.driver.execute_script("arguments[0].click();",
                                                           target_element_for_js_click); time.sleep(0.3)
                                self._emit_progress("debug", f"线程 {self.worker_id}: JS点击成功。")
                            else: # 没有备用元素，JS点击也无法执行
                                self._emit_progress("error", f"线程 {self.worker_id}: JS点击失败：未找到备用目标元素。")
                        except Exception as js_e: # JS点击失败
                            self._emit_progress("error", f"线程 {self.worker_id}: JS点击也失败: {js_e}")
                    except TimeoutException: # Selenium 操作超时
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 操作超时: 题目 {q_topic_num}, ID {q_div_id}, 动作 {action}。")
                    except NoSuchElementException: # 元素未找到
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 元素未找到: 题目 {q_topic_num}, ID {q_div_id}, 动作 {action}。")
                    except Exception as e_instr: # 其他指令执行错误
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 处理题目 {q_topic_num} 时发生错误: {type(e_instr).__name__} - {str(e_instr)[:150]}")

                # 检查是否因用户中止而退出整个填写过程
                if not self.is_running: raise InterruptedError("用户中止操作")

                # --- 分页、提交、验证码、结果检查 ---
                # 问卷星通常是一次性加载所有问题但分fieldset隐藏，所以parser可能已经获取了所有问题。
                # 但如果问卷是真正的多页（下一页加载新内容），这里需要根据实际情况调整。
                # 当前逻辑是查找是否有“下一页”按钮，如果有就点击，并等待加载。
                try: # 尝试点击下一页按钮 (如果存在)
                    # 定位下一页按钮，通常ID是 divNextPage
                    next_page_button = self.driver.find_element(By.ID, "divNextPage")
                    # 检查按钮是否可见且启用
                    if next_page_button.is_displayed() and next_page_button.is_enabled():
                        self._emit_progress("info", f"线程 {self.worker_id}: 点击下一页...")
                        next_page_button.click();
                        # 等待旧的下一页按钮消失，表示页面已切换或加载
                        WebDriverWait(self.driver, 15).until(EC.staleness_of(next_page_button));
                        time.sleep(random.uniform(1.0, 2.0)) # 等待页面稳定
                        # TODO: 如果有下一页且新的问题出现在新加载的DOM中，需要有逻辑来获取并填写这些新问题。
                        # 目前假设parser能获取所有fieldset的问题。如果不是，需要重新解析或有专门的分页处理逻辑。
                except NoSuchElementException: # 如果没有找到下一页按钮，说明是最后一页或单页问卷
                    self._emit_progress("info", f"线程 {self.worker_id}: 未找到“下一页”，准备提交。")

                self._emit_progress("info", f"线程 {self.worker_id}: 尝试提交...")
                # 等待并点击提交按钮，通常ID是 ctlNext
                submit_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="ctlNext"]'))) # 问卷星提交按钮常用XPath
                submit_button.click();
                time.sleep(random.uniform(0.5, 1.0)) # 短暂等待，看是否弹出确认或验证码

                try: # 尝试处理提交确认弹窗 (如果存在)
                    # 定位弹窗中的确认按钮，通常是layui-layer-btn类下的a标签，文本为“确定”或“确认”
                    confirm_button = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH,
                                                                                                     "//div[contains(@class,'layui-layer-btn')]/a[normalize-space()='确定' or normalize-space()='确认']")))
                    confirm_button.click();
                    self._emit_progress("info", f"线程 {self.worker_id}: 点击了提交确认。");
                    time.sleep(random.uniform(0.8, 1.2)) # 等待弹窗关闭和页面响应
                except: # 未找到确认弹窗，忽略
                    self._emit_progress("info", f"线程 {self.worker_id}: 未找到提交确认弹窗。")

                try: # 尝试处理智能验证按钮 (如果存在)
                    # 定位智能验证按钮，通常ID是 SM_BTN_1
                    verify_button = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.ID, "SM_BTN_1")))
                    self._emit_progress("info", f"线程 {self.worker_id}: 点击智能验证按钮。");
                    verify_button.click();
                    time.sleep(random.uniform(2.5, 4.0)) # 等待智能验证结果或滑块出现
                except: # 未找到智能验证按钮，忽略
                    self._emit_progress("info", f"线程 {self.worker_id}: 未找到智能验证按钮。")

                try: # 尝试处理滑块验证码 (如果存在)
                    # 等待滑块文本（“请按住滑块”）出现
                    WebDriverWait(self.driver, 7).until(EC.visibility_of_element_located(
                        (By.XPATH, '//*[@id="nc_1__scale_text"]/span[contains(text(),"请按住滑块")]')))
                    # 定位滑块按钮
                    slider_button_el = self.driver.find_element(By.XPATH, '//*[@id="nc_1_n1z"]');
                    self._emit_progress("captcha", f"线程 {self.worker_id}: 检测到滑块验证...")
                    actions_slider = ActionChains(self.driver); # 创建 ActionChains
                    actions_slider.click_and_hold(slider_button_el) # 按住滑块

                    # 计算随机拖拽距离和分段移动，模拟真实用户行为
                    total_drag_target = random.randint(258, 280); # 目标距离范围 (经验值，可能需要针对不同网站调整)
                    num_segments = random.randint(3, 6); # 分段次数
                    current_moved = 0
                    for i in range(num_segments):
                        if current_moved >= total_drag_target * 0.95: break # 如果接近目标，提前结束
                        # 计算当前段的移动距离，并加入随机偏移
                        segment_dist = (total_drag_target / num_segments) + random.randint(-15,
                                                                                           15) if i < num_segments - 1 else total_drag_target - current_moved + random.randint(
                            5, 20) # 最后一段确保到达或略微超过目标
                        segment_dist = max(10, int(segment_dist)) # 每段至少移动10px
                        if current_moved + segment_dist > total_drag_target * 1.15: segment_dist = total_drag_target * 1.15 - current_moved; # 防止移动过远
                        if segment_dist <= 0: break # 无需移动则退出
                        # 移动鼠标，垂直方向也加入随机偏移
                        actions_slider.move_by_offset(segment_dist, random.randint(-7, 7));
                        # 暂停模拟真实行为，最后一段暂停时间可以短一些
                        actions_slider.pause(random.uniform(0.02, (0.15 if i < num_segments - 1 else 0.05)));
                        current_moved += segment_dist # 累加移动距离

                    actions_slider.release().perform(); # 释放滑块
                    self._emit_progress("info", f"线程 {self.worker_id}: 滑块拖动完成，约: {current_moved}px。");
                    time.sleep(random.uniform(2.5, 4.0)) # 等待验证结果

                except TimeoutException: # 未检测到滑块验证
                    self._emit_progress("info", f"线程 {self.worker_id}: 未检测到滑块验证。")
                except Exception as e_slider: # 滑块验证过程中出错
                    self._emit_progress("error",
                                        f"线程 {self.worker_id}: 滑块验证出错: {type(e_slider).__name__} - {e_slider}")

                self._emit_progress("info", f"线程 {self.worker_id}: 等待提交结果...")
                # 等待页面跳转或出现成功/失败提示
                try:
                    WebDriverWait(self.driver, 12).until(EC.any_of(
                        # 常见成功URL关键词
                        EC.url_contains("finished"), EC.url_contains("result"), EC.url_contains("completed"),
                        EC.url_contains("thank"), EC.url_contains("Success"),
                        # 常见成功页面文本
                        EC.presence_of_element_located((By.XPATH,
                                                        "//*[contains(text(),'提交成功') or contains(text(),'感谢您') or contains(text(),'已完成') or contains(text(),'谢谢')]")),
                        # 常见失败页面文本
                        EC.presence_of_element_located((By.XPATH,
                                                        "//*[contains(text(),'提交失败') or contains(text(),'错误') or contains(@class,'wjx_error') or contains(@class,'error_validator')]"))
                    ))
                except TimeoutException: # 等待最终结果超时
                    self._emit_progress("warn", f"线程 {self.worker_id}: 等待最终结果超时。")

                # 检查最终页面状态判断提交是否成功
                final_url = self.driver.current_url;
                final_title = self.driver.title.lower() if self.driver.title else "";
                page_source_lower = ""
                try:
                    page_source_lower = self.driver.page_source.lower()
                except: # 获取页面源码时可能出错
                    self._emit_progress("warn", f"线程 {self.worker_id}: 无法获取最终页面源码。")

                # 定义成功和失败的关键词列表
                success_k_url = ["finished", "result", "complete", "thank", "success", "aspx"]; # 常见成功URL片段
                success_k_title = ["感谢", "完成", "成功", "提交成功", "谢谢"] # 常见成功页面标题关键词
                success_k_page = ["提交成功", "感谢您", "问卷已提交", "已完成", "thank you", "completed",
                                  "submitted successfully", "您的回答已提交"] # 常见成功页面文本关键词
                # 定义失败的关键词列表
                error_k_page = ["提交失败", "验证码错误", "必填项", "网络超时", "重新提交", "滑块验证失败",
                                "frequencylimit", "error", "fail", "invalid", "请稍后重试", "系统繁忙", "不允许提交",
                                "答题时间过短"] # 常见失败页面文本关键词

                submission_successful = False;
                extracted_error_message = "" # 用于提取页面上的具体错误信息

                # 首先检查页面是否包含明确的错误或失败提示
                if any(keyword in page_source_lower for keyword in error_k_page):
                    submission_successful = False;
                    fail_reason = "页面包含明确的错误或失败提示。"
                    # 尝试提取具体的错误信息文本
                    try:
                        # 常见的错误信息元素选择器或XPath列表，从页面中查找并提取文本
                        err_selectors = [
                            "//div[contains(@class,'tip_wrapper') and (contains(.,'失败') or contains(.,'错误') or contains(.,'验证'))]",
                            "//div[contains(@class,'alert_error') or contains(@class,'error_validator') or contains(@class,'wjx_error')]",
                            "//div[@class='layui-layer-content' and (contains(.,'失败') or contains(.,'错误') or contains(.,'验证') or contains(.,'不允许'))]",
                            "//div[contains(@class,'field_answer_tip') or contains(@class,'div_error_msg')]"]
                        for selector in err_selectors:
                            error_elements = self.driver.find_elements(By.XPATH, selector)
                            for err_el in error_elements:
                                if err_el.is_displayed() and err_el.text.strip():
                                    extracted_error_message = err_el.text.strip()[:150]; # 提取并截断错误信息
                                    break # 找到一个错误信息就够了
                            if extracted_error_message: break # 如果找到了错误信息，退出外层循环
                    except: # 提取错误信息时出错，忽略
                        pass
                    # 组合最终的失败消息
                    final_message_or_url = f"{fail_reason}" + (
                        f" 页面提示: {extracted_error_message}" if extracted_error_message else f" (关键词匹配). URL: {final_url}")
                else:
                    # 如果页面没有明确错误，检查是否是成功状态
                    url_changed = initial_url.split('?')[0].split('#')[0] != final_url.split('?')[0].split('#')[0] # 检查URL是否变化（去除参数和锚点）
                    url_ok = any(k in final_url.lower() for k in success_k_url); # URL是否包含成功关键词
                    title_ok = any(k in final_title for k in success_k_title); # 标题是否包含成功关键词
                    page_ok = any(k in page_source_lower for k in success_k_page) # 页面源码是否包含成功关键词

                    if url_changed and url_ok: # URL变化且包含成功关键词
                        submission_successful = True; final_message_or_url = f"成功提交, URL跳转: {final_url}"
                    elif title_ok: # 标题包含成功关键词
                        submission_successful = True; final_message_or_url = f"成功提交, 标题: '{self.driver.title}'. URL: {final_url}"
                    elif page_ok: # 页面源码包含成功关键词
                        submission_successful = True; final_message_or_url = f"成功提交, 页面含成功标识. URL: {final_url}"
                    # 如果URL变化，但没有明确的错误关键词，也可能成功 (需要用户复核)
                    elif url_changed and not any(
                        ek in final_url.lower() for ek in ["error", "fail", "login", "code=", "Error", "Fail"]):
                        submission_successful = True; final_message_or_url = f"提交后URL变化且无明显错误: {final_url} (请复核)"
                    else: # 其他情况，判断为未知状态或失败
                        submission_successful = False; final_message_or_url = f"提交后状态未知. URL: {final_url}, 标题: '{self.driver.title}'"

                # 更新本次填写尝试的成功状态和最终消息
                current_fill_success = submission_successful
                # 发送相应的进度消息
                if current_fill_success:
                    self._emit_progress("success_once", f"线程 {self.worker_id}: {final_message_or_url}")
                else:
                    self._emit_progress("error", f"线程 {self.worker_id}: {final_message_or_url}")

            except InterruptedError: # 捕获用户中止异常
                final_message_or_url = f"线程 {self.worker_id}: 用户中止"; self._emit_progress("info",
                                                                                               final_message_or_url); self.is_running = False # 设置运行标志为False，退出主循环
            except TimeoutException as te: # 捕获Selenium操作超时异常
                final_message_or_url = f"线程 {self.worker_id}: 操作超时: {str(te).splitlines()[0]}"; self._emit_progress(
                    "error", final_message_or_url)
            except Exception as e_run: # 捕获其他未知异常
                tb_str = traceback.format_exc(); # 获取异常追踪信息
                final_message_or_url = f"线程 {self.worker_id}: 未知错误: {type(e_run).__name__} - {str(e_run)[:200]}\nTrace: {tb_str.splitlines()[-3:]}"; # 提取错误类型、消息和最后几行追踪信息
                self._emit_progress("error", final_message_or_url)
            finally:
                # 本次填写尝试结束后的清理和状态更新
                if self.driver:
                    try:
                        self.driver.quit() # 关闭浏览器和 WebDriver
                    except Exception as quit_e: # 忽略关闭时的错误
                        self._emit_progress("warn", f"线程 {self.worker_id}: 关闭WebDriver出错: {quit_e}")
                    self.driver = None # 清空 driver 引用
                self._cleanup_user_data_dir() # 清理用户数据目录

                # 如果本次填写成功，增加已完成计数
                if current_fill_success: self.fills_completed_by_this_worker += 1
                # 发射单次填写完成信号
                self.single_fill_finished_signal.emit(self.worker_id, current_fill_success, final_message_or_url)

                # 检查是否达到本线程目标份数或收到停止信号
                if not self.is_running or self.fills_completed_by_this_worker >= self.num_fills_to_complete_by_worker:
                    # 达到目标或停止，退出外层填写循环
                    break

                # 如果需要继续填写下一份，短暂休息
                if self.is_running:
                    sleep_duration = random.uniform(3, 7) # 随机休息时间
                    self._emit_progress("info", f"线程 {self.worker_id} 本次结束, 休息 {sleep_duration:.1f} 秒...")
                    # 分段睡眠，以便快速响应停止/暂停信号
                    for _ in range(int(sleep_duration * 10)): # 将总睡眠时间分成100ms的小段
                        if not self.is_running: break; time.sleep(0.1) # 每段睡眠后都检查停止信号

        # 填写任务结束（达到目标或被中止）
        if self.fills_completed_by_this_worker >= self.num_fills_to_complete_by_worker:
            self._emit_progress("info",
                                f"线程 {self.worker_id} 完成全部分配 {self.num_fills_to_complete_by_worker} 份。")
        elif not self.is_running:
            self._emit_progress("info",
                                f"线程 {self.worker_id} 中止, 完成 {self.fills_completed_by_this_worker}/{self.num_fills_to_complete_by_worker} 份。")
        else:
            # 可能是WebDriver初始化失败等原因导致在未完成目标份数前退出循环
            self._emit_progress("warn",
                                f"线程 {self.worker_id} 提前结束, 完成 {self.fills_completed_by_this_worker}/{self.num_fills_to_complete_by_worker} 份。")

        # 发射线程完成信号，通知主线程此Worker已结束
        self.worker_completed_all_fills_signal.emit(self.worker_id)

    def stop_worker(self):
        """
        接收停止信号，设置运行标志为 False，并尝试中断 WebDriver 操作。
        设置标志位是主要的停止机制，依赖于 worker 在循环或 sleep 中检查 is_running。
        """
        if self.is_running:
            self._emit_progress("info", f"线程 {self.worker_id} 接收到停止信号。")
            self.is_running = False
            # Selenium 的同步 API 很难在外部优雅地中断阻塞调用（如 driver.get 或等待元素）。
            # 最可靠的方式是设置标志位，并依赖 worker 的 internal loops/sleeps 来检查。
            # 另一种方法是尝试 driver.execute_script("window.stop();")，但这并不总是有效，且可能导致其他问题。
            # 对于长时间的 driver.get，超时设置是主要的安全网。

    def pause_worker(self):
        """
        接收暂停信号，设置暂停标志为 True。
        """
        if self.is_running and not self.is_paused:
            self._emit_progress("info", f"线程 {self.worker_id} 已暂停。")
            self.is_paused = True

    def resume_worker(self):
        """
        接收恢复信号，设置暂停标志为 False。
        """
        if self.is_running and self.is_paused:
            self.is_paused = False
            self._emit_progress("info", f"线程 {self.worker_id} 已恢复。")