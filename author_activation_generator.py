# author_activation_generator.py
import uuid
import json
import os
import time

ACTIVATIONS_FILE_PATH = "activations.json"


def load_activations():
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
    return {}


def save_activations(activations_data):
    try:
        with open(ACTIVATIONS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(activations_data, f, indent=4, ensure_ascii=False)
        print(f"激活码数据已成功保存到 {ACTIVATIONS_FILE_PATH}")
    except Exception as e:
        print(f"保存激活码数据到 {ACTIVATIONS_FILE_PATH} 文件时出错: {e}")


def generate_and_add_code(validity_period_code, input_window_seconds=0, description=""):
    activations = load_activations()
    new_uuid_str = str(uuid.uuid4())

    while new_uuid_str in activations: # 确保UUID唯一性
        new_uuid_str = str(uuid.uuid4())

    current_utc_timestamp = time.time() # 统一使用 time.time() 获取UTC时间戳

    activation_entry = {
        "validity_code": validity_period_code.upper(),
        "issue_timestamp_utc": current_utc_timestamp,
        "input_window_seconds": int(input_window_seconds),
        "description": description,
        "issued_at_readable_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(current_utc_timestamp)),
        "issued_at_readable_local": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(current_utc_timestamp))
    }
    activations[new_uuid_str] = activation_entry
    save_activations(activations)

    # 给用户的激活码通常只是UUID，或者UUID_有效期代码（如果希望用户感知）
    # 考虑到 ActivationDialog 中用户输入处理，返回 UUID 即可，或 UUID_validity_code
    return f"{new_uuid_str}" # 或者 f"{new_uuid_str}_{validity_period_code.upper()}"


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
            validity_choice_str = input("请输入激活后的有效期 (例如 7D, UNL): ").strip()

            parsed_validity_code = ""
            is_valid_validity_format = False
            if validity_choice_str.upper() == "UNL":
                is_valid_validity_format = True
                parsed_validity_code = "UNL"
            else:
                val_part = "".join(filter(str.isdigit, validity_choice_str))
                unit_part = "".join(filter(str.isalpha, validity_choice_str)).upper()
                if val_part and val_part.isdigit() and int(val_part) > 0 and unit_part in ['H', 'D', 'M', 'Y']:
                    is_valid_validity_format = True
                    parsed_validity_code = val_part + unit_part

            if not is_valid_validity_format:
                print("错误：激活后的有效期格式无效或数值无效。请确保数值大于0且单位正确。")
                continue

            input_window_str = input("请输入此激活码的输入有效时长（分钟，0 表示不限制此码的输入时效性）: ").strip()
            input_window_minutes = 0
            if input_window_str.isdigit():
                input_window_minutes = int(input_window_str)
            input_window_seconds_for_json = input_window_minutes * 60

            desc_str = input("请输入激活码描述 (可选，方便您记录用途): ").strip()

            try:
                generated_user_code_uuid_part = generate_and_add_code(
                    parsed_validity_code,
                    input_window_seconds_for_json,
                    desc_str
                )
                print(f"\n--- 激活码已成功生成并添加 ---")
                print(f"  UUID (用于JSON查找和用户输入): {generated_user_code_uuid_part}")
                # print(f"  提供给用户的激活码 (可选格式): {generated_user_code_uuid_part}_{parsed_validity_code}")
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
                    if isinstance(entry_data, dict):
                        print(f"    激活后有效期: {entry_data.get('validity_code', 'N/A')}")
                        issue_ts = entry_data.get('issue_timestamp_utc')
                        if issue_ts:
                            print(f"    签发时间 (UTC): {entry_data.get('issued_at_readable_utc', 'N/A')}")
                            print(f"    签发时间 (Local): {entry_data.get('issued_at_readable_local', 'N/A')}")
                        win_sec = entry_data.get('input_window_seconds', 0)
                        if win_sec > 0:
                            print(f"    输入窗口期: {win_sec // 60} 分钟")
                        print(f"    描述: {entry_data.get('description', '无')}")
                    else:
                        print(f"    激活后有效期 (旧格式): {entry_data}")
                    count += 1
                    if count >= 10:
                        print("\n  ... (更多激活码请直接查看JSON文件)")
                        break
                if count == 0:
                    print("  文件中没有找到激活码条目。")

        elif operation == '3':
            print(f"\n请注意：建议使用文本编辑器直接、谨慎地操作 '{ACTIVATIONS_FILE_PATH}' 文件。")
            print("确保JSON格式正确，每个条目包含 'validity_code', 'issue_timestamp_utc', 和 'input_window_seconds'。")

        else:
            print("无效的操作选项，请重新输入。")

