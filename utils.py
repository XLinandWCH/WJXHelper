# utils.py
import numpy
import re


def normalize_probabilities(prob_dict_or_list):
    """
    参数归一化，把概率值按比例缩放到概率值和为1。
    接受字典或列表。如果是字典，会修改其值。如果是列表，会返回新列表。
    """
    if isinstance(prob_dict_or_list, dict):
        for key in prob_dict_or_list:
            if isinstance(prob_dict_or_list[key], list) and sum(prob_dict_or_list[key]) > 0:
                prob_sum = sum(prob_dict_or_list[key])
                prob_dict_or_list[key] = [x / prob_sum for x in prob_dict_or_list[key]]
        return prob_dict_or_list
    elif isinstance(prob_dict_or_list, list):
        normalized_list = []
        for item in prob_dict_or_list:
            if isinstance(item, list) and sum(item) > 0:
                prob_sum = sum(item)
                normalized_list.append([x / prob_sum for x in item])
            else:
                normalized_list.append(item)  # 例如 -1 代表随机
        return normalized_list
    return prob_dict_or_list


def validate_ip_proxy(ip_string):
    """校验IP代理地址合法性 (例如: 127.0.0.1:8080)"""
    if not ip_string:
        return False
    # 简单的IP:端口格式校验，可以根据需要增强
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}$"
    return bool(re.match(pattern, ip_string))


def parse_weights_from_string(weight_str, num_options):
    """
    从逗号分隔的字符串解析权重。
    如果解析失败或数量不匹配，返回等权重的列表。
    """
    try:
        weights = [abs(int(w.strip())) for w in weight_str.split(',')]  # 权重必须非负
        if len(weights) == num_options:
            if sum(weights) == 0:  # 如果所有权重都是0，则均等处理
                return [1] * num_options
            return weights
    except ValueError:
        pass  # 解析失败
    return [1] * num_options  # 默认等权重


def calculate_choice_from_weights(weights_list):
    """
    根据权重列表（已经是数字列表），返回一个按概率选择的索引。
    如果权重列表为空或总和为0，则返回-1表示无法选择或随机（取决于调用者如何处理）。
    """
    if not weights_list or sum(weights_list) == 0:
        return -1  # 或其他表示错误/随机的值

    # 归一化概率
    probabilities = [w / sum(weights_list) for w in weights_list]

    # 生成0到len-1的索引
    indices = list(range(len(weights_list)))

    # 按概率选择一个索引
    chosen_index = numpy.random.choice(indices, p=probabilities)
    return chosen_index


def calculate_multiple_choices_from_percentages(percentage_list):
    """
    根据每个选项的选择百分比列表（例如 [100, 30, 20]），
    返回一个被选中选项的索引列表。
    """
    selected_indices = []
    for i, percentage in enumerate(percentage_list):
        if not (0 <= percentage <= 100):
            # 如果概率值无效，可以默认不选或按50%处理，这里简单跳过或认为不选
            prob = 0
        else:
            prob = percentage / 100.0

        if numpy.random.rand() < prob:
            selected_indices.append(i)
    return selected_indices

