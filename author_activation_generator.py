# author_activation_generator.py
import uuid
import json
import os
import time

ACTIVATIONS_FILE_PATH = "activations.json" # 激活文件路径


def load_activations():
    # 加载激活文件数据
    if os.path.exists(ACTIVATIONS_FILE_PATH):
        try:
            with open(ACTIVATIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"警告: {ACTIVATIONS_FILE_PATH} 文件内容不是有效的JSON。将尝试创建一个新的或在现有基础上操作。")
            return {}
        except Exception as e:
            print(f"读取 {ACTIVATIONS_FILE_PATH} 文件时出错: {e}。将尝试创建一个新的或在现有基础上操作。")
            return {}
    return {} # 文件不存在或读取失败，返回空字典


def save_activations(activations_data):
    # 保存激活数据到文件
    try:
        with open(ACTIVATIONS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(activations_data, f, indent=4, ensure_ascii=False) # indent=4 美化JSON输出
        print(f"激活码数据已成功保存到 {ACTIVATIONS_FILE_PATH}")
    except Exception as e:
        print(f"保存激活码数据到 {ACTIVATIONS_FILE_PATH} 文件时出错: {e}")


def generate_and_add_code(validity_period_code, input_window_seconds=0, description=""):
    # 生成并添加新的激活码条目
    activations = load_activations() # 先加载现有数据
    new_uuid_str = str(uuid.uuid4()) # 生成新的UUID

    while new_uuid_str in activations: # 确保UUID唯一性 (理论上碰撞概率极低)
        new_uuid_str = str(uuid.uuid4())

    current_utc_timestamp = time.time() # 获取当前UTC时间戳 (float)

    # 构建激活码条目字典
    activation_entry = {
        "validity_code": validity_period_code.upper(), # 激活后的有效期代码 (如 "7D", "1M", "UNL")
        "issue_timestamp_utc": current_utc_timestamp,  # 签发时间戳 (UTC)
        "input_window_seconds": int(input_window_seconds), # 此激活码的输入有效时长（秒），0表示不限制
        "description": description, # 描述信息
        "issued_at_readable_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(current_utc_timestamp)), # 人类可读的签发时间 (UTC)
        "issued_at_readable_local": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(current_utc_timestamp)) # 人类可读的签发时间 (本地)
    }
    activations[new_uuid_str] = activation_entry # 将新条目添加到数据中
    save_activations(activations) # 保存回文件

    # 返回生成的UUID，用户将使用此UUID进行激活
    return f"{new_uuid_str}"


if __name__ == "__main__":
    print("--- 问卷星助手 - 激活码生成与管理工具 (JSON存储) ---")
    while True:
        print("\n请选择操作:")
        print("  1. 生成并添加新激活码")
        print("  2. 查看现有激活码 (仅部分)")
        print("  3. (高级) 手动编辑或删除激活码 (请直接操作JSON文件)")
        print("  Q. 退出程序")

        operation = input("请输入操作编号: ").strip().upper()

        if operation == 'Q':
            break

        if operation == '1':
            print("\n--- 生成新激活码 ---")

            print("激活后的有效期类型:")
            print("  H: 小时 (例如: 24H)")
            print("  D: 天   (例如: 7D)")
            print("  M: 月   (例如: 1M)")
            print("  Y: 年   (例如: 1Y)")
            print("  UNL: 永久 (名义上，如20年)")
            validity_choice_str = input("请输入激活后的有效期 (例如 7D, 1M, UNL): ").strip()

            parsed_validity_code = ""
            is_valid_validity_format = False
            if validity_choice_str.upper() == "UNL":
                is_valid_validity_format = True
                parsed_validity_code = "UNL"
            else:
                val_part = "".join(filter(str.isdigit, validity_choice_str)) # 提取数字部分
                unit_part = "".join(filter(str.isalpha, validity_choice_str)).upper() # 提取字母部分并转大写
                if val_part and val_part.isdigit() and int(val_part) > 0 and unit_part in ['H', 'D', 'M', 'Y']:
                    is_valid_validity_format = True
                    parsed_validity_code = val_part + unit_part # 组合成如 "7D"

            if not is_valid_validity_format:
                print("错误：激活后的有效期格式无效或数值无效。请确保数值大于0且单位正确 (H, D, M, Y, UNL)。")
                continue

            input_window_str = input("请输入此激活码的输入有效时长（分钟，0 表示不限制此码的输入时效性）: ").strip()
            input_window_minutes = 0
            if input_window_str.isdigit():
                input_window_minutes = int(input_window_str)
            input_window_seconds_for_json = input_window_minutes * 60 # 转换为秒

            desc_str = input("请输入激活码描述 (可选，方便您记录用途): ").strip()

            try:
                generated_user_code_uuid_part = generate_and_add_code(
                    parsed_validity_code,
                    input_window_seconds_for_json,
                    desc_str
                )
                print(f"\n--- 激活码已成功生成并添加 ---")
                print(f"  UUID (用于JSON查找和用户输入): {generated_user_code_uuid_part}")
                print(f"  激活后的有效期代码: {parsed_validity_code}")
                if input_window_seconds_for_json > 0:
                    print(f"  此激活码需在签发后 {input_window_minutes} 分钟内输入有效。")
                else:
                    print(f"  此激活码无输入时间窗口限制。")
                print(f"  描述: {desc_str if desc_str else '无'}")
                print(f"  (已更新到 {ACTIVATIONS_FILE_PATH})")
            except Exception as e_gen:
                print(f"生成激活码时发生错误: {e_gen}")

        elif operation == '2':
            activations_data_loaded = load_activations()
            if not activations_data_loaded:
                print(f"{ACTIVATIONS_FILE_PATH} 为空或无法加载。")
            else:
                print(f"\n--- {ACTIVATIONS_FILE_PATH} 中的激活码信息 (最多显示前10条) ---")
                count = 0
                for uuid_key, entry_data in activations_data_loaded.items():
                    print(f"\n  激活码 UUID: {uuid_key}")
                    if isinstance(entry_data, dict): # 新格式，包含详细信息
                        print(f"    激活后有效期: {entry_data.get('validity_code', 'N/A')}")
                        print(f"    签发时间 (UTC): {entry_data.get('issued_at_readable_utc', 'N/A')}")
                        # print(f"    签发时间 (Local): {entry_data.get('issued_at_readable_local', 'N/A')}") # 本地时间可能意义不大，除非明确时区
                        win_sec = entry_data.get('input_window_seconds', 0)
                        if win_sec > 0:
                            print(f"    输入窗口期: {win_sec // 60} 分钟")
                        print(f"    描述: {entry_data.get('description', '无')}")
                    else: # 旧格式，直接是有效期代码
                        print(f"    激活后有效期 (旧格式): {entry_data}")
                    count += 1
                    if count >= 10:
                        print("\n  ... (更多激活码请直接查看JSON文件)")
                        break
                if count == 0:
                    print("  文件中没有找到激活码条目。")

        elif operation == '3':
            print(f"\n请注意：建议使用文本编辑器直接、谨慎地操作 '{ACTIVATIONS_FILE_PATH}' 文件。")
            print("确保JSON格式正确，每个条目应为字典，包含 'validity_code', 'issue_timestamp_utc', 'input_window_seconds' 等键。")

        else:
            print("无效的操作选项，请重新输入。")