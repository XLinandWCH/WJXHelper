# text_formatter_cli.py
import re
import sys

# 定义填空题随机分隔符常量
RANDOM_SEPARATOR = "||"
# 定义填空题顺序标记常量
SEQUENTIAL_MARKER_START = "["
SEQUENTIAL_MARKER_END = "]"


def format_text(input_string, format_choice):
    """
    根据选择的格式对输入的字符串进行处理。
    输入字符串中通常多个项目用空格或其他空白字符分隔。

    Args:
        input_string (str): 原始输入字符串，例如 "张三 李四 王五"。
        format_choice (int): 格式选项。
                             1: 随机格式 (使用 '||' 分隔)。
                             2: 顺序格式 (使用 '[]' 包裹每个项目)。

    Returns:
        str: 处理后的字符串，或包含错误信息的字符串。
    """
    if not isinstance(input_string, str) or not input_string.strip():
        return "错误: 输入字符串为空或只有空白字符。"

    # 使用 split() 方法以任意空白字符（空格、制表符、换行符等）作为分隔符，
    # 并且会自动忽略连续的空白字符和字符串开头/结尾的空白字符，从而得到有效项目列表。
    items = input_string.split()

    if not items:
        return "错误: 输入字符串未包含有效项目 (按空白字符分割后为空)。"

    if format_choice == 1:
        # 格式化为随机选择格式 (使用 || 连接所有项目)
        return RANDOM_SEPARATOR.join(items)
    elif format_choice == 2:
        # 格式化为顺序填写格式 (将每个项目用 [] 包裹，然后连接)
        return "".join([f"{SEQUENTIAL_MARKER_START}{item}{SEQUENTIAL_MARKER_END}" for item in items])
    else:
        return f"错误: 无效的格式选项 '{format_choice}'。请选择 1 或 2。"


if __name__ == "__main__":
    # 提供一个简单的命令行界面或交互模式来测试 format_text 函数。
    print("--- 文本格式化工具 ---")
    print(f"  选项 1: 随机格式 (使用 \"{RANDOM_SEPARATOR}\" 分隔，例如: 项1{RANDOM_SEPARATOR}项2)")
    print(
        f"  选项 2: 顺序格式 (使用 \"{SEQUENTIAL_MARKER_START}项目{SEQUENTIAL_MARKER_END}\" 包裹，例如: {SEQUENTIAL_MARKER_START}项1{SEQUENTIAL_MARKER_END}{SEQUENTIAL_MARKER_START}项2{SEQUENTIAL_MARKER_END})")
    print("-" * 30)

    try:
        # 检查命令行参数的数量。如果用户提供了两个额外的参数（输入字符串和格式选项），则直接处理。
        if len(sys.argv) == 3:
            # 命令行参数示例：python text_formatter_cli.py "张三 李四 王五" 1
            input_str_arg = sys.argv[1]
            format_choice_arg = int(sys.argv[2])  # 将格式选项转换为整数

            result = format_text(input_str_arg, format_choice_arg)
            print(f"输入原始文本: '{input_str_arg}'")
            print(f"选择格式选项: {format_choice_arg}")
            print(f"格式化输出: {result}")
        else:
            # 如果没有提供足够的命令行参数，则进入交互模式。
            print("未提供命令行参数，进入交互模式。")
            while True:
                print("请输入原始文本（每行一个项目，输入 '.' 单独一行表示结束）：")
                lines = []
                while True:
                    line = input().strip()
                    if line == ".":
                        break
                    lines.append(line)

                input_str = " ".join(lines).strip()
                if not input_str:
                    print("输入为空，退出程序。")
                    break

                while True:
                    format_choice_input = input("请输入格式选项 (1 或 2): ").strip()
                    try:
                        format_choice = int(format_choice_input)
                        if format_choice in [1, 2]:
                            break
                        else:
                            print("无效的格式选项，请输入 1 或 2。")
                    except ValueError:
                        print("无效的格式选项，请输入整数 1 或 2。")

                result = format_text(input_str, format_choice)
                print(f"处理结果: {result}")
                print("-" * 30)  # 分隔线，方便多次操作

    except Exception as e:
        print(f"程序运行中发生错误: {e}")