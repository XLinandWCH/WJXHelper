# filler_worker.py (修改后的)
# 负责在一个独立线程中驱动浏览器填写问卷的工作类。

import time
import random
import traceback
import numpy  # 确保导入，用于随机选择、概率计算等
import os
import tempfile
import shutil
import re # 导入正则表达式模块

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
# 确保 utils.py 中的 calculate_multiple_choices_from_percentages 函数能够正确处理概率列表
from utils import parse_weights_from_string, calculate_choice_from_weights, calculate_multiple_choices_from_percentages

# 导入新的填写逻辑处理类
from wjx_fill_logic import WJXFillLogic

# 导入常量模块 (假设已经创建 constants.py 并定义了这些常量)
try:
    from constants import (_FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM,
                           _FILL_IN_BLANK_FORMAT_SEQUENTIAL,
                           _FILL_IN_BLANK_FORMAT_RANDOM)
except ImportError:
    # 如果导入失败，使用默认值，但应确保 constants.py 存在且正确
    print("WARNING: Failed to import constants from constants.py. Using default values.")
    _FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM = "||"
    _FILL_IN_BLANK_FORMAT_SEQUENTIAL = "sequential"
    _FILL_IN_BLANK_FORMAT_RANDOM = "random"


class FillerWorker(QThread):
    """
    负责在一个独立线程中驱动浏览器填写问卷的工作类。
    每个Worker实例负责完成指定数量的问卷填写任务。
    它管理 WebDriver 生命周期、多份填写的循环、整体流程（加载、提交、验证码）
    并将单个题目的填写委托给 WJXFillLogic 类。
    """
    # 定义信号，用于与主UI线程通信，报告进度、完成状态和消息
    # worker_id, 已完成份数(本线程), 目标份数(本线程), 消息类型(info,warn,error等), 消息内容
    progress_signal = pyqtSignal(int, int, int, str, str)
    # worker_id, 本次填写是否成功, 消息/最终URL
    single_fill_finished_signal = pyqtSignal(int, bool, str)
    # worker_id
    worker_completed_all_fills_signal = pyqtSignal(int)

    def __init__(self, worker_id, url, user_raw_configurations_template,
                 num_fills_for_this_worker, total_target_fills,
                 browser_type="edge",
                 driver_executable_path=None,
                 headless=True, proxy=None,
                 base_user_data_dir_path=None,
                 slow_mode=False,
                 shared_sequential_indices: dict = None,  # 新增参数：共享的顺序索引字典
                 sequential_indices_mutex: QMutex = None,   # 新增参数：共享的互斥锁
                 human_like_mode_config: dict = None):
        """
        初始化工作线程。
        :param worker_id: 工作线程的唯一ID。
        :param url: 待填写问卷的URL。
        :param user_raw_configurations_template: 从问卷设置界面获取的用户配置模板。
        :param num_fills_for_this_worker: 本线程需要完成的填写份数。
        :param total_target_fills: 所有线程的总填写目标份数（用于UI全局进度显示）。
        :param browser_type: 使用的浏览器类型（"edge", "chrome", "firefox"）。
        :param driver_executable_path: 对应浏览器驱动的路径。
        :param headless: 是否以无头模式运行。
        :param proxy: 代理地址（格式如 "IP:PORT"）。
        :param base_user_data_dir_path: 用户数据目录的基础路径。
        :param slow_mode: 是否启用慢速稳定模式。
        :param shared_sequential_indices: 所有Worker共享的顺序填空索引字典 {q_div_id: current_index}。
        :param sequential_indices_mutex: 访问共享顺序填空索引字典时使用的互斥锁 (QMutex)。
        :param human_like_mode_config: 包含“拟人工”模式配置的字典。
        """
        super().__init__()
        # 初始化工作线程的各项属性
        self.worker_id = worker_id
        self.url = url
        # 保存用户原始配置模板，包含了各种配置（填空、权重、概率、必选等）
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
        self.slow_mode = slow_mode
        self.human_like_mode_config = human_like_mode_config if human_like_mode_config else {'enabled': False}
        # 用户数据目录的基础路径
        self.base_user_data_dir_path = base_user_data_dir_path
        # 本次运行实际使用的用户数据目录 (每个worker一个独立目录)
        self.actual_user_data_dir = None

        # --- 用于追踪顺序填空题的当前索引 ---
        # 这个状态是共享的，由外部（如主窗口或 Worker Manager）传入并保护
        self._shared_sequential_indices = shared_sequential_indices  # 保存共享字典的引用
        self._sequential_indices_mutex = sequential_indices_mutex    # 保存共享互斥锁的引用

        # WebDriver 实例
        self.driver = None

        # WJXFillLogic 实例 (在 run 方法中每次填写尝试前创建)
        self._fill_logic = None


    def _initialize_driver(self):
        """
        初始化 WebDriver 实例。根据配置的浏览器类型、驱动路径、无头模式、代理和用户数据目录进行设置。
        :return: 初始化成功返回 True，失败返回 False。
        """
        try:
            # 定义常用User-Agent和CDP脚本用于反爬
            # 根据浏览器类型选择一个合适的User-Agent
            if "edge" in self.browser_type:
                 common_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.2200.0"
            elif "chrome" in self.browser_type:
                 common_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            elif "firefox" in self.browser_type:
                 common_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
            else: # 默认一个通用UA
                 common_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


            # CDP脚本用于修改 navigator 属性，使其看起来不像自动化工具 (仅限Chromium内核浏览器)
            common_cdp_script = """
               Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
               Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
               Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
               Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
               Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
               // 模拟 WebGL 指纹
               const getParameter = WebGLRenderingContext.prototype.getParameter;
               WebGLRenderingContext.prototype.getParameter = function(parameter) {
                   if (parameter === 37445) return 'Intel Open Source Technology Center';
                   if (parameter === 37446) return 'Mesa DRI Intel(R) Ivybridge Desktop';
                   return getParameter(parameter);
               };
            """

            # 设置用户数据目录，用于保持session/cookie/缓存等（仅限Chromium内核浏览器）
            # 每个 Worker 使用一个独立的用户数据目录，以便并发运行互不影响
            if self.browser_type in ["edge", "chrome"]:
                # 如果指定了基础路径且存在，则在该基础路径下创建worker专属子目录
                if self.base_user_data_dir_path and os.path.isdir(self.base_user_data_dir_path):
                    self.actual_user_data_dir = os.path.join(self.base_user_data_dir_path,
                                                             f"profile_w{self.worker_id}_{random.randint(1000, 9999)}") # 随机后缀增加唯一性
                else: # 否则在系统临时目录下创建
                    self.actual_user_data_dir = os.path.join(tempfile.gettempdir(),
                                                             f"wjx_filler_profile_w{self.worker_id}_{random.randint(1000, 9999)}")
                # 确保目录存在，如果同名路径是文件则删除
                if os.path.exists(self.actual_user_data_dir) and not os.path.isdir(self.actual_user_data_dir):
                    try:
                        os.remove(self.actual_user_data_dir)
                    except OSError:
                        pass # 忽略删除失败的错误
                os.makedirs(self.actual_user_data_dir, exist_ok=True)
                self._emit_progress("debug", f"线程 {self.worker_id}: 使用用户数据目录: {self.actual_user_data_dir}")
            else: # Firefox 等其他浏览器可能不支持 --user-data-dir 参数，或者方式不同
                 # 对于 Firefox，可以考虑使用 profile 参数，但这里简化处理，不为 Firefox 设置独立用户数据目录
                 self.actual_user_data_dir = None # Firefox 不设置此项
                 self._emit_progress("debug", f"线程 {self.worker_id}: {self.browser_type.capitalize()} 不支持独立用户数据目录或未配置，将使用默认 profile。")


            # 设置驱动服务（如果指定了驱动路径）
            service = None
            if self.driver_executable_path and os.path.isfile(self.driver_executable_path):
                try:
                    if self.browser_type == "edge":
                        service = EdgeService(executable_path=self.driver_executable_path)
                    elif self.browser_type == "chrome":
                        service = ChromeService(executable_path=self.driver_executable_path)
                    elif self.browser_type == "firefox":
                        service = FirefoxService(executable_path=self.driver_executable_path)
                    else: # 不支持的浏览器类型
                        self._emit_progress("error",
                                            f"线程 {self.worker_id}: 初始化时遇到不支持的浏览器类型 '{self.browser_type}'"); return False
                except Exception as service_e:
                     self._emit_progress("error",
                                        f"线程 {self.worker_id}: 初始化驱动服务时出错: {type(service_e).__name__} - {service_e}"); return False

            elif self.driver_executable_path: # 如果用户指定了路径但文件不存在
                 self._emit_progress("warn",
                                     f"线程 {self.worker_id}: 指定的驱动路径 '{self.driver_executable_path}' 不存在，尝试从系统PATH查找。")
                 # Selenium 会尝试从系统PATH查找，无需指定 service

            # 配置并创建浏览器实例
            if self.browser_type == "edge":
                edge_options = EdgeOptions();
                edge_options.use_chromium = True # 确保使用Chromium内核Edge
                # 设置无头模式和GPU禁用
                if self.headless: edge_options.add_argument("--headless=new"); edge_options.add_argument("--disable-gpu") # 新版headless模式
                # 设置代理
                if self.proxy:
                    proxy_url = f"http://{self.proxy}" # 默认http
                    # 简单的判断，如果代理看起来像https或socks，可以调整
                    # 但通常IP:PORT格式是http/https通用
                    edge_options.add_argument(f"--proxy-server={proxy_url}")
                # 其他常用选项
                edge_options.add_argument("--no-sandbox"); # 禁用沙箱（在某些环境下需要）
                edge_options.add_argument("--disable-dev-shm-usage") # 解决Docker等环境下的 /dev/shm 问题
                edge_options.add_argument("--disable-infobars") # 禁用"Chrome正受到自动测试软件的控制"
                edge_options.add_argument("--start-maximized") # 启动时最大化
                edge_options.add_argument("--disable-extensions") # 禁用扩展
                edge_options.add_argument("--disable-popup-blocking") # 禁用弹窗拦截
                edge_options.add_argument("--log-level=3") # 减少日志输出

                # 反爬虫选项
                edge_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"]) # 排除自动化和日志标志
                edge_options.add_experimental_option('useAutomationExtension', False) # 禁用自动化扩展
                edge_options.add_argument('--disable-blink-features=AutomationControlled') # 禁用 Blink 特性 AutomationControlled
                edge_options.add_argument(f"user-agent={common_user_agent}") # 设置User-Agent
                # 随机化窗口大小以模拟不同用户环境
                resolutions = ["1920,1080", "1536,864", "1440,900", "1366,768"]
                edge_options.add_argument(f"--window-size={random.choice(resolutions)}")

                # 用户数据目录
                if self.actual_user_data_dir: edge_options.add_argument(f"--user-data-dir={self.actual_user_data_dir}")

                # 创建Edge WebDriver实例
                self.driver = webdriver.Edge(service=service, options=edge_options) if service else webdriver.Edge(
                    options=edge_options)

            elif self.browser_type == "chrome":
                # Chrome配置类似Edge
                chrome_options = ChromeOptions()
                if self.headless: chrome_options.add_argument("--headless=new"); chrome_options.add_argument(
                    "--disable-gpu") # 新版headless模式
                if self.proxy:
                    proxy_url = f"http://{self.proxy}"
                    chrome_options.add_argument(f"--proxy-server={proxy_url}")
                chrome_options.add_argument("--no-sandbox");
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-infobars")
                chrome_options.add_argument("--start-maximized")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument("--log-level=3") # 减少日志输出
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument(f"user-agent={common_user_agent}")
                resolutions = ["1920,1080", "1536,864", "1440,900", "1366,768"]
                chrome_options.add_argument(f"--window-size={random.choice(resolutions)}")

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
                    try:
                        proxy_host, proxy_port = self.proxy.split(":")
                        firefox_options.set_preference("network.proxy.http", proxy_host); # HTTP代理
                        firefox_options.set_preference("network.proxy.http_port", int(proxy_port))
                        firefox_options.set_preference("network.proxy.ssl", proxy_host); # HTTPS代理
                        firefox_options.set_preference("network.proxy.ssl_port", int(proxy_port))
                        firefox_options.set_preference("network.proxy.socks", proxy_host); # SOCKS代理
                        firefox_options.set_preference("network.proxy.socks_port", int(proxy_port))
                         # 默认不代理 localhost
                        firefox_options.set_preference("network.proxy.no_proxies_on", "localhost, 127.0.0.1")
                    except Exception as proxy_e:
                         self._emit_progress("warn", f"线程 {self.worker_id}: Firefox代理配置 '{self.proxy}' 无效: {proxy_e}. 将不使用代理。");
                         # 清除可能已设置的部分代理偏好
                         firefox_options.set_preference("network.proxy.type", 0) # 恢复默认（无代理）


                # 反爬虫选项
                firefox_options.set_preference("dom.webdriver.enabled", False) # 禁用 navigator.webdriver
                firefox_options.set_preference('useAutomationExtension', False) # 禁用自动化扩展
                firefox_options.profile.set_preference("general.useragent.override", common_user_agent) # 设置User-Agent
                # 模拟屏幕分辨率（需要 Firefox 驱动支持 --window-size 或使用 ActionChains/JS 设置）
                # firefox_options.add_argument(f"--width=1920"); firefox_options.add_argument(f"--height=1080") # 这些可能不是标准命令行参数

                # 创建Firefox WebDriver实例
                self.driver = webdriver.Firefox(service=service,
                                                options=firefox_options) if service else webdriver.Firefox(
                    options=firefox_options)
                # Firefox 设置窗口大小可能需要在创建实例后进行
                try:
                    self.driver.set_window_size(1920, 1080)
                except Exception as size_e:
                    self._emit_progress("warn", f"线程 {self.worker_id}: Firefox设置窗口大小失败: {size_e}")


            else:
                # 不支持的浏览器类型，发送错误信号
                self._emit_progress("error",
                                    f"线程 {self.worker_id}: 初始化时遇到不支持的浏览器类型 '{self.browser_type}'"); return False

            # 设置页面加载和元素查找的超时时间
            self.driver.set_page_load_timeout(60); # 页面加载最长等待时间，防止卡死
            self.driver.implicitly_wait(5) # 元素隐式等待时间
            # 执行CDP脚本（仅限Chromium内核浏览器）
            if self.browser_type in ["edge", "chrome"] and self.driver:
                try:
                    self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": common_cdp_script})
                except Exception as cdp_e:
                     self._emit_progress("warn", f"线程 {self.worker_id}: 执行CDP脚本失败 (可能浏览器或驱动版本不支持): {cdp_e}")

            self._emit_progress("info", f"线程 {self.worker_id}: {self.browser_type.capitalize()} Driver 初始化成功。")
            return True # 初始化成功

        except WebDriverException as wde: # 捕获 WebDriver 相关的异常
            error_msg = (f"线程 {self.worker_id}: 初始化 {self.browser_type.capitalize()} Driver 失败 (WebDriverException)。\n"
                         f"请确保驱动程序版本与浏览器匹配，并在“程序设置”中指定正确路径或将其添加到系统PATH。\n"
                         f"尝试路径: {self.driver_executable_path if self.driver_executable_path else '系统PATH'}\n"
                         f"具体错误: {str(wde).splitlines()[0]}") # 提取错误的第一行
            self._emit_progress("error", error_msg);
            self._cleanup_user_data_dir(); # 清理可能创建的用户数据目录
            # 设置 is_running 为 False 确保线程停止
            self.is_running = False
            return False
        except Exception as e: # 捕获其他初始化错误
            error_msg = (f"线程 {self.worker_id}: 初始化 {self.browser_type.capitalize()} Driver 时发生未知错误。\n"
                         f"尝试路径: {self.driver_executable_path if self.driver_executable_path else '系统PATH'}\n"
                         f"具体错误: {type(e).__name__} - {e}")
            self._emit_progress("error", error_msg);
            self._cleanup_user_data_dir();
            # 设置 is_running 为 False 确保线程停止
            self.is_running = False
            return False

    def _cleanup_user_data_dir(self):
        """
        清理 worker 创建的临时用户数据目录。
        注意：这个方法应该在 driver.quit() 调用之后执行。
        """
        if self.actual_user_data_dir and os.path.exists(self.actual_user_data_dir):
            # 添加一个小的延迟，确保浏览器进程完全退出释放文件锁
            time.sleep(0.5)
            try:
                # 使用 shutil.rmtree 清理目录，ignore_errors=True 会忽略删除过程中的错误
                shutil.rmtree(self.actual_user_data_dir, ignore_errors=True)
                self._emit_progress("debug",
                                    f"线程 {self.worker_id}: 已清理用户数据目录 {self.actual_user_data_dir}")
            except Exception as e_cleanup_parser: # 捕获清理时的错误
                self._emit_progress("warn",
                                    f"线程 {self.worker_id}: 清理用户数据目录 {self.actual_user_data_dir} 失败: {e_cleanup_parser}")
        self.actual_user_data_dir = None # 清空目录路径引用

    def _emit_progress(self, msg_type, message):
        """
        发射进度信号，将消息传递给UI线程更新日志和状态。
        这是一个回调函数，可以传递给 WJXFillLogic。
        :param msg_type: 消息类型 (如 "info", "warn", "error", "success_once", "captcha", "debug")。
        :param message: 消息内容字符串。
        """
        # 在发射信号前检查线程是否仍在运行，避免在线程退出后发射信号导致错误
        if hasattr(self, 'is_running') and self.is_running:
             self.progress_signal.emit(self.worker_id, self.fills_completed_by_this_worker,
                                       self.num_fills_to_complete_by_worker, msg_type, message)
        # 线程停止后，可能仍然会调用 _emit_progress (例如在 finally 块中)。
        # 此时直接打印到控制台作为后备日志。
        else:
             print(f"[Worker {self.worker_id} Log ({msg_type})]: {message}")


    def _generate_randomized_instructions(self, raw_configs_template):
        """
        根据用户配置模板生成本次填写尝试的具体操作指令列表。
        这个方法只负责生成“执行计划”（指令列表），不实际执行 Selenium 操作。
        对于填空题，指令会包含答案列表和填写格式，实际选择答案由填写逻辑类在 run 方法中进行。
        :param raw_configs_template: 用户配置模板列表（从 QuestionnaireSetupWidget 获取）。
        :return: 生成的指令列表，失败返回 None 或空列表。
        """
        if not raw_configs_template:
            self._emit_progress("error", f"线程 {self.worker_id}: _generate_randomized_instructions: 原始配置模板为空。")
            return [] # 返回空列表而不是 None

        fill_instructions = [] # 存储生成的指令

        # 遍历每个问题模板
        for q_template in raw_configs_template:
            # 提取模板中的问题信息
            q_id = q_template.get('id');
            q_topic_num = q_template.get('topic_num');
            q_type = q_template.get('type_code')

            # 再次验证模板项的基本数据完整性
            if not q_id or not q_topic_num or not q_type:
                 self._emit_progress("warn", f"线程 {self.worker_id}: 跳过一个无效的问题模板项 (缺少ID/题号/类型): {q_template}")
                 continue # 跳过此问题模板

            # 获取解析后的选项数据（包含“其他”项配置和“必选”标记）
            options_parsed = q_template.get('options_parsed', [])
            # 获取解析后的子问题数据
            sub_questions_parsed = q_template.get('sub_questions', [])


            # 构建指令的基础结构
            instruction_base = {"id": q_id, "topic_num": q_topic_num, "type_code": q_type}

            # --- 处理填空题/多行填空题 (类型 1, 2) ---
            # 对于填空题，指令只需包含答案列表和格式，实际选择/获取答案由填写逻辑类在 run 方法中进行
            if q_type in ["1", "2"]:
                instruction = instruction_base.copy();
                instruction["action"] = "fill" # 操作是填充文本框
                # 从模板中获取解析后的答案列表和填写格式，直接存储到指令中
                instruction["text_answers_list"] = q_template.get("text_answers_list", [""])
                instruction["fill_format"] = q_template.get("fill_format", _FILL_IN_BLANK_FORMAT_RANDOM) # 默认随机格式
                # 如果答案列表为空，且不是顺序填写（顺序填写空列表可能需要空字符串占位），发出警告
                if not instruction["text_answers_list"] and instruction["fill_format"] != _FILL_IN_BLANK_FORMAT_SEQUENTIAL:
                     self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (填空): 配置的答案列表为空，将填空字符串。")
                     instruction["text_answers_list"] = [""] # 确保列表至少包含一个空字符串，避免索引错误
                fill_instructions.append(instruction)

            # --- 滑块题 (类型 8) ---
            elif q_type == "8":
                instruction = instruction_base.copy();
                instruction["action"] = "fill" # 操作是填充文本框
                raw_slider_text = q_template.get("raw_slider_input", "75").strip() # 默认值 75
                parsed_value = "75" # 默认解析值为 75
                try:
                    # 解析滑块配置字符串
                    if ':' in raw_slider_text: # 检查是否存在冒号，用于判断“值1,值2,...:权重1,权重2,...”格式
                        parts = raw_slider_text.split(':')
                        if len(parts) == 2:
                            values_str, weights_str = parts
                            # 安全地解析值和权重，只取数字部分
                            values = [int(v.strip()) for v in values_str.split(',') if v.strip().isdigit()]
                            weights_list = [int(w.strip()) for w in weights_str.split(',') if w.strip().isdigit()]

                            # 检查值和权重数量是否匹配且非空，权重和大于0
                            if values and weights_list and len(values) == len(weights_list) and sum(weights_list) > 0:
                                # 根据权重选择一个值的索引
                                chosen_value_idx = calculate_choice_from_weights(weights_list)
                                # 如果选择成功 (索引有效)，使用选中的值
                                if chosen_value_idx != -1:
                                    parsed_value = str(values[chosen_value_idx])
                                else: # 权重计算或选择失败
                                     self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (滑块): 权重选择失败，随机选择一个值。")
                                     parsed_value = str(random.choice(values)) if values else "75" # 随机选一个值或默认值
                            else: # 值或权重列表解析失败或不匹配
                                 self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (滑块): 值和权重格式无效或不匹配 '{raw_slider_text}'，尝试按逗号分割随机选。")
                                 # 回退到按逗号分隔随机选的逻辑
                                 values = [int(v.strip()) for v in raw_slider_text.replace(':', ',').split(',') if v.strip().isdigit()]
                                 parsed_value = str(random.choice(values)) if values else "75"

                        else: # 冒号格式但不符合“值:权重”结构
                             self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (滑块): 冒号格式 '{raw_slider_text}' 无效，尝试按逗号分割随机选。")
                             # 回退到按逗号分隔随机选的逻辑
                             values = [int(v.strip()) for v in raw_slider_text.split(',') if v.strip().isdigit()]
                             parsed_value = str(random.choice(values)) if values else "75"

                    elif ',' in raw_slider_text: # 支持 "值1,值2,..." 格式 (等权重随机)
                        values = [int(v.strip()) for v in raw_slider_text.split(',') if v.strip().isdigit()]
                        parsed_value = str(random.choice(values)) if values else "75" # 随机选一个值或默认值
                    else: # 支持单个整数值
                        parsed_value = str(int(raw_slider_text)) if raw_slider_text.isdigit() else "75"

                except Exception as e_parse_slider: # 解析失败则使用默认值并警告
                    self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num}: 滑块值配置 '{raw_slider_text}' 解析出错: {e_parse_slider}，使用默认值 '75'。")
                    parsed_value = "75"

                instruction["text_answer"] = parsed_value # 将解析或随机选择的值存储到指令
                fill_instructions.append(instruction)

            # --- 单选题, 量表题, 下拉选择题 (类型 3, 5, 7) ---
            # 这些题型根据权重选择一个选项
            elif q_type in ["3", "5", "7"]:
                if options_parsed:
                    instruction = instruction_base.copy();
                    raw_weights_str = q_template.get("raw_weight_input", "")
                    # 解析权重字符串，获取数字权重列表
                    weights = parse_weights_from_string(raw_weights_str, len(options_parsed));
                    # 根据权重选择一个选项的索引 (在 options_parsed 列表中的索引)
                    chosen_option_idx_in_list = calculate_choice_from_weights(weights)

                    selected_option_data = None
                    if chosen_option_idx_in_list != -1:
                         selected_option_data = options_parsed[chosen_option_idx_in_list]
                    elif options_parsed: # 权重选择失败，随机选一个
                         self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (类型 {q_type}): 权重配置 '{raw_weights_str}' 无效或选择失败，随机选择一个选项。")
                         selected_option_data = random.choice(options_parsed)

                    # 如果成功选定了选项
                    if selected_option_data:
                        # 设置操作类型和目标选项的原始索引（在HTML结构中的1-based索引）
                        instruction["action"] = "click" if q_type != "7" else "dropdown_select";
                        instruction["target_original_index"] = selected_option_data.get("original_index")

                        # 如果被选中的是“其他”选项，并且配置了自定义文本
                        # 这里需要检查 option_data 中是否有 enable_other_text_input 标记和 raw_other_text_input 内容
                        if selected_option_data.get("is_other_specify") and selected_option_data.get("enable_other_text_input", False):
                            raw_texts_for_other = selected_option_data.get("raw_other_text_input", "")
                            if raw_texts_for_other:
                                # 按||分隔自定义文本，随机选择一个
                                possible_other_texts = [ans.strip() for ans in raw_texts_for_other.split(_FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM) if ans.strip()]
                                if possible_other_texts:
                                    instruction["other_text_to_fill"] = random.choice(possible_other_texts)
                                    instruction["requires_other_text_fill"] = True # 标记需要填写“其他”文本
                                    # 如果parser为"其他"项提供了文本框定位信息，也传递过去 (主要针对下拉框)
                                    if selected_option_data.get("other_input_locator"):
                                         instruction["other_input_locator"] = selected_option_data["other_input_locator"]
                                    if selected_option_data.get("other_input_tag"):
                                         instruction["other_input_tag"] = selected_option_data["other_input_tag"]
                                else:
                                    self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 选定了其他项，但配置的自定义文本为空或无效。")
                        fill_instructions.append(instruction)
                    else:
                        self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (类型 {q_type}): 无选项可选或选择逻辑出错，跳过。")

                else:
                    self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (类型 {q_type}): 未解析到选项或配置无效，跳过。")

            # --- 多选题 (类型 4) ---
            # 多选题根据概率选择多个选项，并强制包含必选项
            elif q_type == "4":
                if options_parsed:
                    raw_probs_str = q_template.get("raw_prob_input", "");

                    selected_original_indices_set = set() # 使用集合存储选中的原始索引，避免重复
                    selected_options_data_list = [] # 存储被选中的选项数据，用于后续生成指令和处理“其他”项

                    # 1. 处理必选选项
                    required_options_data = [opt for opt in options_parsed if opt.get("must_select", False)]
                    for opt_data in required_options_data:
                        # 确保必选选项有 original_index
                        if opt_data.get("original_index") is not None:
                             selected_original_indices_set.add(opt_data["original_index"])
                             selected_options_data_list.append(opt_data)
                        else:
                             self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 标记为必选的选项缺少原始索引，无法选中。选项文本: {opt_data.get('text', '无文本')}")


                    # 2. 处理非必选选项 (根据概率随机选择)
                    non_required_options_data = [opt for opt in options_parsed if not opt.get("must_select", False)]
                    if non_required_options_data:
                        # 解析所有选项的概率，需要与 options_parsed 列表中的选项顺序对应
                        try:
                            percentages_str_list = [p.strip() for p in raw_probs_str.split(',') if p.strip()]
                            # 转换为整数列表，支持小数
                            all_percentages = []
                            for p_str in percentages_str_list:
                                try:
                                    p_float = float(p_str)
                                    if 0 <= p_float <= 1:
                                        all_percentages.append(int(p_float * 100))
                                    else:
                                        all_percentages.append(int(p_float)) # 假设是 0-100 的整数
                                except ValueError:
                                    raise ValueError("Non-digit found in probability string")

                            if len(all_percentages) != len(options_parsed):
                                raise ValueError("Probability count mismatch")

                            # 对非必选选项进行概率选择
                            # 可以重新构建一个只包含非必选选项及其对应概率的列表，然后调用 calculate_multiple_choices_from_percentages
                            # 或者直接遍历 options_parsed 并根据索引获取概率，然后判断非必选的选项是否选中
                            # 采用第二种方式，直接遍历 options_parsed 并使用索引查找概率
                            for i, opt_data in enumerate(options_parsed):
                                if not opt_data.get("must_select", False): # 只处理非必选选项
                                    try:
                                        # 新逻辑：检查“其它”选项是否满足选择条件
                                        is_other_option = opt_data.get("is_other_specify", False)
                                        has_other_text = opt_data.get("raw_other_text_input", "").strip()
                                        
                                        # 如果是“其它”选项，但没有勾选“必选”且没有填写文本，则强制不选中
                                        if is_other_option and not has_other_text:
                                            continue # 跳过这个选项的概率判断

                                        # 获取此非必选选项对应的概率
                                        prob = all_percentages[i]
                                        # 进行概率判断
                                        if random.randint(1, 100) <= prob:
                                            # 如果选中，添加到集合和列表中
                                            if opt_data.get("original_index") is not None:
                                                if opt_data["original_index"] not in selected_original_indices_set: # 集合会自动去重
                                                     selected_original_indices_set.add(opt_data["original_index"])
                                                     selected_options_data_list.append(opt_data)
                                            else:
                                                 self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 非必选选项缺少原始索引，无法选中。选项文本: {opt_data.get('text', '无文本')}")

                                    except IndexError: # 概率列表索引越界
                                        self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 概率配置数量与选项数量不匹配。")
                                        break
                                    except Exception as e_prob_select: # 其他概率选择错误
                                        self._emit_progress("error", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 非必选概率选择出错: {e_prob_select}")


                        except Exception as e_parse_prob: # 概率字符串解析失败或数量不匹配
                            self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 多选概率配置 '{raw_probs_str}' 错误/不匹配，随机选择非必选选项。错误: {e_parse_prob}")
                            # 回退到随机选择一定数量的非必选选项
                            num_non_required_to_select = random.randint(0, max(0, len(non_required_options_data))) # 随机选择0到非必选选项总数之间的数量
                            selected_non_required = random.sample(non_required_options_data, min(num_non_required_to_select, len(non_required_options_data))) # 随机抽取非必选选项数据
                            for opt_data in selected_non_required:
                                if opt_data.get("original_index") is not None:
                                     if opt_data["original_index"] not in selected_original_indices_set: # 集合去重
                                         selected_original_indices_set.add(opt_data["original_index"])
                                         selected_options_data_list.append(opt_data)
                                else:
                                     self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 随机选中的非必选选项缺少原始索引，无法选中。选项文本: {opt_data.get('text', '无文本')}")


                    # 3. 为所有选中的选项（必选 + 随机非必选）生成点击指令
                    if not selected_options_data_list:
                        self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 未选中任何选项 (无必选，随机也未选中)，跳过。")
                    else:
                         # 对选中的选项列表按原始索引排序（可选，使得指令顺序一致）
                        selected_options_data_list.sort(key=lambda x: x.get("original_index", 0))

                        for selected_opt_data in selected_options_data_list:
                             multi_choice_instruction = instruction_base.copy();
                             multi_choice_instruction["action"] = "click" # 多选操作是点击
                             # 目标选项的原始索引（在HTML结构中的1-based索引）
                             multi_choice_instruction["target_original_index"] = selected_opt_data.get("original_index")

                             # 如果被选中的是“其他”选项，并且配置了自定义文本
                             if selected_opt_data.get("is_other_specify") and selected_opt_data.get("enable_other_text_input", False):
                                 raw_texts_for_other = selected_opt_data.get("raw_other_text_input", "")
                                 if raw_texts_for_other:
                                     # 按||分隔自定义文本，随机选择一个
                                     possible_other_texts = [ans.strip() for ans in raw_texts_for_other.split(_FILL_IN_BLANK_SEPARATOR_FOR_WORKER_RANDOM) if ans.strip()]
                                     if possible_other_texts:
                                         multi_choice_instruction["other_text_to_fill"] = random.choice(possible_other_texts)
                                         multi_choice_instruction["requires_other_text_fill"] = True # 标记需要填写“其他”文本
                                         # 如果parser提供了文本框定位信息，传递过去
                                         if selected_opt_data.get("other_input_locator"):
                                              multi_choice_instruction["other_input_locator"] = selected_opt_data["other_input_locator"]
                                         if selected_opt_data.get("other_input_tag"):
                                              multi_choice_instruction["other_input_tag"] = selected_opt_data["other_input_tag"]
                                     else:
                                         self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 选定了其他项 ({selected_opt_data.get('original_index')})，但配置的自定义文本为空或无效。")

                             # 只有当 original_index 有效时才添加指令
                             if multi_choice_instruction["target_original_index"] is not None:
                                fill_instructions.append(multi_choice_instruction) # 添加指令到列表
                             else:
                                 self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (多选): 选中的选项缺少原始索引，跳过生成指令。选项文本: {selected_opt_data.get('text', '无文本')}")

                else: # 问题没有解析到任何选项
                     self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (类型 {q_type}): 未解析到选项或配置无效，跳过。")


            # --- 矩阵题 (类型 6) ---
            # 矩阵题为每个子问题根据权重选择一个选项
            elif q_type == "6":
                sub_questions_raw_configs = q_template.get("sub_questions_raw_configs", []) # 从模板获取子问题配置 (包含用户输入和parser数据)
                # 确保获取到的是列表
                if not isinstance(sub_questions_raw_configs, list) or not sub_questions_raw_configs:
                     self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} (类型 {q_type}): 未解析到子问题配置或配置无效，跳过。")
                     continue

                for sub_q_config in sub_questions_raw_configs:
                    sub_q_parsed_data = sub_q_config.get("sub_q_parsed_data", {}) # 获取parser提供的子问题原始数据
                    sub_q_options_parsed = sub_q_parsed_data.get("options", []) # 获取子问题的选项数据

                    # 检查子问题原始数据和选项是否存在
                    if not sub_q_parsed_data or not sub_q_options_parsed:
                        self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (原始索引 {sub_q_parsed_data.get('original_index', '未知')}): 缺少原始解析数据或未解析到选项，跳过。")
                        continue

                    raw_sub_q_weights_str = sub_q_config.get("raw_weight_input", "") # 获取用户输入的权重字符串
                    # 解析子问题权重，获取数字权重列表
                    sub_q_weights = parse_weights_from_string(raw_sub_q_weights_str, len(sub_q_options_parsed));
                    # 根据权重选择一个子问题选项的索引 (在 sub_q_options_parsed 列表中的索引)
                    chosen_sub_q_opt_idx = calculate_choice_from_weights(sub_q_weights)

                    selected_sub_q_opt_data = None
                    if chosen_sub_q_opt_idx != -1:
                         selected_sub_q_opt_data = sub_q_options_parsed[chosen_sub_q_opt_idx]
                    elif sub_q_options_parsed: # 权重选择失败，随机选一个
                         self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (原始索引 {sub_q_parsed_data.get('original_index', '未知')}): 权重配置 '{raw_sub_q_weights_str}' 无效或选择失败，随机选择一个选项。")
                         selected_sub_q_opt_data = random.choice(sub_q_options_parsed)

                    # 如果成功选定了子问题选项
                    if selected_sub_q_opt_data:
                         # 构建矩阵子问题点击指令
                        matrix_sub_instruction = instruction_base.copy();
                        matrix_sub_instruction["action"] = "matrix_click" # 矩阵题操作是点击
                        # 子问题行元素的ID前缀，用于定位行（从parser原始数据中获取）
                        matrix_sub_instruction["sub_q_id_prefix"] = sub_q_parsed_data.get("id_prefix", f"matrix_{q_topic_num}_sub_{sub_q_parsed_data.get('original_index', '未知')}")
                        # 子问题在整个子问题列表中的原始索引 (如果需要，从parser原始数据中获取)
                        matrix_sub_instruction["sub_q_original_index"] = sub_q_parsed_data.get("original_index")
                        # 被选中的子问题选项的原始索引（在HTML结构中的1-based索引，相对于子问题行）
                        matrix_sub_instruction["target_original_index"] = selected_sub_q_opt_data.get("original_index")

                        # 只有当 sub_q_id_prefix 和 target_original_index 都有效时才添加指令
                        if matrix_sub_instruction["sub_q_id_prefix"] and matrix_sub_instruction["target_original_index"] is not None:
                             fill_instructions.append(matrix_sub_instruction) # 添加指令
                        else:
                             self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (原始索引 {sub_q_parsed_data.get('original_index', '未知')}): 缺少 ID 前缀或选项原始索引，跳过生成指令。")

                    else:
                         self._emit_progress("warn", f"线程 {self.worker_id}: 题 {q_topic_num} 子问题 (原始索引 {sub_q_parsed_data.get('original_index', '未知')}): 无选项可选或选择逻辑出错，跳过。")


            # --- 排序题 (类型 11) ---
            # 排序题只需要标记进行随机排序，无需选择具体顺序，逻辑由填写类处理
            elif q_type == "11":
                # 检查是否有可排序的选项
                if options_parsed and len(options_parsed) > 1: # 至少需要两个选项才能排序
                    instruction = instruction_base.copy();
                    instruction["action"] = "sort_random"; # 操作是随机排序
                    # 存储解析到的排序项数据 (如果需要，虽然逻辑在WJXFillLogic中直接获取)
                    # instruction["sortable_options_parsed"] = options_parsed # parser获取的选项数据
                    fill_instructions.append(instruction)
                else:
                     self._emit_progress("info", f"线程 {self.worker_id}: 题 {q_topic_num} (排序): 项目数不足 ({len(options_parsed) if options_parsed else 0})，无需排序。")


            else:
                # 其他不支持配置或无需配置的题型，不生成指令，由填写逻辑类决定是否跳过
                self._emit_progress("info", f"线程 {self.worker_id}: 题 {q_topic_num} (类型 {q_type}): 此题型不支持详细配置或无需配置，跳过指令生成。")
                pass # 不生成指令

        # 如果没有生成任何填写指令，发送警告
        if not fill_instructions and raw_configs_template:
             self._emit_progress("warn",
                                f"线程 {self.worker_id}: 未能根据配置模板生成任何填写指令。这可能意味着所有题目都无法配置或已被过滤。")
        elif fill_instructions:
             self._emit_progress("debug", f"线程 {self.worker_id}: 成功生成 {len(fill_instructions)} 条填写指令。")

        return fill_instructions # 返回生成的指令列表

    def run(self):
        """
        工作线程的主执行循环，负责多次填写问卷。
        """
        self._emit_progress("info",
                            f"线程 {self.worker_id} ({self.browser_type}, {'无头' if self.headless else '有头'}) 启动。目标份数: {self.num_fills_to_complete_by_worker}")

        # 外层循环：控制本线程要完成的填写份数
        while self.fills_completed_by_this_worker < self.num_fills_to_complete_by_worker and self.is_running:
            # 确保 WebDriver 已初始化
            if not self.driver: # 只在第一次或 driver 关闭后需要重新初始化
                 if not self._initialize_driver():
                    # Driver 初始化失败，_initialize_driver 中已发出错误信号并设置 is_running=False
                    break # 初始化失败，退出主循环

            # 为本次填写生成具体的操作指令列表
            # 这个列表每份填写都会重新生成，以实现随机性（除了顺序填空）
            self.fill_config_instructions = self._generate_randomized_instructions(
                self.user_raw_configurations_template)

            # 如果指令生成失败或为空，跳过本次填写
            if not self.fill_config_instructions:
                self._emit_progress("error", f"线程 {self.worker_id}: 无法为此填写尝试生成指令 (指令列表为空)，跳过本次填写。")
                # 发射单次填写完成信号（失败）
                self.single_fill_finished_signal.emit(self.worker_id, False, f"线程 {self.worker_id}: 指令生成失败或为空")
                # 短暂休息后继续尝试下一份，但只有在仍运行时才休息
                if self.is_running: time.sleep(random.uniform(2, 5));
                continue # 继续外层循环，尝试下一份填写


            # 标记本次填写是否成功
            current_fill_success = False
            final_message_or_url = "未知原因失败"
            initial_url = self.url # 保存初始URL用于对比判断提交结果

            try:
                self._emit_progress("info",
                                    f"线程 {self.worker_id}: 开始第 {self.fills_completed_by_this_worker + 1} 次填写...")
                # 打开问卷URL
                self.driver.get(initial_url)
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.ID, "divQuestion")))
                self._emit_progress("debug", f"线程 {self.worker_id}: 问卷页面加载完成。")
                time.sleep(random.uniform(1.5, 3.0))

                # 创建并执行填写逻辑
                self._fill_logic = WJXFillLogic(
                    driver=self.driver,
                    worker_id=self.worker_id,
                    log_callback=self._emit_progress,
                    is_running_check=lambda: self.is_running,
                    is_paused_check=lambda: self.is_paused,
                    shared_sequential_indices=self._shared_sequential_indices,
                    sequential_indices_mutex=self._sequential_indices_mutex,
                    slow_mode=self.slow_mode,
                    human_like_mode_config=self.human_like_mode_config
                )

                self._emit_progress("info", f"线程 {self.worker_id}: 开始按指令填写 {len(self.fill_config_instructions)} 个题目...")
                for instruction in self.fill_config_instructions:
                    while self.is_paused and self.is_running:
                        time.sleep(0.1)
                    if not self.is_running:
                        raise InterruptedError("用户中止操作")
                    
                    # 调用填写逻辑，并检查其返回值
                    success = self._fill_logic.process_instruction(instruction)
                    if not success:
                        # 如果 process_instruction 返回 False，可能意味着需要人工干预验证码
                        # 在 WJXFillLogic 中，当AI处理失败时，它会返回 False
                        # Worker 在这里捕获这个状态，并暂停自己
                        self._emit_progress("captcha_failed", f"线程 {self.worker_id}: AI验证码处理失败，线程暂停等待人工操作。")
                        self.pause() # 暂停当前线程
                        # 可以在这里持续循环等待，直到 is_paused 变为 False
                        while self.is_paused and self.is_running:
                            time.sleep(0.5)
                        
                        # 如果线程被用户继续，再次检查验证码是否已解决
                        if self.is_running:
                            self._emit_progress("info", f"线程 {self.worker_id}: 用户已继续，重新检查页面状态...")
                            # 重新执行一次验证码检查，以确认人工操作是否完成
                            if not self._fill_logic._handle_captcha():
                                self._emit_progress("error", f"线程 {self.worker_id}: 人工操作后验证码仍存在或处理失败，跳过本次填写。")
                                raise ValueError("Captcha still present after manual intervention.") # 抛出异常以终止本次填写

                if not self.is_running: raise InterruptedError("用户中止操作")

                # 分页处理
                while self.is_running:
                    try:
                        next_page_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.ID, "divNextPage")))
                        if next_page_button.is_displayed() and next_page_button.is_enabled():
                            self._emit_progress("info", f"线程 {self.worker_id}: 点击下一页...")
                            next_page_button.click()
                            WebDriverWait(self.driver, 10).until(EC.staleness_of(next_page_button))
                            time.sleep(random.uniform(1.0, 2.0))
                        else:
                            break
                    except (NoSuchElementException, TimeoutException):
                        break

                if not self.is_running: raise InterruptedError("用户中止操作")

                # 提交
                self._emit_progress("info", f"线程 {self.worker_id}: 尝试提交...")
                submit_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="ctlNext"]')))
                self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", submit_button)
                time.sleep(0.5)
                try:
                    submit_button.click()
                except ElementClickInterceptedException:
                    self.driver.execute_script("arguments[0].click();", submit_button)

                time.sleep(1.0)

                # 提交后确认和验证码处理
                try:
                    confirm_button = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH,
                                                                                                     "//div[contains(@class,'layui-layer-btn')]/a[normalize-space()='确定' or normalize-space()='确认' or normalize-space()='是的']")))
                    confirm_button.click()
                    time.sleep(1.5)
                except (TimeoutException, NoSuchElementException):
                    pass # 忽略

                try:
                    verify_button = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//*[@id='SM_BTN_1' or contains(@class, 'sm-btn')]")))
                    verify_button.click()
                    time.sleep(3.0)
                except (TimeoutException, NoSuchElementException):
                    pass # 忽略

                # 滑块验证
                try:
                    slider_area_xpath = '//*[@id="nc_1__scale_text"]/span | //div[@id="nc_1_n1t"]'
                    WebDriverWait(self.driver, 7).until(EC.presence_of_element_located((By.XPATH, slider_area_xpath)))
                    slider_button_xpath = '//*[@id="nc_1_n1z"]'
                    slider_button_el = self.driver.find_element(By.XPATH, slider_button_xpath)
                    self._emit_progress("captcha", f"线程 {self.worker_id}: 检测到滑块验证...")
                    
                    total_drag_target = random.randint(265, 295)
                    actions_slider = ActionChains(self.driver)
                    actions_slider.click_and_hold(slider_button_el).perform()
                    
                    # 模拟拖动
                    num_segments = random.randint(5, 10)
                    for i in range(num_segments):
                        if not self.is_running: break
                        ratio = (i + 1) / num_segments
                        target_x = total_drag_target * ratio
                        current_x = (i / num_segments) * total_drag_target
                        move_x = target_x - current_x + random.uniform(-3, 3)
                        move_y = random.uniform(-5, 5)
                        actions_slider.move_by_offset(xoffset=move_x, yoffset=move_y)
                        actions_slider.pause(random.uniform(0.05, 0.2))
                    
                    actions_slider.release().perform()
                    self._emit_progress("info", f"线程 {self.worker_id}: 滑块验证尝试完成。")
                    time.sleep(3) # 等待验证结果
                except (TimeoutException, NoSuchElementException):
                    self._emit_progress("debug", f"线程 {self.worker_id}: 未检测到滑块验证码。")
                except Exception as e_slider:
                    self._emit_progress("warn", f"线程 {self.worker_id}: 处理滑块验证时发生错误: {e_slider}")

                # 检查结果
                time.sleep(random.uniform(2.5, 4.0))
                final_url = self.driver.current_url
                if "Finish" in final_url or "finish" in final_url or "finished" in final_url or "completemobile" in final_url:
                    current_fill_success = True
                    final_message_or_url = final_url
                    self._emit_progress("success_once", f"线程 {self.worker_id}: 第 {self.fills_completed_by_this_worker + 1} 次填写成功。")
                else:
                    # 检查是否有错误提示
                    try:
                        error_element = self.driver.find_element(By.XPATH, "//*[contains(@class, 'w-error-v2') or contains(@class, 'w-tip-error')]")
                        error_text = error_element.text.strip() if error_element.text else "未知提交错误"
                        final_message_or_url = f"线程 {self.worker_id}: 提交失败: {error_text}"
                        self._emit_progress("error", final_message_or_url)
                    except (NoSuchElementException, TimeoutException):
                        final_message_or_url = f"线程 {self.worker_id}: 提交后页面未跳转到成功页，且未找到明确错误提示。URL: {final_url}"
                        self._emit_progress("warn", final_message_or_url)
            
            except InterruptedError:
                final_message_or_url = f"线程 {self.worker_id}: 用户中止操作"
                self._emit_progress("warn", final_message_or_url)
                # is_running 已经是 False, 循环会自动终止
            except ValueError as ve: # 捕获我们自己抛出的验证码处理异常
                final_message_or_url = f"线程 {self.worker_id}: {ve}"
                self._emit_progress("error", final_message_or_url)
                current_fill_success = False
            except Exception as e:
                final_message_or_url = f"线程 {self.worker_id}: 填写或提交过程中发生严重错误: {type(e).__name__} - {e}"
                self._emit_progress("error", f"{final_message_or_url}\n{traceback.format_exc()}")
                current_fill_success = False
            finally:
                # 无论成功与否，都更新计数并发送单次完成信号
                if current_fill_success:
                    self.fills_completed_by_this_worker += 1
                
                self.single_fill_finished_signal.emit(self.worker_id, current_fill_success, final_message_or_url)

                # 如果线程未被外部停止，且未达到目标份数，则短暂休息后继续
                if self.is_running and self.fills_completed_by_this_worker < self.num_fills_to_complete_by_worker:
                    sleep_duration = random.uniform(3, 7) if not self.slow_mode else random.uniform(7, 15)
                    self._emit_progress("debug", f"线程 {self.worker_id}: 单次完成，休息 {sleep_duration:.1f} 秒后继续...")
                    time.sleep(sleep_duration)
