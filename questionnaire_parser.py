# questionnaire_parser.py
import time
import re
import os
import tempfile  # 新增
import shutil  # 新增
import random

from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import traceback  # 引入traceback


def fetch_questionnaire_structure(url, browser_type="edge", driver_executable_path=None,
                                  headless=True, base_user_data_dir_path=None):
    """
    使用 Selenium 获取问卷结构。
    url: 问卷链接。
    browser_type: "edge", "chrome", or "firefox".
    driver_executable_path: 对应浏览器驱动的路径。如果为None，Selenium会尝试从PATH查找。
    headless: 是否以无头模式运行。
    base_user_data_dir_path: 用于创建独立用户配置文件的基础路径。
    返回一个问题列表，或一个包含 "error" 键的字典。
    """
    print(f"解析器: 开始解析问卷: {url} 使用 {browser_type}")
    if driver_executable_path:
        print(f"解析器: 指定驱动路径: {driver_executable_path}")
    else:
        print(f"解析器: 未指定驱动路径，将从系统PATH查找 {browser_type} driver。")

    driver = None
    actual_user_data_dir_parser = None

    try:
        common_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36 Edg/90.0.818.66"
        common_cdp_script = """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """

        if browser_type in ["edge", "chrome"]:
            if base_user_data_dir_path and os.path.isdir(base_user_data_dir_path):
                actual_user_data_dir_parser = os.path.join(base_user_data_dir_path,
                                                           f"profile_parser_{random.randint(10000, 99999)}")
            else:
                actual_user_data_dir_parser = os.path.join(tempfile.gettempdir(),
                                                           f"wjx_parser_profile_{random.randint(10000, 99999)}")
            if os.path.exists(actual_user_data_dir_parser) and not os.path.isdir(actual_user_data_dir_parser):
                try:
                    os.remove(actual_user_data_dir_parser)
                except OSError:
                    pass
            os.makedirs(actual_user_data_dir_parser, exist_ok=True)
            print(f"解析器: 使用用户数据目录: {actual_user_data_dir_parser}")

        service = None
        if driver_executable_path and os.path.isfile(driver_executable_path):
            if browser_type == "edge":
                service = EdgeService(executable_path=driver_executable_path)
            elif browser_type == "chrome":
                service = ChromeService(executable_path=driver_executable_path)
            elif browser_type == "firefox":
                service = FirefoxService(executable_path=driver_executable_path)
        elif driver_executable_path:
            if browser_type == "edge":
                service = EdgeService(executable_path=driver_executable_path)
            elif browser_type == "chrome":
                service = ChromeService(executable_path=driver_executable_path)
            elif browser_type == "firefox":
                service = FirefoxService(executable_path=driver_executable_path)

        if browser_type == "edge":
            edge_options = EdgeOptions();
            edge_options.use_chromium = True
            if headless: edge_options.add_argument("--headless"); edge_options.add_argument("--disable-gpu")
            edge_options.add_argument("--no-sandbox");
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_options.add_experimental_option('useAutomationExtension', False)
            edge_options.add_argument('--disable-blink-features=AutomationControlled')
            edge_options.add_argument(f"user-agent={common_user_agent}")
            if actual_user_data_dir_parser: edge_options.add_argument(f"--user-data-dir={actual_user_data_dir_parser}")
            driver = webdriver.Edge(service=service, options=edge_options) if service else webdriver.Edge(
                options=edge_options)
        elif browser_type == "chrome":
            chrome_options = ChromeOptions()
            if headless: chrome_options.add_argument("--headless"); chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox");
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument(f"user-agent={common_user_agent}")
            if actual_user_data_dir_parser: chrome_options.add_argument(
                f"--user-data-dir={actual_user_data_dir_parser}")
            driver = webdriver.Chrome(service=service, options=chrome_options) if service else webdriver.Chrome(
                options=chrome_options)
        elif browser_type == "firefox":
            firefox_options = FirefoxOptions()
            if headless: firefox_options.add_argument("--headless")
            firefox_options.set_preference("dom.webdriver.enabled", False)
            firefox_options.set_preference('useAutomationExtension', False)
            firefox_options.profile.set_preference("general.useragent.override", common_user_agent)
            driver = webdriver.Firefox(service=service, options=firefox_options) if service else webdriver.Firefox(
                options=firefox_options)
        else:
            return {"error": f"不支持的浏览器类型: {browser_type}"}

        print(f"解析器: {browser_type.capitalize()} WebDriver 启动成功。")
        if browser_type in ["edge", "chrome"] and driver:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": common_cdp_script})

    except WebDriverException as wde:
        error_msg = (f"启动 {browser_type.capitalize()} Driver 失败 (WebDriverException)。\n"
                     f"请确保驱动程序版本与浏览器匹配，并在“程序设置”中指定正确路径或将其添加到系统PATH。\n"
                     f"尝试路径: {driver_executable_path if driver_executable_path else '系统PATH'}\n"
                     f"具体错误: {str(wde).splitlines()[0]}")
        print(f"解析器: {error_msg}")
        if driver: driver.quit()
        if actual_user_data_dir_parser and os.path.exists(actual_user_data_dir_parser):
            try:
                shutil.rmtree(actual_user_data_dir_parser, ignore_errors=True)
            except Exception:
                pass
        return {"error": error_msg}
    except Exception as e:
        error_msg = (f"启动 {browser_type.capitalize()} Driver 时发生未知错误。\n"
                     f"具体错误: {type(e).__name__} - {e}")
        print(f"解析器: {error_msg}")
        if driver: driver.quit()
        if actual_user_data_dir_parser and os.path.exists(actual_user_data_dir_parser):
            try:
                shutil.rmtree(actual_user_data_dir_parser, ignore_errors=True)
            except Exception:
                pass
        return {"error": error_msg}

    questions_data = []
    try:
        print(f"解析器: 正在打开URL: {url}")
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "divQuestion")))
        print("解析器: 核心问卷区域 'divQuestion' 已加载。")

        fieldsets = driver.find_elements(By.XPATH, '//*[@id="divQuestion"]/fieldset')
        if not fieldsets:
            print("解析器: 未找到分页的fieldset，尝试将整个 'divQuestion' 视为一个fieldset。")
            div_question_element = driver.find_elements(By.ID, 'divQuestion')
            if div_question_element:
                fieldsets = div_question_element
            else:
                return {"error": "页面结构异常，未找到核心问卷容器 'divQuestion'。"}

        current_question_number_overall = 0
        print(f"解析器: 找到 {len(fieldsets)} 个fieldset (页面部分)。")

        for fieldset_index, fieldset in enumerate(fieldsets):
            print(f"解析器: 正在处理 Fieldset {fieldset_index + 1}...")
            question_elements_in_fieldset = fieldset.find_elements(By.XPATH, "./div[@topic]")
            print(f"解析器: Fieldset {fieldset_index + 1} 中找到 {len(question_elements_in_fieldset)} 个问题元素。")

            for q_element in question_elements_in_fieldset:
                current_question_number_overall += 1
                q_id_attr = q_element.get_attribute("id")
                q_topic_attr = q_element.get_attribute("topic")
                q_type_attr = q_element.get_attribute("type")
                print(f"  解析器: 解析原始题目信息: ID={q_id_attr}, Topic={q_topic_attr}, Type={q_type_attr}")
                if not q_topic_attr or not q_topic_attr.isdigit():
                    print(f"    解析器: 跳过无效元素: id='{q_id_attr}', topic='{q_topic_attr}' (topic非数字或为空)")
                    continue

                question_info = {"id": q_id_attr, "topic_num": q_topic_attr, "type_code": q_type_attr,
                                 "text": f"题目 {q_topic_attr} (默认标题)",
                                 "options": [], "sub_questions": [], "page_index": fieldset_index + 1,
                                 "question_index_overall": current_question_number_overall}
                try:
                    title_element = q_element.find_element(By.XPATH,
                                                           ".//div[contains(@class,'field-label') or contains(@class,'matrix-title') or contains(@class,'slider-title') or contains(@class,'div_title')]")
                    raw_text = title_element.text.strip()
                    cleaned_text = re.sub(r"^\d+[\s.、*]*★?", "", raw_text).strip()
                    question_info["text"] = cleaned_text if cleaned_text else raw_text
                    if not question_info["text"]:
                        alt_title_elements = q_element.find_elements(By.XPATH,
                                                                     "./div[contains(@class,'div_title_logic_text')]")
                        if alt_title_elements: question_info["text"] = re.sub(r"^\d+[\s.、*]*★?", "", alt_title_elements[
                            0].text.strip()).strip()
                except NoSuchElementException:
                    print(f"    解析器: 题目 {q_topic_attr} 未找到标准标题元素，尝试备用方案。")
                    try:
                        full_text_lines = q_element.text.split('\n')
                        if full_text_lines:
                            raw_text = full_text_lines[0].strip()
                            cleaned_text = re.sub(r"^\d+[\s.、*]*★?", "", raw_text).strip()
                            question_info[
                                "text"] = cleaned_text if cleaned_text else f"问题 {q_topic_attr} (标题提取失败)"
                        else:
                            question_info["text"] = f"问题 {q_topic_attr} (标题提取失败)"
                    except Exception as title_ex:
                        print(f"    解析器: 提取题目 {q_topic_attr} 备用标题时发生异常: {title_ex}")
                        question_info["text"] = f"问题 {q_topic_attr} (标题提取异常)"
                print(f"    解析器: 提取到标题: '{question_info['text']}'")

                if q_type_attr in ["3", "4", "5"]:
                    option_containers = []
                    try:
                        option_containers.extend(q_element.find_elements(By.XPATH,
                                                                         f".//div[contains(@class,'ui-controlgroup')]/div[starts-with(@class,'ui-radio') or starts-with(@class,'ui-checkbox')]"))
                    except:
                        pass
                    if not option_containers:
                        try:
                            option_containers.extend(q_element.find_elements(By.XPATH,
                                                                             ".//div[contains(@class,'scale-div')]//ul/li[contains(@class,'scale-item') or contains(@class,'rating-item') or not(@class)]"))
                        except:
                            pass
                    if not option_containers:
                        try:
                            option_containers.extend(
                                q_element.find_elements(By.XPATH, ".//label[input[@type='radio' or @type='checkbox']]"))
                        except:
                            pass
                    print(f"    解析器: 类型 {q_type_attr}, 找到 {len(option_containers)} 个选项容器。")
                    other_keywords = ("其他", "其它", "请注明", "请填写")

                    for opt_idx, opt_container in enumerate(option_containers):
                        opt_text = opt_container.text.strip()
                        opt_val = str(opt_idx + 1)
                        try:
                            input_el = opt_container.find_element(By.XPATH,
                                                                  ".//input[@type='radio' or @type='checkbox' or @type='text']")
                            val_attr = input_el.get_attribute('value')
                            if val_attr: opt_val = val_attr
                        except:
                            pass

                        if opt_text:
                            option_details = {"text": opt_text, "value": opt_val, "original_index": opt_idx + 1}
                            if any(keyword in opt_text for keyword in other_keywords):
                                option_details["is_other_specify"] = True
                                print(f"      解析器: 选项 {opt_idx + 1} 被识别为 '其他' 类型。")
                                try:
                                    possible_other_input_xpaths = [
                                        ".//input[@type='text'][not(@disabled)]", ".//textarea[not(@disabled)]",
                                        "./following-sibling::input[@type='text'][1][not(@disabled)]",
                                        "./following-sibling::textarea[1][not(@disabled)]",
                                        "./ancestor::label/following-sibling::input[@type='text'][1][not(@disabled)]",
                                        "./ancestor::label/following-sibling::textarea[1][not(@disabled)]"
                                    ]
                                    other_input_el = None
                                    for xpath_attempt in possible_other_input_xpaths:
                                        try:
                                            candidate_el = opt_container.find_element(By.XPATH, xpath_attempt)
                                            if candidate_el.is_displayed(): other_input_el = candidate_el; break
                                        except NoSuchElementException:
                                            continue

                                    if other_input_el:
                                        option_details["other_input_tag"] = other_input_el.tag_name
                                        other_input_id = other_input_el.get_attribute("id")
                                        other_input_name = other_input_el.get_attribute("name")
                                        if other_input_id:
                                            option_details["other_input_locator"] = {"type": "id",
                                                                                     "value": other_input_id}
                                            print(
                                                f"        解析器: '其他'选项发现关联文本框 (Tag: {other_input_el.tag_name}, ID: {other_input_id})")
                                        elif other_input_name:
                                            option_details["other_input_locator"] = {"type": "name",
                                                                                     "value": other_input_name}
                                            print(
                                                f"        解析器: '其他'选项发现关联文本框 (Tag: {other_input_el.tag_name}, Name: {other_input_name})")
                                        else:
                                            print(f"        解析器: '其他'选项关联文本框无ID或Name，定位可能困难。")
                                except Exception as e_other_locator_find:
                                    print(f"        解析器: 查找'其他'选项关联文本框时出错: {e_other_locator_find}")
                            question_info["options"].append(option_details)
                            print(f"      解析器: 选项 {opt_idx + 1}: '{opt_text}' (Value: {opt_val})")
                        else:
                            print(f"      解析器: 选项 {opt_idx + 1} 文本为空，跳过。")

                elif q_type_attr == "7":
                    try:
                        select_element = q_element.find_element(By.XPATH, f".//select[@id='q{q_topic_attr}']")
                        option_elements = select_element.find_elements(By.TAG_NAME, "option")
                        print(f"    解析器: 类型 7 (下拉框), 找到 {len(option_elements)} 个原始option元素。")
                        opt_display_idx = 0
                        for opt_el in option_elements:
                            opt_text = opt_el.text.strip();
                            opt_val = opt_el.get_attribute('value')
                            if opt_val and opt_text and "请选择" not in opt_text:
                                opt_display_idx += 1
                                option_details = {"text": opt_text, "value": opt_val, "original_index": opt_display_idx}
                                # 下拉框的“其他”项通常是value为空或特殊值，且文本提示输入
                                if (not opt_val or opt_val == "-1" or opt_val.lower() == "other") and \
                                        any(keyword in opt_text.lower() for keyword in
                                            ["other", "其他", "其它", "specify", "注明"]):
                                    option_details["is_other_specify"] = True
                                    print(f"        解析器: 下拉选项 {opt_display_idx} 被识别为 '其他' 类型。")
                                    # 下拉框的 "其他" 文本框通常是动态出现的，其ID可能与select的ID相关
                                    # 例如 q<topic_num>_other or q<topic_num>_text
                                    # This is highly heuristic and might need specific adaptation for WJX
                                    related_other_input_id = f"q{q_topic_attr}_other"  # Common pattern
                                    try:
                                        # Check if such an element potentially exists (even if not visible yet)
                                        # We can't reliably find it here if it's dynamically generated on select.
                                        # So we'll just assume a common ID pattern for the filler to try.
                                        # Or, some dropdowns might have a data-other attribute on the option.
                                        if driver.find_elements(By.ID, related_other_input_id) or \
                                                driver.find_elements(By.ID,
                                                                     f"q{q_topic_attr}_text"):  # Check if a common ID exists
                                            option_details["other_input_locator"] = {"type": "id",
                                                                                     "value": related_other_input_id}
                                            option_details[
                                                "other_input_tag"] = "input"  # Usually input for dropdown other
                                            print(f"          解析器: 下拉'其他'项可能关联ID: {related_other_input_id}")
                                    except:
                                        pass
                                question_info["options"].append(option_details)
                                print(f"      解析器: 下拉选项 {opt_display_idx}: '{opt_text}' (Value: {opt_val})")
                            else:
                                print(f"      解析器: 跳过无效下拉选项: Text='{opt_text}', Value='{opt_val}'")
                    except:
                        print(f"    解析器: 题目 {q_topic_attr} (下拉框) 未找到标准select元素或解析失败。")
                elif q_type_attr == "6":
                    try:
                        sub_q_rows = q_element.find_elements(By.XPATH,
                                                             ".//table[contains(@class,'matrix') or @class='tableitems']/tbody/tr[normalize-space(@class)='matrixNormalTr' or normalize-space(@class)='matrixRandomTr' or not(@class)]")
                        header_option_elements = q_element.find_elements(By.XPATH,
                                                                         ".//table[contains(@class,'matrix') or @class='tableitems']/thead/tr/th")
                        print(
                            f"    解析器: 类型 6 (矩阵题), 找到 {len(sub_q_rows)} 个子问题行, {len(header_option_elements)} 个表头列。")
                        matrix_shared_options = []
                        start_col_index_for_options = 1 if header_option_elements and not header_option_elements[
                            0].text.strip() and len(header_option_elements) > 1 else 0
                        for opt_col_idx, th_element in enumerate(header_option_elements[start_col_index_for_options:]):
                            opt_text = th_element.text.strip()
                            if opt_text: matrix_shared_options.append({"text": opt_text, "value": str(opt_col_idx + 1),
                                                                       "original_index": opt_col_idx + 1 + start_col_index_for_options}); print(
                                f"      解析器: 矩阵共享选项 {opt_col_idx + 1}: '{opt_text}'")
                        if not matrix_shared_options and sub_q_rows:
                            first_data_row_tds = sub_q_rows[0].find_elements(By.XPATH, "./td")
                            if len(first_data_row_tds) > 1:
                                print("      解析器: 尝试从矩阵第一数据行推断选项...")
                                for td_idx, td_el in enumerate(first_data_row_tds[1:]):
                                    try:
                                        input_in_td = td_el.find_element(By.XPATH,
                                                                         ".//input[@type='radio' or @type='checkbox']");
                                        aria_label = input_in_td.get_attribute(
                                            "aria-label") or input_in_td.get_attribute("title");
                                        opt_text = aria_label.strip() if aria_label else f"列{td_idx + 1}"
                                    except:
                                        opt_text = f"列{td_idx + 1}"
                                    matrix_shared_options.append(
                                        {"text": opt_text, "value": str(td_idx + 1), "original_index": td_idx + 2});
                                    print(f"        解析器: 推断出矩阵选项 {td_idx + 1}: '{opt_text}'")
                        for row_idx, sub_q_row_element in enumerate(sub_q_rows):
                            try:
                                sub_q_text_element = sub_q_row_element.find_element(By.XPATH, "./td[1]");
                                sub_q_text = sub_q_text_element.text.strip();
                                sub_q_tr_id = sub_q_row_element.get_attribute("id")
                                if not sub_q_tr_id: sub_q_tr_id = f"matrix_{q_topic_attr}_row_{row_idx + 1}"
                                if sub_q_text and matrix_shared_options:
                                    question_info["sub_questions"].append(
                                        {"text": sub_q_text, "options": matrix_shared_options, "id_prefix": sub_q_tr_id,
                                         "original_index": row_idx + 1});
                                    print(
                                        f"      解析器: 矩阵子问题 {row_idx + 1}: '{sub_q_text}', TR_ID: {sub_q_tr_id}")
                                else:
                                    print(
                                        f"      解析器: 跳过矩阵子问题 {row_idx + 1} (文本: '{sub_q_text}', 选项数: {len(matrix_shared_options)})")
                            except:
                                print(
                                    f"    解析器: 解析矩阵题 {q_topic_attr} 的子问题行 {row_idx + 1} 失败 (未找到td[1])。")
                    except Exception as e_matrix:
                        print(f"    解析器: 解析矩阵题 {q_topic_attr} 时出错: {e_matrix}")
                elif q_type_attr == "11":
                    print(f"    解析器: 类型 11 (排序题)")
                    try:
                        sortable_list_container = q_element.find_elements(By.XPATH,
                                                                          ".//ul[contains(@class,'sort_data') or contains(@class,'sortable') or contains(@class,'rank')]")
                        if sortable_list_container:
                            sortable_items = sortable_list_container[0].find_elements(By.XPATH, "./li")
                            print(f"      解析器: 找到 {len(sortable_items)} 个可排序项。")
                            for s_idx, s_item in enumerate(sortable_items):
                                s_text = s_item.text.strip()
                                if s_text: question_info["options"].append(
                                    {"text": s_text, "value": str(s_idx + 1), "original_index": s_idx + 1}); print(
                                    f"        解析器: 排序项 {s_idx + 1}: '{s_text}'")
                        else:
                            print(f"      解析器: 未找到排序题的 ul 容器。")
                    except Exception as e_sort:
                        print(f"    解析器: 解析排序题 {q_topic_attr} 选项时出错: {e_sort}")

                is_valid_q = False
                if question_info["text"] and not question_info["text"].startswith(f"题目 {q_topic_attr}"):
                    if q_type_attr in ["1", "2", "8", "11"]:
                        is_valid_q = True
                    elif question_info["options"]:
                        is_valid_q = True
                    elif q_type_attr == "6" and question_info["sub_questions"] and question_info["sub_questions"][
                        0].get("options"):
                        is_valid_q = True
                if is_valid_q:
                    questions_data.append(question_info);
                    print(f"    解析器: 问题 {q_topic_attr} 添加成功。")
                else:
                    print(
                        f"    解析器: 信息不足或类型不支持，跳过问题: ID={q_id_attr}, Text='{question_info['text']}', Opts={len(question_info.get('options', []))}, SubQs={len(question_info.get('sub_questions', []))}")
    except TimeoutException:
        return {"error": f"页面加载或操作超时: {url}"}
    except Exception as e_main:
        return {"error": f"解析问卷时发生主流程错误: {e_main}\n{traceback.format_exc()}"}
    finally:
        if driver:
            driver.quit();
            print("解析器: WebDriver 已关闭。")
        if actual_user_data_dir_parser and os.path.exists(actual_user_data_dir_parser):
            try:
                shutil.rmtree(actual_user_data_dir_parser, ignore_errors=True)
                print(f"解析器: 已清理用户数据目录 {actual_user_data_dir_parser}")
            except Exception as e_cleanup_parser:
                print(f"解析器: 清理用户数据目录 {actual_user_data_dir_parser} 失败: {e_cleanup_parser}")

    if not questions_data: return {"error": "未能从问卷中解析出任何有效的问题。"}
    print(f"解析器: 问卷解析完成，共提取到 {len(questions_data)} 个有效问题。")
    return questions_data


