# widgets_filling_process.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QProgressBar, QTextEdit, QGroupBox, QSpinBox, QFormLayout,
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QSizePolicy, QSplitter)  # 导入 QSplitter 和 QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
import time
import random

from filler_worker import FillerWorker


class FillingProcessWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window_ref = parent
        self._init_ui()  # 先初始化UI

        self.workers = {}
        self.worker_id_counter = 0
        self.total_fills_target = 0
        self.total_fills_completed = 0
        self.total_fills_failed = 0

        self.current_questionnaire_url = None
        self.parsed_questionnaire_data_cache = None
        # !!! 修改点: 存储原始配置模板 !!!
        self.user_raw_configs_template_cache = None
        self.basic_settings_cache = None

        self.is_globally_paused = False
        self.is_process_running = False

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- 控制区 ---
        control_group = QGroupBox("填写控制")
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("开始填写")
        self.start_button.setObjectName("StartButton")
        self.start_button.clicked.connect(self._start_filling_process)
        control_layout.addWidget(self.start_button)
        self.pause_resume_button = QPushButton("暂停")
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.clicked.connect(self._toggle_pause_resume)
        control_layout.addWidget(self.pause_resume_button)
        self.stop_button = QPushButton("停止全部")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_all_workers)
        control_layout.addWidget(self.stop_button)
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # --- 总体进度 ---
        progress_group = QGroupBox("总体进度")
        progress_layout = QVBoxLayout()
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setTextVisible(True)
        self.overall_progress_bar.setFormat("总进度: %p% (%v/%m 份)")
        progress_layout.addWidget(self.overall_progress_bar)
        self.stats_label = QLabel("已完成: 0 份 | 成功率: N/A | 预计剩余时间: N/A")
        progress_layout.addWidget(self.stats_label)
        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)

        # --- 线程状态和日志 (使用 QSplitter) ---
        log_group = QGroupBox("线程状态与日志")
        log_layout_for_group = QVBoxLayout()  # GroupBox需要一个主布局

        # !!! 修改点: 使用 QSplitter !!!
        self.log_splitter = QSplitter(Qt.Vertical)  # 创建垂直分割器

        # 表格部分
        self.thread_status_table = QTableWidget()
        self.thread_status_table.setColumnCount(5)
        self.thread_status_table.setHorizontalHeaderLabels(["线程ID", "状态", "完成数", "单次进度", "最新消息"])
        self.thread_status_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.thread_status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.thread_status_table.setColumnWidth(0, 60)
        self.thread_status_table.setColumnWidth(1, 80)
        self.thread_status_table.setColumnWidth(2, 80)
        self.thread_status_table.setColumnWidth(3, 150)
        self.thread_status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # self.thread_status_table.setMinimumHeight(150) # 由Splitter管理高度

        # 全局日志输出区域 (作为Splitter的第二个子控件)
        log_output_container = QWidget()  # 给日志文本和标签一个容器
        log_output_vlayout = QVBoxLayout(log_output_container)
        log_output_vlayout.setContentsMargins(0, 0, 0, 0)
        log_output_vlayout.addWidget(QLabel("全局日志:"))
        self.global_log_output = QTextEdit()
        self.global_log_output.setReadOnly(True)
        self.global_log_output.setObjectName("StatusLog")
        # self.global_log_output.setFixedHeight(100) # 移除固定高度
        log_output_vlayout.addWidget(self.global_log_output)

        self.log_splitter.addWidget(self.thread_status_table)
        self.log_splitter.addWidget(log_output_container)  # 将包含日志的容器添加到splitter

        # 设置初始分割比例或大小 (可选)
        self.log_splitter.setStretchFactor(0, 1)  # 表格部分拉伸因子为1
        self.log_splitter.setStretchFactor(1, 1)  # 日志部分拉伸因子为1 (初始均分)
        # 或者 self.log_splitter.setSizes([200, 150]) # 设置初始高度

        log_layout_for_group.addWidget(self.log_splitter)  # 将Splitter添加到GroupBox的布局
        log_group.setLayout(log_layout_for_group)
        main_layout.addWidget(log_group, 1)  # 让log_group在主布局中可拉伸

    # !!! 修改点: prepare_for_filling 参数名 !!!
    def prepare_for_filling(self, url, parsed_questionnaire_data, user_raw_configurations_template, basic_settings):
        self.current_questionnaire_url = url
        self.parsed_questionnaire_data_cache = parsed_questionnaire_data
        # !!! 修改点: 存储原始配置模板 !!!
        self.user_raw_configs_template_cache = user_raw_configurations_template
        self.basic_settings_cache = basic_settings

        # 重置统计数据和UI
        self.total_fills_target = basic_settings.get("num_fills_total", 1)
        self.total_fills_completed = 0
        self.total_fills_failed = 0
        self.overall_progress_bar.setMaximum(self.total_fills_target if self.total_fills_target > 0 else 1)  # 避免max为0
        self.overall_progress_bar.setValue(0)
        self.stats_label.setText(f"已完成: 0 份 | 成功率: N/A | 预计剩余时间: N/A")
        self.thread_status_table.setRowCount(0)
        self.global_log_output.clear()

        self.start_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.is_process_running = False
        self.is_globally_paused = False
        self.pause_resume_button.setText("暂停")

        self._log_global_message(
            f"配置已加载。问卷URL: {url[:50]}...，目标份数: {self.total_fills_target}，线程数: {basic_settings.get('num_threads', 1)}")

    def _log_global_message(self, message, level="info"):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        # 为确保HTML换行正确，使用<br>而不是\n
        if level == "error":
            formatted_message = f"<font color='red'>[{timestamp}] [{level.upper()}] {message}</font>"
        elif level == "warn":
            formatted_message = f"<font color='orange'>[{timestamp}] [{level.upper()}] {message}</font>"
        elif level == "success":
            formatted_message = f"<font color='green'>[{timestamp}] [{level.upper()}] {message}</font>"
        else:
            formatted_message = f"[{timestamp}] [{level.upper()}] {message}"
        self.global_log_output.append(formatted_message)  # QTextEdit 会自动处理 <br>

    def _start_filling_process(self):
        # !!! 修改点: 检查 self.user_raw_configs_template_cache !!!
        if not self.current_questionnaire_url or \
                not self.parsed_questionnaire_data_cache or \
                not self.user_raw_configs_template_cache or \
                not self.basic_settings_cache:
            QMessageBox.warning(self, "无法开始", "问卷配置信息不完整，请返回“问卷配置”页面检查。")
            return

        if self.is_process_running:
            QMessageBox.information(self, "提示", "填写过程已经在运行中。")
            return

        num_threads = self.basic_settings_cache.get("num_threads", 1)
        self.total_fills_target = self.basic_settings_cache.get("num_fills_total", 1)

        # 确保 target 大于0
        if self.total_fills_target <= 0:
            QMessageBox.warning(self, "提示", "目标填写份数必须大于0。")
            return

        if self.total_fills_completed >= self.total_fills_target:
            QMessageBox.information(self, "提示", "已达到目标填写份数。如需重新开始，请调整目标份数。")
            return

        self.is_process_running = True
        self.start_button.setEnabled(False)
        self.pause_resume_button.setEnabled(True)
        self.pause_resume_button.setText("暂停")
        self.is_globally_paused = False
        self.stop_button.setEnabled(True)

        self.overall_progress_bar.setMaximum(self.total_fills_target)
        self._update_overall_progress_display()

        actual_num_threads_to_start = min(num_threads, self.total_fills_target - self.total_fills_completed)
        if actual_num_threads_to_start <= 0:
            self._log_global_message("没有需要启动的线程 (可能已完成或目标为0)。", "warn")
            # 重置按钮状态
            self.is_process_running = False
            self.start_button.setEnabled(True)
            self.pause_resume_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            return

        fills_per_thread = (self.total_fills_target - self.total_fills_completed) // actual_num_threads_to_start
        remaining_fills = (self.total_fills_target - self.total_fills_completed) % actual_num_threads_to_start

        self.thread_status_table.setRowCount(actual_num_threads_to_start)

        for i in range(actual_num_threads_to_start):
            self.worker_id_counter += 1
            worker_id = self.worker_id_counter
            num_fills_for_this_thread = fills_per_thread + (1 if i < remaining_fills else 0)
            if num_fills_for_this_thread == 0: continue

            # !!! 修改点: 传递 user_raw_configs_template_cache 给 Worker !!!
            worker = FillerWorker(
                worker_id=worker_id,
                url=self.current_questionnaire_url,
                # 修改这里:
                user_raw_configurations_template=self.user_raw_configs_template_cache,
                num_fills_for_this_worker=num_fills_for_this_thread,
                total_target_fills=self.total_fills_target,
                headless=self.basic_settings_cache.get("headless", True),  # 从设置获取headless
                proxy=self.basic_settings_cache.get("proxy"),
                msedgedriver_path=self.basic_settings_cache.get("msedgedriver_path")
            )
            worker.progress_signal.connect(self._on_worker_progress)
            worker.single_fill_finished_signal.connect(self._on_worker_single_fill_finished)
            worker.worker_completed_all_fills_signal.connect(self._on_worker_completed_all)

            self.workers[worker_id] = worker
            self._update_thread_table_row(worker_id, i, "准备中...", 0, num_fills_for_this_thread, "")
            worker.start()
            self._log_global_message(f"启动线程 {worker_id}，目标填写 {num_fills_for_this_thread} 份。")

        if not self.workers:
            self._log_global_message("未能启动任何工作线程。", "error")
            self.is_process_running = False
            self.start_button.setEnabled(True)
            self.pause_resume_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    # ... ( _find_row_for_worker, _update_thread_table_row, _on_worker_progress,
    #       _on_worker_single_fill_finished, _on_worker_completed_all,
    #       _update_overall_progress_display, _toggle_pause_resume,
    #       _stop_all_workers, stop_all_workers_forcefully, _finish_filling_process, closeEvent
    #       这些方法保持不变，因为它们不直接处理配置的随机化，而是显示和控制流程 )
    # ... （请将您之前文件中的这些方法粘贴回此处，我只展示了修改的部分）

    # --- 以下是之前文件中未修改的方法，请确保它们存在 ---
    def _find_row_for_worker(self, worker_id):
        for row in range(self.thread_status_table.rowCount()):
            item = self.thread_status_table.item(row, 0)
            if item and int(item.text()) == worker_id:
                return row
        return -1

    def _update_thread_table_row(self, worker_id, row_index, status_text, completed_count, target_count, message,
                                 progress_val=None):
        if row_index < 0 or row_index >= self.thread_status_table.rowCount():
            existing_row = self._find_row_for_worker(worker_id)
            if existing_row != -1:
                row_index = existing_row
            else:
                self._log_global_message(f"更新表格失败：线程 {worker_id} 的行索引 {row_index} 无效。", "error")
                return

        self.thread_status_table.setItem(row_index, 0, QTableWidgetItem(str(worker_id)))
        self.thread_status_table.setItem(row_index, 1, QTableWidgetItem(status_text))
        self.thread_status_table.setItem(row_index, 2, QTableWidgetItem(f"{completed_count}/{target_count}"))

        if progress_val is not None:
            progress_bar_item = QProgressBar()
            progress_bar_item.setRange(0, 100)
            progress_bar_item.setValue(progress_val)
            progress_bar_item.setTextVisible(True)
            progress_bar_item.setFormat("%p%")
            self.thread_status_table.setCellWidget(row_index, 3, progress_bar_item)
        elif status_text in ["完成", "已完成(本线程)", "失败", "单次失败", "已停止"]:  # 更全面的结束状态
            if self.thread_status_table.cellWidget(row_index, 3):
                self.thread_status_table.removeCellWidget(row_index, 3)
            self.thread_status_table.setItem(row_index, 3, QTableWidgetItem("N/A"))
        elif self.thread_status_table.cellWidget(row_index, 3) is None and status_text not in ["准备中..."]:
            self.thread_status_table.setItem(row_index, 3, QTableWidgetItem("进行中..."))

        msg_item = QTableWidgetItem(message[:100] + "..." if len(message) > 100 else message)
        self.thread_status_table.setItem(row_index, 4, msg_item)

        bg_color = QColor(Qt.white)  # 默认背景
        if "失败" in status_text or "错误" in status_text or "error" == message.lower().split("] ")[-1].split(":")[
            0].strip('[] '):
            bg_color = QColor(255, 220, 220)  # 淡红色
        elif "成功" in status_text or "success" == message.lower().split("] ")[-1].split(":")[0].strip('[] '):
            bg_color = QColor(220, 255, 220)  # 淡绿色

        for col in range(self.thread_status_table.columnCount()):
            table_item = self.thread_status_table.item(row_index, col)
            if table_item:  # 确保item存在
                table_item.setBackground(bg_color)

    def _on_worker_progress(self, worker_id, current_done_by_worker, target_for_worker, msg_type, message):
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return

        status_text = "运行中"
        if msg_type == "error":
            status_text = "错误"
        elif msg_type == "captcha":
            status_text = "验证码"
        elif msg_type == "success_once":
            status_text = "单次成功"  # 这个状态可能很快被 single_fill_finished覆盖

        self._update_thread_table_row(worker_id, row_idx, status_text, current_done_by_worker, target_for_worker,
                                      message)
        self._log_global_message(f"线程 {worker_id}: {message}", msg_type)

    def _on_worker_single_fill_finished(self, worker_id, success, message_or_url):
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return

        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return

        completed_by_worker = worker_ref.fills_completed_by_this_worker
        target_for_worker = worker_ref.num_fills_to_complete_by_worker

        if success:
            self.total_fills_completed += 1
            self._update_thread_table_row(worker_id, row_idx, "单次成功", completed_by_worker, target_for_worker,
                                          message_or_url)
            self._log_global_message(f"线程 {worker_id} 成功完成1份。详情: {message_or_url}", "success")
        else:
            self.total_fills_failed += 1
            self._update_thread_table_row(worker_id, row_idx, "单次失败", completed_by_worker, target_for_worker,
                                          message_or_url)
            self._log_global_message(f"线程 {worker_id} 完成1份失败。原因: {message_or_url}", "error")

        self._update_overall_progress_display()

        if self.total_fills_completed >= self.total_fills_target:
            self._log_global_message(f"已达到总目标 {self.total_fills_target} 份，正在停止所有线程...", "info")
            self.stop_all_workers_forcefully(is_target_reached=True)

    def _on_worker_completed_all(self, worker_id):
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return

        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return

        completed_by_worker = worker_ref.fills_completed_by_this_worker
        target_for_worker = worker_ref.num_fills_to_complete_by_worker

        self._update_thread_table_row(worker_id, row_idx, "已完成(本线程)", completed_by_worker, target_for_worker,
                                      "此线程任务结束")
        self._log_global_message(f"线程 {worker_id} 已完成其全部分配任务。", "info")

        all_done = True
        for w in self.workers.values():
            if w.isRunning():
                all_done = False
                break

        if all_done and self.is_process_running:
            self._log_global_message("所有线程均已完成其任务或已停止。", "info")
            self._finish_filling_process(message="所有任务完成。")

    def _update_overall_progress_display(self):
        if self.total_fills_target > 0:
            self.overall_progress_bar.setValue(self.total_fills_completed)
        else:
            self.overall_progress_bar.setValue(0)

        total_attempted = self.total_fills_completed + self.total_fills_failed
        success_rate_str = "N/A"
        if total_attempted > 0:
            success_rate = (self.total_fills_completed / total_attempted) * 100
            success_rate_str = f"{success_rate:.1f}%"

        self.stats_label.setText(
            f"已完成: {self.total_fills_completed} 份 | 成功率: {success_rate_str} (总尝试: {total_attempted}) | 失败: {self.total_fills_failed}")

    def _toggle_pause_resume(self):
        if not self.is_process_running or not self.workers: return

        self.is_globally_paused = not self.is_globally_paused
        action_method = "pause_worker" if self.is_globally_paused else "resume_worker"
        button_text = "继续" if self.is_globally_paused else "暂停"
        log_message = "所有线程已暂停。" if self.is_globally_paused else "所有线程已恢复。"

        self.pause_resume_button.setText(button_text)
        self._log_global_message(log_message, "info")
        for worker in self.workers.values():
            if worker.isRunning():  # 只有还在运行的worker才需要响应
                getattr(worker, action_method)()

    def _stop_all_workers(self):
        reply = QMessageBox.question(self, '确认停止',
                                     "确定要停止所有正在进行的填写任务吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.stop_all_workers_forcefully()

    def stop_all_workers_forcefully(self, is_target_reached=False):
        if not self.workers and not self.is_process_running: return

        self._log_global_message("正在停止所有工作线程...", "warn")
        for worker_id, worker in list(self.workers.items()):
            if worker.isRunning():
                worker.stop_worker()

            row_idx = self._find_row_for_worker(worker_id)
            if row_idx != -1:
                self._update_thread_table_row(worker_id, row_idx, "已停止",
                                              worker.fills_completed_by_this_worker,
                                              worker.num_fills_to_complete_by_worker,
                                              "用户或系统中止")

        if not is_target_reached:
            self._finish_filling_process(message="用户手动停止了所有任务。")
        else:
            self._finish_filling_process(message="已达到目标份数，所有任务结束。")

    def _finish_filling_process(self, message="填写过程结束。"):
        self.is_process_running = False
        self.is_globally_paused = False

        self.start_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.setText("暂停")
        self.stop_button.setEnabled(False)

        self._log_global_message(message, "info")
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage(message)

    def closeEvent(self, event):
        self.stop_all_workers_forcefully()
        super().closeEvent(event)

