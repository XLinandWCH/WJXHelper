# questionnaire_parser.py
import time
import re
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup  # 引入BS4辅助解析

# !!! 重要: 你需要下载 msedgedriver.exe 并将其路径配置到系统PATH，
# !!! 或者在下面代码中显式指定路径。
# !!! 例如: MSEDGEDRIVER_PATH = "C:/path/to/msedgedriver.exe"
MSEDGEDRIVER_PATH = "C:/Users/xlina/Desktop/WJXHelper/msedgedriver.exe"  # 设置为 None 则尝试从PATH查找


def fetch_questionnaire_structure(url, msedgedriver_path=None):
    """
    使用 Selenium (headless Edge) 获取问卷结构。
    返回一个问题列表，每个问题是一个字典，包含:
    'id', 'type_code', 'topic_num', 'text', 'options', 'sub_questions'
    """
    global MSEDGEDRIVER_PATH  # 允许函数外部修改路径
    if msedgedriver_path:
        MSEDGEDRIVER_PATH = msedgedriver_path

    edge_options = EdgeOptions()
    edge_options.use_chromium = True  # 必须，因为新版Edge基于Chromium
    edge_options.add_argument("--headless")
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument("--no-sandbox")
    edge_options.add_argument("--disable-dev-shm-usage")
    # 避免被检测为自动化工具
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option('useAutomationExtension', False)
    # 有些网站会检测 navigator.webdriver
    edge_options.add_argument('--disable-blink-features=AutomationControlled')

    if MSEDGEDRIVER_PATH:
        service = EdgeService(executable_path=MSEDGEDRIVER_PATH)
        driver = webdriver.Edge(service=service, options=edge_options)
    else:
        try:
            # 尝试从系统PATH自动查找msedgedriver
            driver = webdriver.Edge(options=edge_options)
        except Exception as e:
            print(f"启动EdgeDriver失败，请确保msedgedriver.exe在系统PATH中，或在代码中指定其路径。错误: {e}")
            return None

    # 再次尝试隐藏webdriver属性，cdp命令在新版selenium中可能需要调整
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                  get: () => undefined
                });
                Object.defineProperty(navigator, 'languages', {
                  get: () => ['zh-CN', 'zh']
                });
                Object.defineProperty(navigator, 'plugins', {
                  get: () => [1, 2, 3, 4, 5],
                });
            """
        })
    except Exception as e:
        print(f"执行CDP命令失败 (可能不影响，但提示一下): {e}")

    questions_data = []
    try:
        driver.get(url)
        # 等待页面JS执行和元素加载，时间可以适当调整
        # 对于复杂的问卷星页面，可能需要更智能的等待条件 WebDriverWait
        time.sleep(3)  # 增加等待时间

        # 定位所有问题容器 (这是核心，需要根据问卷星实际HTML结构调整)
        # 原始脚本的 XPath: //*[@id="divQuestion"]/fieldset  然后  .//div[@topic]
        # 我们尝试更直接地找带 topic 属性的 div
        # 示例问卷星的结构: div.field.ui-field-contain

        # 使用 driver.find_elements 定位，而不是BeautifulSoup，因为JS动态内容
        # 这是一个通用尝试，实际问卷星的class可能更复杂或有版本变化
        # q_divs = driver.find_elements(By.XPATH, "//div[starts-with(@id, 'div') and @topic]")
        # 你的示例代码用的是: //*[@id="fieldset{i}"]/div  (分页)
        # 我们先尝试获取所有fieldset，再遍历其中的问题

        fieldsets = driver.find_elements(By.XPATH, '//*[@id="divQuestion"]/fieldset')
        if not fieldsets:  # 如果没有分页的fieldset，尝试直接找问题div
            fieldsets = [driver.find_element(By.ID, 'divQuestion')]  # 将整个问卷视为一个fieldset

        current_question_number_overall = 0  # 追踪问题的绝对序号

        for fieldset_index, fieldset in enumerate(fieldsets):
            # 在每个fieldset中查找问题
            # 问题通常是fieldset下的直接子div，并且有 'topic' 属性
            question_elements_in_fieldset = fieldset.find_elements(By.XPATH, "./div[@topic]")

            for q_element in question_elements_in_fieldset:
                current_question_number_overall += 1
                q_id_attr = q_element.get_attribute("id")  # 例如: div1, div2
                q_topic_attr = q_element.get_attribute("topic")  # 例如: 1, 2, ... (题号)
                q_type_attr = q_element.get_attribute("type")  # 例如: 3 (单选), 4 (多选)

                if not q_topic_attr or not q_topic_attr.isdigit():
                    print(f"跳过无效元素: id='{q_id_attr}', topic='{q_topic_attr}'")
                    continue

                question_info = {
                    "id": q_id_attr,
                    "topic_num": q_topic_attr,
                    "type_code": q_type_attr,
                    "text": f"题目 {q_topic_attr}",  # 默认文本
                    "options": [],
                    "sub_questions": [],  # 用于矩阵题
                    "page_index": fieldset_index + 1,  # 属于第几页
                    "question_index_overall": current_question_number_overall  # 绝对题号
                }

                # 1. 获取问题文本
                try:
                    # 优先找 .field-label 或 .matrix-title (更精确)
                    title_element = q_element.find_element(By.XPATH,
                                                           ".//div[contains(@class, 'field-label') or contains(@class, 'matrix-title') or contains(@class, 'slider-title')]")
                    # 移除题号前缀，例如 "1. 您..." -> "您..."
                    raw_text = title_element.text.strip()
                    # 使用正则表达式移除可能的 "数字. " 或 "数字、" 前缀
                    cleaned_text = re.sub(r"^\d+[\s.、]*", "", raw_text).strip()
                    question_info["text"] = cleaned_text if cleaned_text else raw_text  # 如果清理后为空，用原始的
                except NoSuchElementException:
                    # 如果找不到特定标签，尝试获取整个 q_element 的文本，并做些清理
                    try:
                        full_text = q_element.text.split('\n')[0].strip()  # 取第一行
                        cleaned_text = re.sub(r"^\d+[\s.、]*", "", full_text).strip()
                        question_info["text"] = cleaned_text if cleaned_text else f"问题 {q_topic_attr} (标题提取失败)"
                    except:
                        pass  # 保持默认文本

                # 2. 根据题型解析选项
                if q_type_attr in ["3", "4", "5"]:  # 单选, 多选, 量表题
                    # 选项通常在 .ui-controlgroup > div 内，或者 ul > li 内
                    option_containers = []
                    try:
                        # 优先尝试 .ui-controlgroup (常见于单选/多选)
                        option_containers = q_element.find_elements(By.XPATH,
                                                                    f".//div[contains(@class, 'ui-controlgroup')]/div[starts-with(@class, 'ui-radio') or starts-with(@class, 'ui-checkbox')]")
                    except NoSuchElementException:
                        pass

                    if not option_containers:  # 尝试 ul > li (常见于量表题或某些自定义选项)
                        try:
                            # 量表题的选项可能在 .scale-div ul li
                            # 你的脚本用的是: #div{current} > div.scale-div > div > ul > li:nth-child({b})
                            # 更通用的: .//div[contains(@class,'scale-div')]//ul/li
                            option_containers = q_element.find_elements(By.XPATH,
                                                                        ".//div[contains(@class,'scale-div')]//ul/li[contains(@class,'scale-item') or contains(@class,'rating-item') or not(@class)]")  # 添加not(@class)以匹配无class的li
                        except NoSuchElementException:
                            pass

                    if not option_containers:  # 再尝试一种通用的查找label的
                        try:
                            option_containers = q_element.find_elements(By.XPATH,
                                                                        ".//label[input[@type='radio' or @type='checkbox']]")
                        except:
                            pass

                    for opt_idx, opt_container in enumerate(option_containers):
                        opt_text = opt_container.text.strip()
                        # 尝试获取 input 的 value 作为 'value' (如果存在)
                        opt_val = str(opt_idx + 1)  # 默认用1-based索引
                        try:
                            input_el = opt_container.find_element(By.XPATH,
                                                                  ".//input[@type='radio' or @type='checkbox' or @type='text']")  # type text用于某些特殊量表
                            val_attr = input_el.get_attribute('value')
                            if val_attr:
                                opt_val = val_attr
                        except NoSuchElementException:
                            pass

                        if opt_text:
                            question_info["options"].append({
                                "text": opt_text,
                                "value": opt_val,  # 可能是数字，也可能是文本值
                                "original_index": opt_idx + 1  # 界面上选项的1-based索引
                            })

                elif q_type_attr == "7":  # 下拉框
                    try:
                        # 下拉框的选项在 select > option
                        # 有时问卷星用 select2.js 动态生成，那种情况解析会更复杂
                        # 先尝试标准 select
                        select_element = q_element.find_element(By.XPATH, f".//select[@id='q{q_topic_attr}']")
                        option_elements = select_element.find_elements(By.TAG_NAME, "option")

                        # original_index 对应于 select 中 option 的顺序 (0-based for value, 1-based for UI display)
                        # select2.js 生成的列表项通常是 1-based
                        opt_display_idx = 0
                        for opt_el in option_elements:
                            opt_text = opt_el.text.strip()
                            opt_val = opt_el.get_attribute('value')
                            if opt_val:  # 跳过 "请选择" (value通常为空)
                                opt_display_idx += 1
                                question_info["options"].append({
                                    "text": opt_text,
                                    "value": opt_val,
                                    "original_index": opt_display_idx  # 下拉项在界面上的1-based索引
                                })
                    except NoSuchElementException:
                        question_info["text"] += " (下拉框解析失败或为动态)"
                    except Exception as e:
                        print(f"解析下拉框题目 {q_topic_attr} 选项时出错: {e}")


                elif q_type_attr == "6":  # 矩阵题
                    try:
                        # 子问题行: 通常在 tbody > tr (排除表头)
                        # 你的脚本: //*[@id="divRefTab{current}"]/tbody/tr
                        # 更通用: .//table[contains(@class,'matrix')]/tbody/tr
                        sub_q_rows = q_element.find_elements(By.XPATH,
                                                             ".//table[contains(@class,'matrix') or @class='tableitems']/tbody/tr[normalize-space(@class)='matrixNormalTr' or normalize-space(@class)='matrixRandomTr' or not(@class)]")  # not @class 用于某些简单表格

                        # 选项列 (表头): thead > tr > th
                        # 你的脚本: //*[@id="drv{current}_1"]/td (这是指具体某行的选项td, 不是表头)
                        # 我们需要表头来定义所有子问题的共享选项
                        header_option_elements = q_element.find_elements(By.XPATH,
                                                                         ".//table[contains(@class,'matrix') or @class='tableitems']/thead/tr/th")

                        matrix_shared_options = []
                        # 表头第一列通常是空的或者子问题标题列，所以选项从第二个th开始
                        start_col_index_for_options = 0
                        if header_option_elements and not header_option_elements[0].text.strip():  # 如果第一个th为空
                            start_col_index_for_options = 1

                        for opt_col_idx, th_element in enumerate(header_option_elements[start_col_index_for_options:]):
                            opt_text = th_element.text.strip()
                            if opt_text:
                                matrix_shared_options.append({
                                    "text": opt_text,
                                    "value": str(opt_col_idx + 1),  # 选项的1-based列索引 (相对于选项列)
                                    # original_index 将是td的nth-child, 所以是 opt_col_idx + 1 + start_col_index_for_options
                                    "original_index": opt_col_idx + 1 + start_col_index_for_options
                                })

                        if not matrix_shared_options:  # 如果从thead没拿到，尝试从第一行数据行的td结构推断
                            first_data_row_tds = q_element.find_elements(By.XPATH,
                                                                         ".//table[contains(@class,'matrix') or @class='tableitems']/tbody/tr[1]/td")
                            # 假设第一个td是行标题
                            if len(first_data_row_tds) > 1:
                                for td_idx, td_el in enumerate(first_data_row_tds[1:]):
                                    # 尝试从td内部的input[type=radio/checkbox]的aria-label或title获取选项文本（如果td本身没文本）
                                    try:
                                        input_in_td = td_el.find_element(By.XPATH,
                                                                         ".//input[@type='radio' or @type='checkbox']")
                                        aria_label = input_in_td.get_attribute(
                                            "aria-label") or input_in_td.get_attribute("title")
                                        opt_text = aria_label.strip() if aria_label else f"选项{td_idx + 1}"
                                    except:
                                        opt_text = f"选项{td_idx + 1}"

                                    matrix_shared_options.append({
                                        "text": opt_text,
                                        "value": str(td_idx + 1),
                                        "original_index": td_idx + 2  # td的nth-child(index) (第一个是行标题)
                                    })

                        for row_idx, sub_q_row_element in enumerate(sub_q_rows):
                            try:
                                # 子问题文本通常在第一个 td
                                sub_q_text_element = sub_q_row_element.find_element(By.XPATH, "./td[1]")
                                sub_q_text = sub_q_text_element.text.strip()
                                # 矩阵子问题的ID前缀，用于定位填写，例如 drv{TopicNum}_{SubQIdx}
                                # 这个ID是 tr 的 id (drv10_1)
                                sub_q_tr_id = sub_q_row_element.get_attribute("id")
                                if not sub_q_tr_id and sub_q_row_element.get_attribute("rowindex"):
                                    sub_q_tr_id = f"drv{q_topic_attr}_{sub_q_row_element.get_attribute('rowindex')}"
                                elif not sub_q_tr_id:  # 如果tr没有id，构造一个临时的
                                    sub_q_tr_id = f"matrix_{q_topic_attr}_row_{row_idx + 1}"

                                if sub_q_text and matrix_shared_options:
                                    question_info["sub_questions"].append({
                                        "text": sub_q_text,
                                        "options": matrix_shared_options,  # 共享选项
                                        "id_prefix": sub_q_tr_id,  # 用于定位该行
                                        "original_index": row_idx + 1  # 子问题在矩阵中的1-based行号
                                    })
                            except NoSuchElementException:
                                print(f"解析矩阵题 {q_topic_attr} 的子问题行 {row_idx + 1} 失败。")
                                continue
                    except Exception as e:
                        print(f"解析矩阵题 {q_topic_attr} 时出错: {e}")
                        question_info["text"] += " (矩阵题解析可能不完整)"

                elif q_type_attr == "1" or q_type_attr == "2":  # 填空题
                    question_info["text"] += " (填空题)"
                    # 填空题没有预设选项，但可以定义一个结构让用户输入
                    question_info["options"] = [{"text": "请在此输入答案", "value": "text_input", "original_index": 1}]

                elif q_type_attr == "8":  # 滑块题
                    question_info["text"] += " (滑块题, 请输入1-100的值)"
                    # 滑块题通常对应一个 input type=text 或 hidden，ID为 q{topic_num}
                    # 我们可以把它当做一个特殊的填空题处理
                    question_info["options"] = [
                        {"text": "滑块值 (1-100)", "value": "slider_input", "original_index": 1}]

                elif q_type_attr == "11":  # 排序题
                    question_info["text"] += " (排序题, 将自动随机排序)"
                    # 排序题的选项是 li 元素，程序将随机点击它们
                    # 解析出可排序项的文本可以帮助用户理解，但配置权重较复杂
                    try:
                        sortable_items = q_element.find_elements(By.XPATH, ".//ul[contains(@class,'sortable')]/li")
                        for s_idx, s_item in enumerate(sortable_items):
                            s_text = s_item.text.strip()
                            if s_text:
                                question_info["options"].append({
                                    "text": s_text,
                                    "value": str(s_idx + 1),
                                    "original_index": s_idx + 1
                                })
                    except:
                        pass  # 解析失败不影响后续随机排序

                # 只有包含有效信息的问题才添加
                # (有文本，并且是填空/滑块/排序，或者有选项，或者有子问题)
                is_valid_question = False
                if question_info["text"] and not question_info["text"].startswith("问题 "):  # 确保提取到有效标题
                    if q_type_attr in ["1", "2", "8", "11"]:  # 这些类型本身有效
                        is_valid_question = True
                    elif question_info["options"]:  # 选择类有选项
                        is_valid_question = True
                    elif q_type_attr == "6" and question_info["sub_questions"]:  # 矩阵有子问题
                        is_valid_question = True

                if is_valid_question:
                    questions_data.append(question_info)
                else:
                    print(
                        f"信息不足，跳过问题: ID={q_id_attr}, Topic={q_topic_attr}, Type={q_type_attr}, Text='{question_info['text']}', Options len={len(question_info['options'])}, SubQ len={len(question_info['sub_questions'])}")


    except TimeoutException:
        print(f"加载页面超时: {url}")
        return {"error": "页面加载超时"}
    except Exception as e:
        print(f"解析问卷时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"解析问卷时发生错误: {e}"}
    finally:
        if 'driver' in locals() and driver:
            driver.quit()

    if not questions_data:
        return {"error": "未能从问卷中解析出任何问题。请检查URL或选择器。"}

    return questions_data


if __name__ == '__main__':
    # 测试 (你需要一个有效的问卷星链接)
    # test_url = "https://www.wjx.cn/vm/xxxxxxx.aspx" # 替换成一个真实链接
    test_url_example = "https://www.wjx.cn/vm/PPiZFM2.aspx# "  # 你提供的示例问卷

    print(
        f"请确保已下载 msedgedriver.exe 并将其路径配置到系统PATH，或在 questionnaire_parser.py 中设置 MSEDGEDRIVER_PATH")
    print(f"正在尝试解析: {test_url_example}")

    # 如果想在测试时指定路径:
    # structure = fetch_questionnaire_structure(test_url_example, msedgedriver_path="C:/your/path/to/msedgedriver.exe")
    structure = fetch_questionnaire_structure(test_url_example)

    if isinstance(structure, dict) and "error" in structure:
        print(f"解析失败: {structure['error']}")
    elif structure:
        print(f"\n成功解析到 {len(structure)} 个问题:")
        for i, q in enumerate(structure):
            print(
                f"\n--- 问题 {q.get('question_index_overall', i + 1)} (页码: {q.get('page_index', 'N/A')}, 原始题号: {q.get('topic_num', 'N/A')}, 类型: {q.get('type_code', 'N/A')}) ---")
            print(f"  ID: {q['id']}")
            print(f"  文本: {q['text']}")
            if q.get("options"):
                print(f"  选项 ({len(q['options'])}):")
                for opt in q["options"]:
                    print(f"    - \"{opt['text']}\" (值: {opt['value']}, 原始HTML索引: {opt['original_index']})")
            if q.get("sub_questions"):
                print(f"  子问题 ({len(q['sub_questions'])}):")
                for sub_q_idx, sub_q in enumerate(q["sub_questions"]):
                    print(
                        f"    - 子问题 {sub_q_idx + 1}: \"{sub_q['text']}\" (ID前缀: {sub_q['id_prefix']}, 原始行索引: {sub_q['original_index']})")
                    if sub_q.get("options"):
                        print(f"      矩阵选项 ({len(sub_q['options'])}):")
                        for opt in sub_q["options"]:
                            print(
                                f"        - \"{opt['text']}\" (值: {opt['value']}, 原始HTML列索引: {opt['original_index']})")
    else:
        print("问卷解析失败或未返回任何问题。")