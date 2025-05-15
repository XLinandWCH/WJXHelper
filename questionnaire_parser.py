# questionnaire_parser.py
import time
import re
import os  # 新增 os 模块导入
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait  # 新增 WebDriverWait
from selenium.webdriver.support import expected_conditions as EC  # 新增 EC

# 默认驱动路径，如果用户未在UI中设置，且驱动不在系统PATH中，可以考虑在此处设置一个后备路径
# 但更推荐的是让用户通过UI设置，或确保驱动在PATH中。
# MSEDGEDRIVER_PATH_FALLBACK = "C:/Users/xlina/Desktop/WJXHelper/msedgedriver.exe" # 这是一个示例后备路径
MSEDGEDRIVER_PATH_FALLBACK = None  # 设置为 None，优先依赖用户设置或系统PATH


def fetch_questionnaire_structure(url, msedgedriver_path_arg=None):
    """
    使用 Selenium (headless Edge) 获取问卷结构。
    msedgedriver_path_arg: 从UI传入的驱动路径。
    返回一个问题列表，或一个包含 "error" 键的字典。
    """
    print(f"Parser: 开始解析问卷: {url}")
    print(f"Parser: 传入的驱动路径参数: {msedgedriver_path_arg}")

    # 决定实际使用的驱动路径
    actual_driver_path = msedgedriver_path_arg
    if not actual_driver_path:  # 如果UI未提供路径
        actual_driver_path = MSEDGEDRIVER_PATH_FALLBACK  # 尝试文件内的后备路径
        if actual_driver_path:
            print(f"Parser: UI未提供驱动路径，使用文件内后备路径: {actual_driver_path}")
        else:
            print(f"Parser: UI未提供驱动路径，且无文件内后备路径，将尝试从系统PATH启动驱动。")

    edge_options = EdgeOptions()
    edge_options.use_chromium = True
    edge_options.add_argument("--headless")
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument("--no-sandbox")
    edge_options.add_argument("--disable-dev-shm-usage")
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option('useAutomationExtension', False)
    edge_options.add_argument('--disable-blink-features=AutomationControlled')
    edge_options.add_argument(  # 添加一个常见的User-Agent
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36 Edg/90.0.818.66"
    )

    driver = None  # 初始化driver变量
    try:
        if actual_driver_path and os.path.exists(actual_driver_path):
            print(f"Parser: 尝试使用指定路径的驱动: {actual_driver_path}")
            service = EdgeService(executable_path=actual_driver_path)
            driver = webdriver.Edge(service=service, options=edge_options)
        else:
            if actual_driver_path:  # 路径指定了但不存在
                print(f"Parser: 指定的驱动路径 {actual_driver_path} 不存在，尝试从系统PATH启动。")
            print(f"Parser: 尝试从系统PATH启动驱动。")
            driver = webdriver.Edge(options=edge_options)  # 尝试从PATH启动
        print("Parser: Edge WebDriver 启动成功。")
    except Exception as e:
        error_msg = (f"启动EdgeDriver失败。请确保 msedgedriver.exe 版本与 Edge 浏览器匹配，"
                     f"并且其路径已在“程序设置”中正确指定，或位于系统 PATH 环境变量中。\n"
                     f"当前尝试路径(若有): {actual_driver_path if actual_driver_path else '无特定路径, 依赖系统PATH'}\n"
                     f"具体错误: {e}")
        print(f"Parser: {error_msg}")
        if driver: driver.quit()  # 确保万一 driver 对象部分初始化了也关闭
        return {"error": error_msg}

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """
        })
    except Exception as e_cdp:
        print(f"Parser: 执行CDP反检测命令失败 (可能不影响): {e_cdp}")

    questions_data = []
    try:
        print(f"Parser: 正在打开URL: {url}")
        driver.get(url)

        # *** 修改点：使用 WebDriverWait 等待核心问卷区域加载 ***
        try:
            WebDriverWait(driver, 20).until(  # 等待最多20秒
                EC.presence_of_element_located((By.ID, "divQuestion"))
            )
            print("Parser: 核心问卷区域 'divQuestion' 已加载。")
        except TimeoutException:
            error_msg = f"加载问卷内容 (divQuestion) 超时: {url}。请检查网络连接和URL是否正确，或目标问卷需要登录/验证。"
            print(f"Parser: {error_msg}")
            return {"error": error_msg}
        # time.sleep(1) # 可以保留一个非常短的延时，确保JS完全执行完毕，但主要依赖上面的WebDriverWait

        fieldsets = driver.find_elements(By.XPATH, '//*[@id="divQuestion"]/fieldset')
        if not fieldsets:
            print("Parser: 未找到分页的fieldset，尝试将整个 'divQuestion' 视为一个fieldset。")
            # 确保 divQuestion 元素存在
            div_question_element = driver.find_elements(By.ID, 'divQuestion')
            if div_question_element:
                fieldsets = div_question_element
            else:  # 如果连 divQuestion 都没有，则无法继续
                error_msg = "页面结构异常，未找到核心问卷容器 'divQuestion'。"
                print(f"Parser: {error_msg}")
                return {"error": error_msg}

        current_question_number_overall = 0
        print(f"Parser: 找到 {len(fieldsets)} 个fieldset (页面部分)。")

        for fieldset_index, fieldset in enumerate(fieldsets):
            print(f"Parser: 正在处理 Fieldset {fieldset_index + 1}...")
            # ./div[@topic] 表示在当前fieldset元素下查找满足条件的div
            question_elements_in_fieldset = fieldset.find_elements(By.XPATH, "./div[@topic]")
            print(f"Parser: Fieldset {fieldset_index + 1} 中找到 {len(question_elements_in_fieldset)} 个问题元素。")

            for q_element in question_elements_in_fieldset:
                current_question_number_overall += 1
                q_id_attr = q_element.get_attribute("id")
                q_topic_attr = q_element.get_attribute("topic")
                q_type_attr = q_element.get_attribute("type")

                print(f"  Parser: 解析原始题目信息: ID={q_id_attr}, Topic={q_topic_attr}, Type={q_type_attr}")

                if not q_topic_attr or not q_topic_attr.isdigit():
                    print(f"    Parser: 跳过无效元素: id='{q_id_attr}', topic='{q_topic_attr}' (topic非数字或为空)")
                    continue

                question_info = {
                    "id": q_id_attr, "topic_num": q_topic_attr, "type_code": q_type_attr,
                    "text": f"题目 {q_topic_attr} (默认标题)", "options": [], "sub_questions": [],
                    "page_index": fieldset_index + 1,
                    "question_index_overall": current_question_number_overall
                }

                # 1. 获取问题文本
                try:
                    title_element = q_element.find_element(By.XPATH,
                                                           ".//div[contains(@class, 'field-label') or contains(@class, 'matrix-title') or contains(@class, 'slider-title') or contains(@class,'div_title')]")
                    raw_text = title_element.text.strip()
                    cleaned_text = re.sub(r"^\d+[\s.、*]*★?", "", raw_text).strip()  # 移除了题号和必填星号 ★
                    question_info["text"] = cleaned_text if cleaned_text else raw_text
                    if not question_info["text"]:  # 如果文本为空，尝试父元素的文本
                        alt_title_elements = q_element.find_elements(By.XPATH,
                                                                     "./div[contains(@class,'div_title_logic_text')]")
                        if alt_title_elements:
                            question_info["text"] = re.sub(r"^\d+[\s.、*]*★?", "",
                                                           alt_title_elements[0].text.strip()).strip()

                except NoSuchElementException:
                    print(f"    Parser: 题目 {q_topic_attr} 未找到标准标题元素，尝试备用方案。")
                    try:  # 尝试取整个元素的第一行文字作为标题
                        full_text_lines = q_element.text.split('\n')
                        if full_text_lines:
                            raw_text = full_text_lines[0].strip()
                            cleaned_text = re.sub(r"^\d+[\s.、*]*★?", "", raw_text).strip()
                            question_info[
                                "text"] = cleaned_text if cleaned_text else f"问题 {q_topic_attr} (标题提取失败)"
                        else:
                            question_info["text"] = f"问题 {q_topic_attr} (标题提取失败)"
                    except Exception as title_ex:
                        print(f"    Parser: 提取题目 {q_topic_attr} 备用标题时发生异常: {title_ex}")
                        question_info["text"] = f"问题 {q_topic_attr} (标题提取异常)"
                print(f"    Parser: 提取到标题: '{question_info['text']}'")

                # 2. 根据题型解析选项 (此部分逻辑较复杂，保持原样，但添加打印)
                if q_type_attr in ["3", "4", "5"]:  # 单选, 多选, 量表题
                    option_containers = []
                    # 尝试多种可能的选项容器结构
                    try:
                        option_containers.extend(q_element.find_elements(By.XPATH,
                                                                         f".//div[contains(@class, 'ui-controlgroup')]/div[starts-with(@class, 'ui-radio') or starts-with(@class, 'ui-checkbox')]"))
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

                    print(f"    Parser: 类型 {q_type_attr}, 找到 {len(option_containers)} 个选项容器。")
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
                            question_info["options"].append(
                                {"text": opt_text, "value": opt_val, "original_index": opt_idx + 1})
                            print(f"      Parser: 选项 {opt_idx + 1}: '{opt_text}' (Value: {opt_val})")
                        else:
                            print(f"      Parser: 选项 {opt_idx + 1} 文本为空，跳过。")


                elif q_type_attr == "7":  # 下拉框
                    try:
                        select_element = q_element.find_element(By.XPATH, f".//select[@id='q{q_topic_attr}']")
                        option_elements = select_element.find_elements(By.TAG_NAME, "option")
                        print(f"    Parser: 类型 7 (下拉框), 找到 {len(option_elements)} 个原始option元素。")
                        opt_display_idx = 0
                        for opt_el in option_elements:
                            opt_text = opt_el.text.strip()
                            opt_val = opt_el.get_attribute('value')
                            if opt_val and opt_text and "请选择" not in opt_text:  # 跳过 "请选择"
                                opt_display_idx += 1
                                question_info["options"].append(
                                    {"text": opt_text, "value": opt_val, "original_index": opt_display_idx})
                                print(f"      Parser: 下拉选项 {opt_display_idx}: '{opt_text}' (Value: {opt_val})")
                            else:
                                print(f"      Parser: 跳过无效下拉选项: Text='{opt_text}', Value='{opt_val}'")
                    except NoSuchElementException:
                        print(f"    Parser: 题目 {q_topic_attr} (下拉框) 未找到标准select元素或解析失败。")
                    except Exception as e_dd:
                        print(f"    Parser: 解析下拉框题目 {q_topic_attr} 选项时出错: {e_dd}")

                elif q_type_attr == "6":  # 矩阵题
                    try:
                        sub_q_rows = q_element.find_elements(By.XPATH,
                                                             ".//table[contains(@class,'matrix') or @class='tableitems']/tbody/tr[normalize-space(@class)='matrixNormalTr' or normalize-space(@class)='matrixRandomTr' or not(@class)]")
                        header_option_elements = q_element.find_elements(By.XPATH,
                                                                         ".//table[contains(@class,'matrix') or @class='tableitems']/thead/tr/th")
                        print(
                            f"    Parser: 类型 6 (矩阵题), 找到 {len(sub_q_rows)} 个子问题行, {len(header_option_elements)} 个表头列。")

                        matrix_shared_options = []
                        start_col_index_for_options = 1 if header_option_elements and not header_option_elements[
                            0].text.strip() and len(header_option_elements) > 1 else 0

                        for opt_col_idx, th_element in enumerate(header_option_elements[start_col_index_for_options:]):
                            opt_text = th_element.text.strip()
                            if opt_text:
                                matrix_shared_options.append({
                                    "text": opt_text, "value": str(opt_col_idx + 1),
                                    "original_index": opt_col_idx + 1 + start_col_index_for_options
                                })
                                print(f"      Parser: 矩阵共享选项 {opt_col_idx + 1}: '{opt_text}'")

                        if not matrix_shared_options and sub_q_rows:  # 尝试从第一行数据推断选项
                            first_data_row_tds = sub_q_rows[0].find_elements(By.XPATH, "./td")
                            if len(first_data_row_tds) > 1:
                                print("      Parser: 尝试从矩阵第一数据行推断选项...")
                                for td_idx, td_el in enumerate(first_data_row_tds[1:]):  # 第一个是行标题
                                    try:
                                        input_in_td = td_el.find_element(By.XPATH,
                                                                         ".//input[@type='radio' or @type='checkbox']")
                                        aria_label = input_in_td.get_attribute(
                                            "aria-label") or input_in_td.get_attribute("title")
                                        opt_text = aria_label.strip() if aria_label else f"列{td_idx + 1}"
                                    except:
                                        opt_text = f"列{td_idx + 1}"
                                    matrix_shared_options.append(
                                        {"text": opt_text, "value": str(td_idx + 1), "original_index": td_idx + 2})
                                    print(f"        Parser: 推断出矩阵选项 {td_idx + 1}: '{opt_text}'")

                        for row_idx, sub_q_row_element in enumerate(sub_q_rows):
                            try:
                                sub_q_text_element = sub_q_row_element.find_element(By.XPATH, "./td[1]")
                                sub_q_text = sub_q_text_element.text.strip()
                                sub_q_tr_id = sub_q_row_element.get_attribute("id")
                                if not sub_q_tr_id: sub_q_tr_id = f"matrix_{q_topic_attr}_row_{row_idx + 1}"

                                if sub_q_text and matrix_shared_options:
                                    question_info["sub_questions"].append({
                                        "text": sub_q_text, "options": matrix_shared_options,
                                        "id_prefix": sub_q_tr_id, "original_index": row_idx + 1
                                    })
                                    print(
                                        f"      Parser: 矩阵子问题 {row_idx + 1}: '{sub_q_text}', TR_ID: {sub_q_tr_id}")
                                else:
                                    print(
                                        f"      Parser: 跳过矩阵子问题 {row_idx + 1} (文本: '{sub_q_text}', 选项数: {len(matrix_shared_options)})")
                            except NoSuchElementException:
                                print(
                                    f"    Parser: 解析矩阵题 {q_topic_attr} 的子问题行 {row_idx + 1} 失败 (未找到td[1])。")
                    except Exception as e_matrix:
                        print(f"    Parser: 解析矩阵题 {q_topic_attr} 时出错: {e_matrix}")

                elif q_type_attr == "11":  # 排序题
                    print(f"    Parser: 类型 11 (排序题)")
                    try:
                        # 排序项通常在 ul class="sort_data" 或类似结构下的 li
                        sortable_list_container = q_element.find_elements(By.XPATH,
                                                                          ".//ul[contains(@class,'sort_data') or contains(@class,'sortable') or contains(@class,'rank')]")
                        if sortable_list_container:
                            sortable_items = sortable_list_container[0].find_elements(By.XPATH, "./li")
                            print(f"      Parser: 找到 {len(sortable_items)} 个可排序项。")
                            for s_idx, s_item in enumerate(sortable_items):
                                s_text = s_item.text.strip()
                                if s_text:
                                    question_info["options"].append(
                                        {"text": s_text, "value": str(s_idx + 1), "original_index": s_idx + 1})
                                    print(f"        Parser: 排序项 {s_idx + 1}: '{s_text}'")
                        else:
                            print(f"      Parser: 未找到排序题的 ul 容器。")
                    except Exception as e_sort:
                        print(f"    Parser: 解析排序题 {q_topic_attr} 选项时出错: {e_sort}")

                # 验证问题是否有效 (有文本，并且是特定类型或有选项/子问题)
                is_valid_q = False
                if question_info["text"] and not question_info["text"].startswith(f"题目 {q_topic_attr}"):  # 确保标题被有效提取
                    if q_type_attr in ["1", "2", "8", "11"]:
                        is_valid_q = True
                    elif question_info["options"]:
                        is_valid_q = True
                    elif q_type_attr == "6" and question_info["sub_questions"] and question_info["sub_questions"][
                        0].get("options"):
                        is_valid_q = True  # 矩阵题需要子问题和共享选项

                if is_valid_q:
                    questions_data.append(question_info)
                    print(f"    Parser: 问题 {q_topic_attr} 添加成功。")
                else:
                    print(
                        f"    Parser: 信息不足或类型不支持，跳过问题: ID={q_id_attr}, Text='{question_info['text']}', Opts={len(question_info.get('options', []))}, SubQs={len(question_info.get('sub_questions', []))}")

    except TimeoutException:  # 这个是Selenium的Timeout，比如driver.get()本身超时
        error_msg = f"页面加载或操作超时: {url}"
        print(f"Parser: {error_msg}")
        return {"error": error_msg}
    except Exception as e_main:
        error_msg = f"解析问卷时发生主流程错误: {e_main}"
        print(f"Parser: {error_msg}")
        import traceback
        traceback.print_exc()  # 打印详细堆栈
        return {"error": error_msg}
    finally:
        if driver:
            driver.quit()
            print("Parser: WebDriver 已关闭。")

    if not questions_data:
        return {"error": "未能从问卷中解析出任何有效的问题。请检查URL或页面结构是否与解析器兼容。"}

    print(f"Parser: 问卷解析完成，共提取到 {len(questions_data)} 个有效问题。")
    return questions_data


if __name__ == '__main__':
    test_url_example = "https://www.wjx.cn/vm/Y7Eps4P.aspx#"  # 使用一个你知道结构的测试问卷
    # test_url_example = "https://www.wjx.cn/vm/PPiZFM2.aspx#" # 你的示例
    print(f"测试解析: {test_url_example}")
    # 测试时可以强制指定驱动路径:
    # structure = fetch_questionnaire_structure(test_url_example, msedgedriver_path_arg="C:/path/to/your/msedgedriver.exe")
    structure = fetch_questionnaire_structure(test_url_example)

    if isinstance(structure, dict) and "error" in structure:
        print(f"\n解析失败: {structure['error']}")
    elif structure:
        print(f"\n成功解析到 {len(structure)} 个问题:")
        for i, q in enumerate(structure):
            print(
                f"\n--- 问题 {q.get('question_index_overall', i + 1)} (原始题号: {q['topic_num']}, 类型: {q['type_code']}) ---")
            print(f"  ID: {q['id']}")
            print(f"  文本: {q['text']}")
            if q.get("options"):
                print(f"  选项 ({len(q['options'])}):")
                for opt in q["options"]:
                    print(f"    - \"{opt['text']}\" (值: {opt['value']}, HTML索引: {opt['original_index']})")
            if q.get("sub_questions"):
                print(f"  子问题 ({len(q['sub_questions'])}):")
                for sub_q_idx, sub_q in enumerate(q["sub_questions"]):
                    print(
                        f"    - 子问题 {sub_q_idx + 1}: \"{sub_q['text']}\" (ID前缀: {sub_q.get('id_prefix', 'N/A')})")
                    if sub_q.get("options"):  # 矩阵共享选项
                        # print(f"      共享选项 ({len(sub_q['options'])}):")
                        # for opt in sub_q["options"]:
                        # print(f"        - \"{opt['text']}\" (值: {opt['value']}, HTML列索引: {opt['original_index']})")
                        pass  # 避免重复打印共享选项
    else:
        print("\n问卷解析失败或未返回任何问题。")