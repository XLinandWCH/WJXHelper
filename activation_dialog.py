
import os
import uuid
import time
import json
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QMessageBox, QDialogButtonBox, QFrame)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

DEFAULT_QR_CODE_PATH_FROM_ROOT = os.path.join("resources", "icons", "payment_qr.png")  # 或 "为爱发电.png"
ACTIVATIONS_JSON_FILENAME = "activations.json"  # 与 main_app.py 中一致


class ActivationDialog(QDialog):
    def __init__(self, project_root_dir, parent=None):
        super().__init__(parent)
        self.project_root_dir = project_root_dir
        self.activations_file_path = os.path.join(self.project_root_dir, ACTIVATIONS_JSON_FILENAME)

        self.setWindowTitle("程序激活 - 支持开发者")
        self.setMinimumWidth(450)  # 可以适当调整宽度

        self.activated_successfully = False
        self.validated_uuid_for_activation = None  # 保存验证通过的UUID
        self.calculated_expiry_timestamp_for_dialog = None  # 保存计算出的激活后过期时间戳

        self.valid_activations_from_json = self._load_activations_from_json_file()

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        info_label = QLabel(
            "感谢您使用本工具！当免费使用次数达到上限后，我们恳请您考虑支持开发者。\n\n"
            "<b>如何免费获取激活码：</b>\n"
            "1. QQ群: <b>139767507</b>\n"
            "2. 邮箱: <b>xlinandwch@outlook.com</b>\n\n"
            "获得激活码后请在下方输入："
        )
        info_label.setWordWrap(True);
        info_label.setTextFormat(Qt.RichText)
        main_layout.addWidget(info_label)

        # 支付二维码显示
        qr_path = os.path.join(self.project_root_dir, "resources", "icons", "为爱发电.png")  # 使用 "为爱发电.png"
        if os.path.exists(qr_path):
            qr_container_layout = QHBoxLayout()
            qr_container_layout.addStretch()
            payment_qr_display_label = QLabel()
            qr_pixmap = QPixmap(qr_path)
            if not qr_pixmap.isNull():
                # 增大二维码显示尺寸
                payment_qr_display_label.setPixmap(qr_pixmap.scaledToWidth(200, Qt.SmoothTransformation))
            else:
                payment_qr_display_label.setText("(二维码图片加载失败)")
            qr_container_layout.addWidget(payment_qr_display_label)
            qr_container_layout.addStretch()
            main_layout.addLayout(qr_container_layout)
            main_layout.addWidget(QLabel("（↑ 若您愿意赞助，可扫描支持 ↑）", alignment=Qt.AlignCenter))
        else:
            main_layout.addWidget(QLabel(f"(二维码图片未找到: {qr_path})", alignment=Qt.AlignCenter))

        line_sep = QFrame();
        line_sep.setFrameShape(QFrame.HLine);
        line_sep.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line_sep)

        activation_input_layout = QHBoxLayout()
        activation_input_layout.addWidget(QLabel("激活码:"))
        self.activation_code_input_field = QLineEdit()
        self.activation_code_input_field.setPlaceholderText("请输入激活码 (通常为UUID_有效期格式)")
        activation_input_layout.addWidget(self.activation_code_input_field)
        main_layout.addLayout(activation_input_layout)

        self.validation_status_label = QLabel("")  # 用于显示验证信息
        self.validation_status_label.setStyleSheet("color: #D32F2F; font-size: 9pt;")  # 红色错误提示
        main_layout.addWidget(self.validation_status_label)

        dialog_buttons = QDialogButtonBox()
        self.submit_activation_button = dialog_buttons.addButton("激活", QDialogButtonBox.AcceptRole)
        cancel_button = dialog_buttons.addButton("关闭", QDialogButtonBox.RejectRole)
        self.submit_activation_button.clicked.connect(self._process_activation_attempt)
        cancel_button.clicked.connect(self.reject)
        main_layout.addWidget(dialog_buttons)

    def _load_activations_from_json_file(self):
        """从JSON文件加载激活数据。"""
        if os.path.exists(self.activations_file_path):
            try:
                with open(self.activations_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    print(f"ActivationDialog: 从 {self.activations_file_path} 加载 {len(data)} 条激活数据。")
                    return data
            except Exception as e:
                print(f"ActivationDialog: 读取或解析 {self.activations_file_path} 失败: {e}")
        else:
            print(f"ActivationDialog: 警告 - 激活文件 {self.activations_file_path} 未找到。")
        return {}

    def _process_activation_attempt(self):
        """处理用户提交的激活码。"""
        user_entered_code = self.activation_code_input_field.text().strip()
        if not user_entered_code:
            self.validation_status_label.setText("请输入激活码。")
            return

        # 用户可能只输入UUID，也可能输入UUID_有效期格式。我们主要用UUID部分去查。
        uuid_to_check = user_entered_code.split('_')[0]

        try:  # 基本的UUID格式检查
            uuid.UUID(uuid_to_check)
        except ValueError:
            self.validation_status_label.setText("激活码的UUID部分格式不正确。")
            return

        if not self.valid_activations_from_json:
            self.validation_status_label.setText(f"无法加载激活数据文件。请联系管理员。")
            return

        activation_data_entry = self.valid_activations_from_json.get(uuid_to_check)

        if not activation_data_entry:
            self.validation_status_label.setText("激活码无效或不存在于授权列表。 (NF)")
            return

        # --- 检查激活码的输入时效性 ---
        if isinstance(activation_data_entry, dict):
            issue_ts_utc = activation_data_entry.get("issue_timestamp_utc")
            input_win_sec = activation_data_entry.get("input_window_seconds", 0)  # 默认为0，不限制

            if issue_ts_utc is not None and input_win_sec > 0:
                try:
                    valid_input_deadline = float(issue_ts_utc) + float(input_win_sec)
                    if time.time() > valid_input_deadline:
                        deadline_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(valid_input_deadline))
                        self.validation_status_label.setText(f"此激活码已过输入有效期 (截至 {deadline_str})。")
                        return
                except ValueError:  # 时间戳或窗口期格式问题
                    self.validation_status_label.setText("激活码配置错误 (时效参数)。")
                    return
        # --- 输入时效性检查结束 ---

        # --- 解析激活后的有效期 ---
        validity_code_after_activation = None
        if isinstance(activation_data_entry, str):  # 兼容旧的简单格式
            validity_code_after_activation = activation_data_entry.upper()
        elif isinstance(activation_data_entry, dict):
            validity_code_after_activation = activation_data_entry.get("validity_code", "").upper()

        if not validity_code_after_activation:
            self.validation_status_label.setText("激活码配置错误 (有效期代码缺失)。")
            return

        now_ts = time.time()
        calculated_expiry = 0.0
        duration_msg_part = ""

        if validity_code_after_activation == "UNL":
            calculated_expiry = now_ts + (365 * 20 * 24 * 60 * 60)  # 20年
            duration_msg_part = "永久"
        else:
            val_s = "".join(filter(str.isdigit, validity_code_after_activation))
            unit_s = "".join(filter(str.isalpha, validity_code_after_activation)).upper()
            if val_s.isdigit() and int(val_s) > 0:
                val_i = int(val_s)
                if unit_s == 'H':
                    calculated_expiry = now_ts + val_i * 3600; duration_msg_part = f"{val_i}小时"
                elif unit_s == 'D':
                    calculated_expiry = now_ts + val_i * 86400; duration_msg_part = f"{val_i}天"
                elif unit_s == 'M':
                    calculated_expiry = now_ts + val_i * 30 * 86400; duration_msg_part = f"{val_i}个月"
                elif unit_s == 'Y':
                    calculated_expiry = now_ts + val_i * 365 * 86400; duration_msg_part = f"{val_i}年"
                else:
                    self.validation_status_label.setText(f"无效的有效期单位: '{unit_s}'。")
                    return
            else:
                self.validation_status_label.setText(f"无效的有效期数值: '{val_s}'。")
                return

        if calculated_expiry > now_ts:
            self.validated_uuid_for_activation = uuid_to_check
            self.calculated_expiry_timestamp_for_dialog = calculated_expiry
            self.activated_successfully = True
            QMessageBox.information(self, "激活成功",
                                    f"激活码有效！\n激活后有效期至: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(calculated_expiry))} ({duration_msg_part}).\n感谢您的支持！")
            self.accept()  # 关闭对话框并返回 QDialog.Accepted
        else:
            self.validation_status_label.setText("此激活码已过期 (根据其设定)。")

    def get_activation_details(self):
        """供主窗口调用，获取验证成功的UUID和计算出的过期时间戳。"""
        if self.activated_successfully:
            return self.validated_uuid_for_activation, self.calculated_expiry_timestamp_for_dialog
        return None, None


