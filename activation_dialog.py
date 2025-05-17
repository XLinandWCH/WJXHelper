import os
import uuid
import time
import json
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QMessageBox, QDialogButtonBox, QFrame, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

# DEFAULT_QR_CODE_PATH_FROM_ROOT 被替换为直接使用文件名
ACTIVATIONS_JSON_FILENAME = "activations.json"  # 激活JSON文件名
PAYMENT_QR_FILENAME = "payment_ten.jpg"  # 新的支付二维码文件名


class ActivationDialog(QDialog):
    def __init__(self, project_root_dir, parent=None):
        super().__init__(parent)
        self.project_root_dir = project_root_dir
        self.activations_file_path = os.path.join(self.project_root_dir, ACTIVATIONS_JSON_FILENAME)

        self.setWindowTitle("程序激活 - 支持开发者")
        self.setMinimumWidth(500)

        self.activated_successfully = False  # 标记是否通过此对话框成功激活
        self.validated_uuid_for_activation = None  # 成功激活的UUID
        self.calculated_expiry_timestamp_for_dialog = None  # 激活后的到期时间戳

        # 从JSON文件加载激活信息 (只读，用于验证用户输入的码)
        # 注意：如果用户通过“扫码支付获取”按钮，会直接修改此文件
        self.valid_activations_from_json = self._load_activations_from_json_file()

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        info_label = QLabel(
            "感谢您使用本工具！当免费使用次数达到上限后，我们恳请您考虑支持开发者。\n\n"
            "<b>如何免费获取激活码：</b>\n"
            "1. QQ群: <b>139767507</b>\n"
            "2. 邮箱: <b>xlinandwch@outlook.com</b>\n\n"
            "<b>付费支持并获取月卡激活码：</b>\n"
            "扫描下方支付宝二维码进行任意金额支持后，点击“我已扫码支持，获取月卡激活码”按钮。\n\n"
            "获得激活码后请在下方输入："
        )
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.RichText)
        main_layout.addWidget(info_label)

        main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # --- 支付二维码显示 ---
        qr_path_full = os.path.join(self.project_root_dir, "resources", "icons", PAYMENT_QR_FILENAME)
        if os.path.exists(qr_path_full):
            qr_container_layout = QHBoxLayout()
            qr_container_layout.addStretch()
            payment_qr_display_label = QLabel()
            qr_pixmap = QPixmap(qr_path_full)
            if not qr_pixmap.isNull():
                payment_qr_display_label.setPixmap(qr_pixmap.scaledToWidth(200, Qt.SmoothTransformation))
            else:
                payment_qr_display_label.setText("(二维码图片加载失败)")
            qr_container_layout.addWidget(payment_qr_display_label)
            qr_container_layout.addStretch()
            main_layout.addLayout(qr_container_layout)

            support_label = QLabel("（↑ 支付宝扫码支持 ↑）", alignment=Qt.AlignCenter)
            support_label.setStyleSheet("font-size: 9pt; color: grey;")
            main_layout.addWidget(support_label)

            # --- 新增：扫码支付后获取激活码按钮 ---
            self.get_paid_activation_button = QPushButton("我已扫码支持，获取月卡激活码")
            self.get_paid_activation_button.clicked.connect(self._handle_paid_user_activation_request)
            main_layout.addWidget(self.get_paid_activation_button, 0, Qt.AlignCenter)

        else:
            main_layout.addWidget(QLabel(f"(支付二维码图片未找到: {qr_path_full})", alignment=Qt.AlignCenter))

        main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Fixed))

        line_sep = QFrame()
        line_sep.setFrameShape(QFrame.HLine)
        line_sep.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line_sep)

        activation_input_layout = QHBoxLayout()
        activation_input_layout.addWidget(QLabel("激活码:"))
        self.activation_code_input_field = QLineEdit()
        self.activation_code_input_field.setPlaceholderText("请输入激活码 (通常为UUID格式或UUID_有效期)")
        activation_input_layout.addWidget(self.activation_code_input_field)
        main_layout.addLayout(activation_input_layout)

        self.validation_status_label = QLabel("")  # 用于显示验证状态/错误信息
        self.validation_status_label.setStyleSheet("color: #D32F2F; font-size: 9pt;")  # 红色字体
        main_layout.addWidget(self.validation_status_label)

        dialog_buttons = QDialogButtonBox()
        self.submit_activation_button = dialog_buttons.addButton("激活", QDialogButtonBox.AcceptRole)
        cancel_button = dialog_buttons.addButton("关闭", QDialogButtonBox.RejectRole)

        self.submit_activation_button.clicked.connect(self._process_activation_attempt)
        cancel_button.clicked.connect(self.reject)
        main_layout.addWidget(dialog_buttons)

    def _load_activations_from_json_file(self, file_path=None):  # 辅助方法：从JSON加载激活数据
        # 从指定路径（或默认路径）加载激活数据
        path_to_load = file_path if file_path else self.activations_file_path
        if os.path.exists(path_to_load):
            try:
                with open(path_to_load, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"激活对话框: 读取或解析 {path_to_load} 失败: {e}")
        else:
            print(f"激活对话框: 警告 - 激活文件 {path_to_load} 未找到。")
        return {}

    def _save_activations_to_json_file(self, activations_data, file_path=None):  # 辅助方法：保存激活数据到JSON
        path_to_save = file_path if file_path else self.activations_file_path
        try:
            with open(path_to_save, 'w', encoding='utf-8') as f:
                json.dump(activations_data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"激活对话框: 保存激活数据到 {path_to_save} 文件时出错: {e}")
            QMessageBox.critical(self, "保存错误", f"无法保存激活信息到文件: {e}")
            return False

    def _generate_activation_entry(self, validity_period_code, input_window_seconds=0, description=""):  # 辅助方法：生成激活条目字典
        current_utc_timestamp = time.time()
        return {
            "validity_code": validity_period_code.upper(),
            "issue_timestamp_utc": current_utc_timestamp,
            "input_window_seconds": int(input_window_seconds),  # 此处对于付费码，通常设为0，表示无输入时效
            "description": description,
            "issued_at_readable_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(current_utc_timestamp)),
            "issued_at_readable_local": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(current_utc_timestamp))
        }

    def _handle_paid_user_activation_request(self):  # 处理“我已支付，获取激活码”按钮点击
        # 1. 生成一个新的1个月激活码
        new_uuid_str = str(uuid.uuid4())
        # 确保UUID唯一 (理论上碰撞概率极低，但以防万一还是检查下)
        current_activations = self._load_activations_from_json_file()
        while new_uuid_str in current_activations:
            new_uuid_str = str(uuid.uuid4())

        # 生成一个月 ("1M") 的激活条目
        activation_entry = self._generate_activation_entry(
            validity_period_code="1M",
            input_window_seconds=0,  # 付费用户获得的码通常不设输入时效
            description="通过扫码支付自动生成的月卡激活码"
        )
        current_activations[new_uuid_str] = activation_entry

        # 2. 保存回 activations.json
        if not self._save_activations_to_json_file(current_activations):
            self.validation_status_label.setText("错误：无法保存新生成的激活码。请检查文件权限。")
            return

        # 3. 将UUID填入输入框
        self.activation_code_input_field.setText(new_uuid_str)
        QMessageBox.information(self, "激活码已生成",
                                f"已为您生成一个为期一个月的激活码，并已填入输入框。\nUUID: {new_uuid_str}\n请点击“激活”按钮完成激活。")

        # 4. 自动点击“激活”按钮
        self._process_activation_attempt()  # 触发激活流程

    def _process_activation_attempt(self):  # 处理激活码输入和验证
        user_entered_code = self.activation_code_input_field.text().strip()
        if not user_entered_code:
            self.validation_status_label.setText("请输入激活码。")
            return

        uuid_to_check = user_entered_code.split('_')[0]  # 用户可能输入 UUID 或 UUID_CODE (我们只关心UUID部分)

        try:
            uuid.UUID(uuid_to_check)  # 检查UUID部分格式是否正确
        except ValueError:
            self.validation_status_label.setText("激活码的UUID部分格式不正确。")
            return

        # 重新加载最新的激活数据，特别是如果刚通过“付费获取”按钮生成了新的
        self.valid_activations_from_json = self._load_activations_from_json_file()

        if not self.valid_activations_from_json:
            self.validation_status_label.setText(
                f"无法加载激活数据文件。请联系管理员。({ACTIVATIONS_JSON_FILENAME} 未找到或无效)")
            return

        activation_data_entry = self.valid_activations_from_json.get(uuid_to_check)

        if not activation_data_entry:
            self.validation_status_label.setText("激活码无效或不存在于授权列表。(代码: NF - 未找到)")
            return

        # --- 检查激活码的输入时效性 (基于JSON中的签发时间和输入窗口) ---
        # 此逻辑主要用于管理员预生成的、有输入时限的激活码
        if isinstance(activation_data_entry, dict):
            issue_ts_utc = activation_data_entry.get("issue_timestamp_utc")
            input_win_sec = activation_data_entry.get("input_window_seconds", 0)

            if issue_ts_utc is not None and input_win_sec > 0:  # 仅当有时效窗口时检查
                try:
                    valid_input_deadline = float(issue_ts_utc) + float(input_win_sec)
                    if time.time() > valid_input_deadline:
                        deadline_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(valid_input_deadline))
                        self.validation_status_label.setText(
                            f"此激活码已过输入有效期 (截至 {deadline_str})。(代码: IW - 输入窗口过期)")
                        return
                except ValueError:  # 时间戳或窗口秒数格式错误
                    self.validation_status_label.setText(
                        "激活码配置错误 (时效参数格式无效)。(代码: TCFG - 时效配置错误)")
                    return

        # --- 解析激活后的有效期 (validity_code) ---
        validity_code_after_activation = None
        if isinstance(activation_data_entry, str):  # 兼容旧格式 "UUID": "7D"
            validity_code_after_activation = activation_data_entry.upper()
        elif isinstance(activation_data_entry, dict):
            validity_code_after_activation = activation_data_entry.get("validity_code", "").upper()

        if not validity_code_after_activation:
            self.validation_status_label.setText("激活码配置错误 (有效期代码缺失)。(代码: VCFG - 有效期配置错误)")
            return

        # --- 计算激活后的到期时间戳 ---
        # 注意: 此处的到期时间是基于 *激活码签发时间* + 有效期时长
        now_ts = time.time()  # 当前时间，用于比较是否已过期
        calculated_expiry = 0.0
        duration_msg_part = ""  # 用于成功提示信息

        # 获取签发时间戳，如果没有则认为签发时间就是现在（这主要针对非常旧的、无签发时间戳的码）
        issue_timestamp = now_ts
        if isinstance(activation_data_entry, dict) and "issue_timestamp_utc" in activation_data_entry:
            issue_timestamp = float(activation_data_entry["issue_timestamp_utc"])

        if validity_code_after_activation == "UNL":  # 永久
            calculated_expiry = issue_timestamp + (365 * 20 * 24 * 60 * 60)  # 约20年
            duration_msg_part = "永久 (名义)"
        else:  # 解析如 "7D", "1M"
            val_s = "".join(filter(str.isdigit, validity_code_after_activation))
            unit_s = "".join(filter(str.isalpha, validity_code_after_activation)).upper()
            if val_s.isdigit() and int(val_s) > 0:
                val_i = int(val_s)
                multipliers = {'H': 3600, 'D': 86400, 'M': 30 * 86400, 'Y': 365 * 86400}  # 单位对应的秒数
                if unit_s in multipliers:
                    calculated_expiry = issue_timestamp + val_i * multipliers[unit_s]
                    duration_map = {'H': "小时", 'D': "天", 'M': "个月", 'Y': "年"}
                    duration_msg_part = f"{val_i}{duration_map[unit_s]}"
                else:
                    self.validation_status_label.setText(f"无效的有效期单位: '{unit_s}'。(代码: VUNIT - 有效期单位错误)")
                    return
            else:
                self.validation_status_label.setText(f"无效的有效期数值: '{val_s}'。(代码: VVAL - 有效期数值错误)")
                return

        if calculated_expiry > now_ts:  # 如果计算出的到期时间晚于当前时间，则激活有效
            self.validated_uuid_for_activation = uuid_to_check
            self.calculated_expiry_timestamp_for_dialog = calculated_expiry
            self.activated_successfully = True
            expiry_readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(calculated_expiry))
            QMessageBox.information(self, "激活成功",
                                    f"激活码有效！\n激活后有效期至: {expiry_readable} (约 {duration_msg_part}).\n感谢您的支持！")
            self.accept()  # 关闭对话框并返回 QDialog.Accepted
        else:
            # 到期时间不晚于当前时间，说明已过期
            self.validation_status_label.setText("此激活码已过期或有效期配置不正确。(代码: VEXP - 已过期或有效期无效)")

    def get_activation_details(self):  # 获取激活成功后的UUID和到期时间戳
        if self.activated_successfully:
            return self.validated_uuid_for_activation, self.calculated_expiry_timestamp_for_dialog
        return None, None