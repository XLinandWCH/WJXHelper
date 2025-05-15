# widgets_filling_process.py
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QProgressBar, QTextEdit, QGroupBox, QSpinBox, QFormLayout,
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QSizePolicy, QSplitter)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont  # 导入 QFont
import time
import traceback

from filler_worker import FillerWorker  # 假设 FillerWorker.py 在同一目录或PYTHONPATH中


class FillingProcessWidget(QWidget):
    request_ui_update_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window_ref = parent
        self._init_ui()

        self.workers = {}
        # ... (其他属性初始化不变) ...
        self.worker_id_counter = 0
        self.current_questionnaire_url = None
        self.parsed_questionnaire_data_cache = None
        self.user_raw_configs_template_cache = None
        self.basic_settings_cache = None
        self.user_requested_fills_for_this_job = 0
        self.current_run_actual_target = 0
        self.current_run_completed_fills = 0
        self.current_run_failed_fills = 0
        self.is_globally_paused = False
        self.is_process_running = False
        self.placeholder_worker_id_start = -1000
        self.last_message_for_worker = {}

        self.request_ui_update_signal.connect(self._perform_ui_updates_from_queue)
        self._ui_update_queue = []

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        # ... (控制按钮和总体进度GroupBox的创建与您提供的代码一致) ...
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
        self.stop_button.clicked.connect(self._manual_stop_all_workers)
        control_layout.addWidget(self.stop_button)
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        progress_group = QGroupBox("总体进度 (本次运行)")
        progress_layout = QVBoxLayout()
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setTextVisible(True)
        self.overall_progress_bar.setFormat("本次运行进度: %p% (%v/%m 份)")
        progress_layout.addWidget(self.overall_progress_bar)
        self.stats_label = QLabel("本次已完成: 0 份 | 成功率: N/A | 失败: 0")
        progress_layout.addWidget(self.stats_label)
        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)


        log_group = QGroupBox("线程状态与日志")
        log_layout_for_group = QVBoxLayout()
        self.log_splitter = QSplitter(Qt.Vertical)
        self.thread_status_table = QTableWidget()

        self.thread_status_table.setColumnCount(4)
        self.thread_status_table.setHorizontalHeaderLabels(["线程ID", "状态", "完成数(本线程)", "最新消息"])

        header = self.thread_status_table.horizontalHeader()
        # *** 修改点：允许前三列宽度可交互调整 ***
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # 最新消息列保持拉伸

        # *** 修改点：调整列宽 ***
        self.thread_status_table.setColumnWidth(0, 120)  # 线程ID
        self.thread_status_table.setColumnWidth(1, 180)  # 状态
        self.thread_status_table.setColumnWidth(2, 180 * 2)  # 完成数(本线程) (原180，现在扩大两倍到360)
        # 最新消息列会自动填充剩余空间

        self.thread_status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.thread_status_table.setAlternatingRowColors(True)

        # *** 行高调整：保持之前较大的行高 ***
        self.thread_status_table.verticalHeader().setDefaultSectionSize(45)
        self.thread_status_table.verticalHeader().setVisible(False)

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
        self.log_splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)])
        log_layout_for_group.addWidget(self.log_splitter)
        log_group.setLayout(log_layout_for_group)
        main_layout.addWidget(log_group, 1)

    # --- 其他方法从您提供的最新版本复制过来，保持不变 ---
    def prepare_for_filling(self, url, parsed_questionnaire_data, user_raw_configurations_template, basic_settings):
        self.current_questionnaire_url = url
        self.parsed_questionnaire_data_cache = parsed_questionnaire_data
        self.user_raw_configs_template_cache = user_raw_configurations_template
        self.basic_settings_cache = basic_settings
        self.user_requested_fills_for_this_job = basic_settings.get("num_fills_total", 1)
        self.current_run_completed_fills = 0
        self.current_run_failed_fills = 0
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setFormat("本次运行进度: %p% (%v/%m 份)")
        self.stats_label.setText(f"本次已完成: 0 份 | 成功率: N/A | 失败: 0")
        self.thread_status_table.setRowCount(0)
        self.start_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False);
        self.pause_resume_button.setText("暂停")
        self.stop_button.setEnabled(False)
        self.is_process_running = False
        self.is_globally_paused = False
        self.last_message_for_worker.clear()
        num_threads_display = self.basic_settings_cache.get("num_threads", 1)
        self._log_global_message(
            f"配置已加载。问卷URL: {url[:50]}...，用户目标份数: {self.user_requested_fills_for_this_job}，设定线程数: {num_threads_display}",
            level="system")

    def _log_global_message(self, message_content, level="info", worker_id=None):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        current_level_str = level
        if not isinstance(level, str): current_level_str = "info"
        color_map = {"error": "red", "warn": "orange", "success": "green", "info": "black", "system": "blue",
                     "captcha": "purple"}
        log_color = color_map.get(current_level_str.lower(), "black")
        prefix = f"[线程 {worker_id}] " if worker_id is not None else ""
        # 确保 message_content 是字符串
        message_to_log = str(message_content) if not isinstance(message_content, str) else message_content
        full_log_message = f"<font color='{log_color}'>[{timestamp}] [{current_level_str.upper()}] {prefix}{message_to_log}</font>"
        self.global_log_output.append(full_log_message)
        self.global_log_output.ensureCursorVisible()
        if current_level_str.lower() in ["error", "warn", "system"]:
            print(f"GLOBAL LOG [{current_level_str.upper()}] {prefix}{message_to_log}")

    def _start_filling_process(self):
        if not self.main_window_ref:
            QMessageBox.critical(self, "严重错误", "主窗口引用丢失，无法启动。");
            return
        if not all([self.current_questionnaire_url, self.parsed_questionnaire_data_cache,
                    self.user_raw_configs_template_cache, self.basic_settings_cache]):
            QMessageBox.warning(self, "无法开始", "问卷配置信息不完整。");
            self._log_global_message("启动失败：必要配置信息缺失。", level="error");
            return
        if self.is_process_running:
            QMessageBox.information(self, "提示", "填写过程已经在运行中。");
            return

        self.current_run_completed_fills = 0;
        self.current_run_failed_fills = 0
        self.user_requested_fills_for_this_job = self.basic_settings_cache.get("num_fills_total", 1)
        self.current_run_actual_target = self.user_requested_fills_for_this_job
        is_activated_globally = self.main_window_ref.is_activated
        global_remaining_free_fills = self.main_window_ref.get_remaining_free_fills()
        if not is_activated_globally: self.current_run_actual_target = min(self.user_requested_fills_for_this_job,
                                                                           global_remaining_free_fills)
        if self.current_run_actual_target <= 0:
            msg = "免费额度已用尽。" if not is_activated_globally and global_remaining_free_fills <= 0 else "目标填写份数为0或无效。"
            QMessageBox.information(self, "无法开始", f"无法启动填写过程：{msg}")
            self._log_global_message(f"启动中止：{msg}", level="warn");
            self._finish_filling_process(message=f"启动中止：{msg}");
            return

        self.is_process_running = True
        self._update_control_buttons_state()
        self.overall_progress_bar.setMaximum(self.current_run_actual_target);
        self.overall_progress_bar.setValue(0)
        self._add_ui_update_task('overall_progress')

        num_threads_user_requested = self.basic_settings_cache.get("num_threads", 1)
        active_thread_count_for_this_run = min(num_threads_user_requested,
                                               self.current_run_actual_target) if not is_activated_globally else num_threads_user_requested
        active_thread_count_for_this_run = max(1, active_thread_count_for_this_run)

        fills_per_thread = [0] * active_thread_count_for_this_run
        if active_thread_count_for_this_run > 0:
            base_fills = self.current_run_actual_target // active_thread_count_for_this_run
            extra_fills = self.current_run_actual_target % active_thread_count_for_this_run
            for i in range(active_thread_count_for_this_run): fills_per_thread[i] = base_fills + (
                1 if i < extra_fills else 0)

        self.thread_status_table.setRowCount(num_threads_user_requested)
        self.workers.clear();
        self.last_message_for_worker.clear()
        actual_workers_started_count = 0
        for i in range(num_threads_user_requested):
            self.worker_id_counter += 1;
            current_processing_worker_id = self.worker_id_counter
            if i < active_thread_count_for_this_run and fills_per_thread[i] > 0:
                worker = FillerWorker(worker_id=current_processing_worker_id, url=self.current_questionnaire_url,
                                      user_raw_configurations_template=self.user_raw_configs_template_cache,
                                      num_fills_for_this_worker=fills_per_thread[i],
                                      total_target_fills=self.current_run_actual_target,
                                      headless=self.basic_settings_cache.get("headless", True),
                                      proxy=self.basic_settings_cache.get("proxy"),
                                      msedgedriver_path=self.basic_settings_cache.get("msedgedriver_path"))
                worker.progress_signal.connect(self._on_worker_progress)
                worker.single_fill_finished_signal.connect(self._on_worker_single_fill_finished)
                worker.worker_completed_all_fills_signal.connect(self._on_worker_completed_all)
                self.workers[current_processing_worker_id] = worker
                initial_msg = "准备启动..."
                self.last_message_for_worker[current_processing_worker_id] = initial_msg
                self._add_ui_update_task('table_row', current_processing_worker_id, i, "准备中...", 0,
                                         fills_per_thread[i], initial_msg)
                worker.start();
                actual_workers_started_count += 1
                self._log_global_message(f"启动，目标 {fills_per_thread[i]} 份。", level="info",
                                         worker_id=current_processing_worker_id)
            else:
                placeholder_id_for_table = self.placeholder_worker_id_start - i
                status_text = "额度受限" if (
                            not is_activated_globally and i >= active_thread_count_for_this_run) else "空闲"
                message_text = "为节约免费次数未启动" if status_text == "额度受限" else "无任务分配"
                self._add_ui_update_task('table_row', placeholder_id_for_table, i, status_text, 0, 0, message_text,
                                         (QColor(220, 220, 255) if status_text == "额度受限" else None))
                self._log_global_message(f"线程槽位 ({status_text}): {message_text}", level="info")
        self.request_ui_update_signal.emit()
        if actual_workers_started_count == 0 and self.current_run_actual_target > 0:
            self._log_global_message("未能启动任何工作线程。", level="error")
            QMessageBox.warning(self, "启动失败", "没有工作线程成功启动。");
            self._finish_filling_process(message="未能启动工作线程。")

    def _find_row_for_worker(self, worker_id_to_find):
        for row in range(self.thread_status_table.rowCount()):
            item = self.thread_status_table.item(row, 0)
            if item and item.text() == str(worker_id_to_find): return row
        return -1

    def _add_ui_update_task(self, task_type, *args):
        self._ui_update_queue.append((task_type, args))

    def _perform_ui_updates_from_queue(self):
        for task_type, args in self._ui_update_queue:
            if task_type == 'table_row':
                self._update_thread_table_row_internal(*args)
            elif task_type == 'overall_progress':
                self._update_overall_progress_display_internal()
            elif task_type == 'control_buttons':
                self._update_control_buttons_state_internal()
        self._ui_update_queue.clear()
        app_instance = QApplication.instance();
        if app_instance: app_instance.processEvents()

    def _update_thread_table_row_internal(self, worker_id_or_placeholder, row_index, status_text,
                                          completed_count, target_count,
                                          message, color_override=None):
        if row_index < 0 or row_index >= self.thread_status_table.rowCount(): return
        try:
            self.thread_status_table.setItem(row_index, 0, QTableWidgetItem(str(worker_id_or_placeholder)))
            self.thread_status_table.setItem(row_index, 1, QTableWidgetItem(status_text))
            self.thread_status_table.setItem(row_index, 2, QTableWidgetItem(str(completed_count)))

            msg_to_display = str(message)
            msg_item = QTableWidgetItem(msg_to_display)
            self.thread_status_table.setItem(row_index, 3, msg_item)

            final_bg_color = color_override
            if not final_bg_color:
                if "失败" in status_text or "错误" in status_text:
                    final_bg_color = QColor(255, 200, 200)
                elif "成功" in status_text or "已完成" in status_text:
                    final_bg_color = QColor(200, 255, 200)
                elif "验证码" in status_text:
                    final_bg_color = QColor(220, 200, 255)
            if final_bg_color:
                for col in range(self.thread_status_table.columnCount()):
                    item = self.thread_status_table.item(row_index, col)
                    if not item: item = QTableWidgetItem(""); self.thread_status_table.setItem(row_index, col, item)
                    item.setBackground(final_bg_color)
        except Exception as e:
            print(f"ERROR in _update_thread_table_row_internal: {e}"); traceback.print_exc()

    def _update_overall_progress_display_internal(self):
        if self.current_run_actual_target > 0:
            self.overall_progress_bar.setValue(self.current_run_completed_fills)
            self.overall_progress_bar.setMaximum(self.current_run_actual_target)
        else:
            self.overall_progress_bar.setValue(0); self.overall_progress_bar.setMaximum(1)
        total_attempted = self.current_run_completed_fills + self.current_run_failed_fills
        success_rate_str = f"{((self.current_run_completed_fills / total_attempted) * 100):.1f}%" if total_attempted > 0 else "N/A"
        self.stats_label.setText(
            f"本次已完成: {self.current_run_completed_fills} 份 | 成功率: {success_rate_str} (总尝试: {total_attempted}) | 失败: {self.current_run_failed_fills}")

    def _update_control_buttons_state_internal(self):
        self.start_button.setEnabled(not self.is_process_running)
        self.pause_resume_button.setEnabled(self.is_process_running)
        self.pause_resume_button.setText("继续" if self.is_globally_paused and self.is_process_running else "暂停")
        self.stop_button.setEnabled(self.is_process_running)

    def _update_control_buttons_state(self):
        self._add_ui_update_task('control_buttons')
        self.request_ui_update_signal.emit()

    def _on_worker_progress(self, worker_id, _ignored_int1, _ignored_int2, msg_type_from_signal, message_from_worker):
        if not self.is_process_running: return
        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        current_msg_type_str = msg_type_from_signal
        if not isinstance(msg_type_from_signal, str): current_msg_type_str = "info"
        status_text = "运行中"
        if current_msg_type_str.lower() == "error":
            status_text = "错误"
        elif current_msg_type_str.lower() == "captcha":
            status_text = "验证码"
        self.last_message_for_worker[worker_id] = message_from_worker
        self._add_ui_update_task('table_row',
                                 worker_id, row_idx, status_text,
                                 worker_ref.fills_completed_by_this_worker,
                                 worker_ref.num_fills_to_complete_by_worker,
                                 message_from_worker
                                 )
        self._log_global_message(message_from_worker, level=current_msg_type_str, worker_id=worker_id)
        self.request_ui_update_signal.emit()

    def _on_worker_single_fill_finished(self, worker_id, success, message_or_url):
        if not self.is_process_running: return
        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        status_text = "";
        log_level = ""
        if success:
            self.main_window_ref.increment_global_fill_count()
            self.current_run_completed_fills += 1
            status_text = "单次成功";
            log_level = "success"
        else:
            self.current_run_failed_fills += 1
            status_text = "单次失败";
            log_level = "error"
        self.last_message_for_worker[worker_id] = message_or_url
        self._add_ui_update_task('table_row', worker_id, row_idx, status_text,
                                 worker_ref.fills_completed_by_this_worker,
                                 worker_ref.num_fills_to_complete_by_worker, message_or_url)
        self._log_global_message(f"{status_text}。详情: {message_or_url}", level=log_level, worker_id=worker_id)
        self._add_ui_update_task('overall_progress')
        should_stop_due_to_limits = False;
        stop_msg = ""
        if not self.main_window_ref.is_activated and self.main_window_ref.get_remaining_free_fills() <= 0:
            self._log_global_message("全局免费额度已用尽...", level="warn", worker_id=None)
            QMessageBox.warning(self, "免费额度用尽", "免费填写次数已用完。任务将中止。")
            should_stop_due_to_limits = True;
            stop_msg = "免费额度用尽。任务中止。"
        if not should_stop_due_to_limits and self.current_run_completed_fills >= self.current_run_actual_target:
            self._log_global_message(f"已达到本次运行目标 {self.current_run_actual_target} 份。", level="info",
                                     worker_id=None)
            should_stop_due_to_limits = True;
            stop_msg = f"已完成目标({self.current_run_actual_target}份)。任务中止。"
        if should_stop_due_to_limits and self.is_process_running:
            self.stop_all_workers_forcefully(
                is_target_reached=(self.current_run_completed_fills >= self.current_run_actual_target),
                message_override=stop_msg)
        self.request_ui_update_signal.emit()

    def _on_worker_completed_all(self, worker_id):
        if not self.is_process_running: return
        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        completion_message = "此线程任务结束"
        self.last_message_for_worker[worker_id] = completion_message
        self._add_ui_update_task('table_row', worker_id, row_idx, "已完成(本线程)",
                                 worker_ref.fills_completed_by_this_worker,
                                 worker_ref.num_fills_to_complete_by_worker, completion_message)
        self._log_global_message(completion_message, level="info", worker_id=worker_id)
        all_threads_really_finished = all(not w.isRunning() for w in self.workers.values())
        if all_threads_really_finished and self.is_process_running:
            final_msg = "所有线程完成任务。" if self.current_run_completed_fills >= self.current_run_actual_target else "所有活动线程结束，但未达总目标。"
            self._log_global_message(final_msg, level="system", worker_id=None)
            self.stop_all_workers_forcefully(
                is_target_reached=(self.current_run_completed_fills >= self.current_run_actual_target),
                message_override=final_msg)
        self.request_ui_update_signal.emit()

    def _toggle_pause_resume(self):
        if not self.is_process_running or not self.workers: return
        self.is_globally_paused = not self.is_globally_paused
        action_method_name = "pause_worker" if self.is_globally_paused else "resume_worker"
        log_action_text = '暂停' if self.is_globally_paused else '恢复'
        self._log_global_message(f"用户{log_action_text}所有线程。", level="system")
        for worker_id, worker in self.workers.items():
            if worker.isRunning():
                getattr(worker, action_method_name)()
                row_idx = self._find_row_for_worker(worker_id)
                if row_idx != -1:
                    s_item = self.thread_status_table.item(row_idx, 1);
                    status_now = s_item.text() if s_item else "未知"
                    new_status = f"已暂停 ({status_now})" if self.is_globally_paused and not status_now.startswith(
                        "已暂停") else \
                        (status_now[len("已暂停 ("):-1] if status_now.startswith(
                            "已暂停 (") and not self.is_globally_paused else status_now)
                    current_latest_message = self.last_message_for_worker.get(worker_id, "")
                    self._add_ui_update_task('table_row', worker_id, row_idx, new_status,
                                             worker.fills_completed_by_this_worker,
                                             worker.num_fills_to_complete_by_worker,
                                             current_latest_message)
        self._update_control_buttons_state()
        self.request_ui_update_signal.emit()

    def _manual_stop_all_workers(self):
        if not self.is_process_running and not self.workers:
            self._log_global_message("没有正在运行的任务可停止。", level="info");
            return
        reply = QMessageBox.question(self, '确认停止', "确定要停止所有正在进行的填写任务吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.stop_all_workers_forcefully(is_target_reached=False, message_override="用户手动停止所有任务。")

    def stop_all_workers_forcefully(self, is_target_reached=False, message_override=None):
        if not self.is_process_running and not self.workers:
            self._update_control_buttons_state();
            return
        log_msg_base = message_override if message_override else (
            "已达到目标份数。" if is_target_reached else "用户中止。")
        self._log_global_message(log_msg_base + " 正在停止所有线程...",
                                 level="warn" if not is_target_reached else "system")
        for worker_id, worker in list(self.workers.items()):
            if worker.isRunning(): worker.stop_worker()
            row_idx = self._find_row_for_worker(worker_id)
            if row_idx != -1:
                self.last_message_for_worker[worker_id] = log_msg_base
                self._add_ui_update_task('table_row', worker_id, row_idx, "已停止",
                                         getattr(worker, 'fills_completed_by_this_worker', 0),
                                         getattr(worker, 'num_fills_to_complete_by_worker', 0),
                                         log_msg_base)
        self._finish_filling_process(message=log_msg_base + " 所有任务已处理停止请求。")
        self.request_ui_update_signal.emit()

    def _finish_filling_process(self, message="填写过程结束。"):
        self.is_process_running = False
        self.is_globally_paused = False
        self._update_control_buttons_state()
        self._log_global_message(message, level="system")
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage(message, 5000)

    def closeEvent(self, event):
        if self.is_process_running:
            self.stop_all_workers_forcefully(is_target_reached=False, message_override="窗口关闭，任务中止。")
        super().closeEvent(event)