if __name__ == '__main__':
    test_url_example = "https://www.wjx.cn/vm/Y7Eps4P.aspx#"
    print(f"测试解析 (默认Edge, 系统PATH): {test_url_example}")
    structure = fetch_questionnaire_structure(test_url_example)
    if isinstance(structure, dict) and "error" in structure:
        print(f"\n解析失败: {structure['error']}")
    elif structure:
        print(f"\n成功解析到 {len(structure)} 个问题:")
        for i, q in enumerate(structure):
            print(
                f"\n--- 问题 {q.get('question_index_overall', i + 1)} (原始题号: {q['topic_num']}, 类型: {q['type_code']}) ---")
            print(f"  ID: {q['id']}");
            print(f"  文本: {q['text']}")
            if q.get("options"):
                print(f"  选项 ({len(q['options'])}):")
                for opt in q["options"]:
                    other_info = " (其他项)" if opt.get("is_other_specify") else ""
                    locator_info = f", Locator: {opt.get('other_input_locator')}" if opt.get(
                        "other_input_locator") else ""
                    tag_info = f", Tag: {opt.get('other_input_tag')}" if opt.get("other_input_tag") else ""
                    print(
                        f"    - \"{opt['text']}\" (值: {opt['value']}, HTML索引: {opt['original_index']}){other_info}{locator_info}{tag_info}")
            if q.get("sub_questions"):
                print(f"  子问题 ({len(q['sub_questions'])}):")
                for sub_q_idx, sub_q in enumerate(q["sub_questions"]):
                    print(
                        f"    - 子问题 {sub_q_idx + 1}: \"{sub_q['text']}\" (ID前缀: {sub_q.get('id_prefix', 'N/A')})")
    else:
        print("\n问卷解析失败或未返回任何问题。")