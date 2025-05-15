from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QProgressBar, QTextEdit, QGroupBox, QSpinBox, QFormLayout,
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QSizePolicy, QSplitter)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
import time
import random
import traceback

from filler_worker import FillerWorker


class FillingProcessWidget(QWidget):
    def __init__(self, parent=None):  # parent is MainWindow
        super().__init__(parent)
        self.main_window_ref = parent  # 保存对主窗口的引用
        self._init_ui()

        self.workers = {}
        self.worker_id_counter = 0
        self.total_fills_target = 0  # 本地任务的目标
        self.total_fills_completed = 0  # 本地任务的完成数
        self.total_fills_failed = 0  # 本地任务的失败数

        self.current_questionnaire_url = None
        self.parsed_questionnaire_data_cache = None
        self.user_raw_configs_template_cache = None
        self.basic_settings_cache = None

        self.is_globally_paused = False
        self.is_process_running = False

    def _init_ui(self):  # UI代码不变，确保它存在
        main_layout = QVBoxLayout(self)
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

        log_group = QGroupBox("线程状态与日志")
        log_layout_for_group = QVBoxLayout()
        self.log_splitter = QSplitter(Qt.Vertical)
        self.thread_status_table = QTableWidget()
        self.thread_status_table.setColumnCount(5)
        self.thread_status_table.setHorizontalHeaderLabels(["线程ID", "状态", "完成数", "单次进度", "最新消息"])
        self.thread_status_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.thread_status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.thread_status_table.setColumnWidth(0, 60);
        self.thread_status_table.setColumnWidth(1, 80)
        self.thread_status_table.setColumnWidth(2, 80);
        self.thread_status_table.setColumnWidth(3, 150)
        self.thread_status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        log_output_container = QWidget()
        log_output_vlayout = QVBoxLayout(log_output_container)
        log_output_vlayout.setContentsMargins(0, 0, 0, 0)
        log_output_vlayout.addWidget(QLabel("全局日志:"))
        self.global_log_output = QTextEdit()
        self.global_log_output.setReadOnly(True)
        self.global_log_output.setObjectName("StatusLog")
        log_output_vlayout.addWidget(self.global_log_output)
        self.log_splitter.addWidget(self.thread_status_table)
        self.log_splitter.addWidget(log_output_container)
        self.log_splitter.setStretchFactor(0, 1)
        self.log_splitter.setStretchFactor(1, 1)
        log_layout_for_group.addWidget(self.log_splitter)
        log_group.setLayout(log_layout_for_group)
        main_layout.addWidget(log_group, 1)

    def prepare_for_filling(self, url, parsed_questionnaire_data, user_raw_configurations_template,
                            basic_settings):  # 此方法不变
        print("FillingProcessWidget: prepare_for_filling called.")
        self.current_questionnaire_url = url
        self.parsed_questionnaire_data_cache = parsed_questionnaire_data
        self.user_raw_configs_template_cache = user_raw_configurations_template
        self.basic_settings_cache = basic_settings

        self.total_fills_target = basic_settings.get("num_fills_total", 1)
        self.total_fills_completed = 0  # 重置本地计数
        self.total_fills_failed = 0  # 重置本地计数
        self.overall_progress_bar.setMaximum(self.total_fills_target if self.total_fills_target > 0 else 1)
        self.overall_progress_bar.setValue(0)
        self.stats_label.setText(f"已完成: 0 份 | 成功率: N/A")
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

    def _log_global_message(self, message, level="info"):  # 此方法不变
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        if level == "error":
            formatted_message = f"<font color='red'>[{timestamp}] [{level.upper()}] {message}</font>"
        elif level == "warn":
            formatted_message = f"<font color='orange'>[{timestamp}] [{level.upper()}] {message}</font>"
        elif level == "success":
            formatted_message = f"<font color='green'>[{timestamp}] [{level.upper()}] {message}</font>"
        else:
            formatted_message = f"[{timestamp}] [{level.upper()}] {message}"
        self.global_log_output.append(formatted_message)

    def _start_filling_process(self):
        print("FillingProcessWidget: _start_filling_process called.")
        # *** 调用主窗口的检查逻辑 ***
        if self.main_window_ref and hasattr(self.main_window_ref, '_can_proceed_with_filling'):
            if not self.main_window_ref._can_proceed_with_filling():
                self._log_global_message("启动中止：未激活或达到使用限制。", "warn")
                # 确保开始按钮可用，以便用户激活后重试
                self.start_button.setEnabled(True)
                return
        else:  # 如果没有主窗口引用或方法，可能在独立测试，给出警告
            print("FillingProcessWidget: 警告 - 无法访问主窗口的激活检查逻辑。")

        # 后续逻辑与之前基本一致，除了在成功时调用主窗口的计数增加
        if not self.current_questionnaire_url or \
                not self.parsed_questionnaire_data_cache or \
                not self.user_raw_configs_template_cache or \
                not self.basic_settings_cache:
            QMessageBox.warning(self, "无法开始", "问卷配置信息不完整，请返回“问卷配置”页面并重新加载问卷和检查设置。")
            self._log_global_message("启动失败：必要配置信息缺失。", "error")
            return

        if self.is_process_running:
            QMessageBox.information(self, "提示", "填写过程已经在运行中。")
            return

        num_threads = self.basic_settings_cache.get("num_threads", 1)
        self.total_fills_target = self.basic_settings_cache.get("num_fills_total", 1)  # 本地任务目标

        if self.total_fills_target <= 0:
            QMessageBox.warning(self, "提示", "目标填写份数必须大于0。")
            return

        if self.total_fills_completed >= self.total_fills_target:  # 检查本地任务是否已完成
            QMessageBox.information(self, "提示", "此任务已达到目标填写份数。如需重新开始，请调整目标份数或重置。")
            return

        self.is_process_running = True
        self.start_button.setEnabled(False)
        self.pause_resume_button.setEnabled(True)
        self.pause_resume_button.setText("暂停")
        self.is_globally_paused = False
        self.stop_button.setEnabled(True)

        self.overall_progress_bar.setMaximum(self.total_fills_target)
        self._update_overall_progress_display()

        # 确定实际需要的填写份数 (考虑全局已填写数和激活状态)
        # 这部分主要由 _can_proceed_with_filling 控制了，这里主要计算本地任务的分配
        remaining_local_target_fills = self.total_fills_target - self.total_fills_completed
        actual_num_threads_to_start = min(num_threads, remaining_local_target_fills)

        if actual_num_threads_to_start <= 0:
            self._log_global_message("没有需要启动的线程 (本地任务可能已完成或目标为0)。", "warn")
            self._finish_filling_process(message="本地任务没有需要执行的。")
            return

        fills_per_thread = remaining_local_target_fills // actual_num_threads_to_start
        extra_fills = remaining_local_target_fills % actual_num_threads_to_start

        self.thread_status_table.setRowCount(actual_num_threads_to_start)
        self.workers.clear()

        for i in range(actual_num_threads_to_start):
            self.worker_id_counter += 1
            worker_id = self.worker_id_counter
            num_fills_for_this_thread = fills_per_thread + (1 if i < extra_fills else 0)
            if num_fills_for_this_thread == 0: continue

            worker = FillerWorker(
                worker_id=worker_id,
                url=self.current_questionnaire_url,
                user_raw_configurations_template=self.user_raw_configs_template_cache,
                num_fills_for_this_worker=num_fills_for_this_thread,
                total_target_fills=self.total_fills_target,  # 这个参数worker内部可能不直接用
                headless=self.basic_settings_cache.get("headless", True),
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
            self._finish_filling_process(message="未能启动工作线程。")

    def _find_row_for_worker(self, worker_id):  # 此方法不变
        for row in range(self.thread_status_table.rowCount()):
            item = self.thread_status_table.item(row, 0)
            if item and int(item.text()) == worker_id: return row
        return -1

    def _update_thread_table_row(self, worker_id, row_index, status_text, completed_count, target_count, message,
                                 progress_val=None):  # 此方法不变
        if row_index < 0 or row_index >= self.thread_status_table.rowCount():
            existing_row = self._find_row_for_worker(worker_id)
            if existing_row != -1:
                row_index = existing_row
            else:
                # self._log_global_message(f"更新表格失败：线程 {worker_id} 的行索引 {row_index} 无效。", "error")
                return  # 避免在线程结束时因找不到行而报错
        self.thread_status_table.setItem(row_index, 0, QTableWidgetItem(str(worker_id)))
        self.thread_status_table.setItem(row_index, 1, QTableWidgetItem(status_text))
        self.thread_status_table.setItem(row_index, 2, QTableWidgetItem(f"{completed_count}/{target_count}"))
        if progress_val is not None:
            progress_bar_item = QProgressBar()
            progress_bar_item.setRange(0, 100);
            progress_bar_item.setValue(progress_val)
            progress_bar_item.setTextVisible(True);
            progress_bar_item.setFormat("%p%")
            self.thread_status_table.setCellWidget(row_index, 3, progress_bar_item)
        elif status_text in ["完成", "已完成(本线程)", "失败", "单次失败", "已停止"]:
            if self.thread_status_table.cellWidget(row_index, 3): self.thread_status_table.removeCellWidget(row_index,
                                                                                                            3)
            self.thread_status_table.setItem(row_index, 3, QTableWidgetItem("N/A"))
        elif self.thread_status_table.cellWidget(row_index, 3) is None and status_text not in ["准备中..."]:
            self.thread_status_table.setItem(row_index, 3, QTableWidgetItem("进行中..."))

        msg_item = QTableWidgetItem(message[:100] + "..." if len(message) > 100 else message)
        self.thread_status_table.setItem(row_index, 4, msg_item)

        bg_color = QColor(Qt.white)
        msg_type_from_message = ""
        if "] " in message:
            try:
                msg_type_from_message = message.split("] ")[0].split("[")[-1].lower()
            except:
                pass  # 防一手解析错误

        if "error" == msg_type_from_message or "失败" in status_text:
            bg_color = QColor(255, 220, 220)
        elif "success" == msg_type_from_message or "成功" in status_text:
            bg_color = QColor(220, 255, 220)

        for col in range(self.thread_status_table.columnCount()):
            table_item = self.thread_status_table.item(row_index, col)
            if table_item: table_item.setBackground(bg_color)

    def _on_worker_progress(self, worker_id, current_done_by_worker, target_for_worker, msg_type, message):  # 此方法不变
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        status_text = "运行中"
        if msg_type == "error":
            status_text = "错误"
        elif msg_type == "captcha":
            status_text = "验证码"
        elif msg_type == "success_once":
            status_text = "单次成功"
        self._update_thread_table_row(worker_id, row_idx, status_text, current_done_by_worker, target_for_worker,
                                      f"[{msg_type.upper()}] {message}")  # 传递消息类型给表格
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
            # *** 通知主窗口增加全局计数 ***
            if self.main_window_ref and hasattr(self.main_window_ref, 'increment_global_fill_count'):
                self.main_window_ref.increment_global_fill_count()

            self._update_thread_table_row(worker_id, row_idx, "单次成功", completed_by_worker, target_for_worker,
                                          f"[SUCCESS] {message_or_url}")
            self._log_global_message(f"线程 {worker_id} 成功完成1份。详情: {message_or_url}", "success")
        else:
            self.total_fills_failed += 1
            self._update_thread_table_row(worker_id, row_idx, "单次失败", completed_by_worker, target_for_worker,
                                          f"[FAIL] {message_or_url}")
            self._log_global_message(f"线程 {worker_id} 完成1份失败。原因: {message_or_url}", "error")

        self._update_overall_progress_display()

        # 检查本地任务是否完成
        if self.total_fills_completed >= self.total_fills_target and self.is_process_running:
            self._log_global_message(f"此轮任务已达到目标 {self.total_fills_target} 份，正在停止所有线程...", "info")
            self.stop_all_workers_forcefully(is_target_reached=True)
        # 检查全局限制 (如果主窗口可访问)
        elif self.main_window_ref and hasattr(self.main_window_ref, '_can_proceed_with_filling'):
            if not self.main_window_ref._can_proceed_with_filling():  # 如果在填写过程中激活失效或次数用尽
                self._log_global_message(f"全局限制已触发或激活失效，正在停止所有线程...", "warn")
                self.stop_all_workers_forcefully(is_target_reached=False)

    def _on_worker_completed_all(self, worker_id):  # 此方法不变
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return
        completed_by_worker = worker_ref.fills_completed_by_this_worker
        target_for_worker = worker_ref.num_fills_to_complete_by_worker
        self._update_thread_table_row(worker_id, row_idx, "已完成(本线程)", completed_by_worker, target_for_worker,
                                      "此线程任务结束")
        self._log_global_message(f"线程 {worker_id} 已完成其全部分配任务。", "info")

        all_threads_finished_or_stopped = True
        for w_instance in self.workers.values():
            if w_instance.isRunning():
                all_threads_finished_or_stopped = False
                break
        if all_threads_finished_or_stopped and self.is_process_running:
            self._log_global_message("所有线程均已完成其任务或已停止。", "info")
            self._finish_filling_process(message="所有任务完成。")

    def _update_overall_progress_display(self):  # 此方法不变
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
            f"已完成: {self.total_fills_completed} 份 | 成功率: {success_rate_str} (本地尝试: {total_attempted}) | 失败: {self.total_fills_failed}")

    def _toggle_pause_resume(self):  # 此方法不变
        if not self.is_process_running or not self.workers: return
        self.is_globally_paused = not self.is_globally_paused
        action_method_name = "pause_worker" if self.is_globally_paused else "resume_worker"
        button_text = "继续" if self.is_globally_paused else "暂停"
        log_message = "所有线程已暂停。" if self.is_globally_paused else "所有线程已恢复。"
        self.pause_resume_button.setText(button_text)
        self._log_global_message(log_message, "info")
        for worker in self.workers.values():
            if worker.isRunning(): getattr(worker, action_method_name)()

    def _stop_all_workers(self):  # 此方法不变
        if not self.is_process_running and not self.workers:
            self._log_global_message("没有正在运行的任务可停止。", "info")
            return
        reply = QMessageBox.question(self, '确认停止', "确定要停止所有正在进行的填写任务吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.stop_all_workers_forcefully()

    def stop_all_workers_forcefully(self, is_target_reached=False):  # 此方法不变
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

        # 不立即清空 self.workers，等待线程真正结束
        # self.workers.clear()

        if not is_target_reached:
            self._finish_filling_process(message="用户手动停止了所有任务。")
        else:
            self._finish_filling_process(message="已达到目标份数，所有任务结束。")

    def _finish_filling_process(self, message="填写过程结束。"):  # 此方法不变
        self.is_process_running = False
        self.is_globally_paused = False
        self.start_button.setEnabled(True)  # 允许重新开始新任务
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.setText("暂停")
        self.stop_button.setEnabled(False)
        self._log_global_message(message, "info")
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage(message, 5000)

    def closeEvent(self, event):  # 此方法不变
        if self.is_process_running:
            self.stop_all_workers_forcefully()
        super().closeEvent(event)
