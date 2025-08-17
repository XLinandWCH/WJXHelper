# widgets_filling_process.py
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QProgressBar, QTextEdit, QGroupBox, QSpinBox, QFormLayout,
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QSizePolicy, QSplitter)
# 确保导入 QColor, QMutex 和 QThread
from PyQt5.QtCore import Qt, pyqtSignal, QMutex, QThread
from PyQt5.QtGui import QColor, QBrush, QFont # <--- 确保 QColor 在导入列表中
import time
import traceback
import re # 用于_toggle_pause_resume中解析暂停状态文本

from filler_worker import FillerWorker  # FillerWorker 的 __init__ 已修改


class FillingProcessWidget(QWidget):
    request_ui_update_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window_ref = parent
        self._init_ui()
        self.workers = {}
        self.worker_id_counter = 0
        self.current_questionnaire_url = None
        self.parsed_questionnaire_data_cache = None
        self.user_raw_configs_template_cache = None
        self.basic_settings_cache = None  # 这个将包含浏览器配置
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

        # --- 新增：用于多线程顺序填空的共享索引和互斥锁 ---
        # 这个字典存储每个顺序填空题 (通过其 q_div_id 标识) 在所有线程中共同的下一个答案索引。
        # 键是问题的 q_div_id，值是下一个应该使用的答案在答案列表中的索引。
        self._shared_sequential_indices = {}
        # 这个互斥锁用于在多个线程访问 _shared_sequential_indices 时进行保护，确保线程安全。
        self._sequential_indices_mutex = QMutex()
        # --- 新增结束 ---


    def _init_ui(self):  # (UI部分保持不变)
        main_layout = QVBoxLayout(self);
        control_group = QGroupBox("填写控制");
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("开始填写");
        self.start_button.setObjectName("StartButton");
        self.start_button.clicked.connect(self._start_filling_process);
        control_layout.addWidget(self.start_button)
        self.pause_resume_button = QPushButton("暂停");
        self.pause_resume_button.setEnabled(False);
        self.pause_resume_button.clicked.connect(self._toggle_pause_resume);
        control_layout.addWidget(self.pause_resume_button)
        self.stop_button = QPushButton("停止全部");
        self.stop_button.setEnabled(False);
        self.stop_button.clicked.connect(self._manual_stop_all_workers);
        control_layout.addWidget(self.stop_button)
        control_group.setLayout(control_layout);
        main_layout.addWidget(control_group)
        progress_group = QGroupBox("总体进度 (本次运行)");
        progress_layout = QVBoxLayout()
        self.overall_progress_bar = QProgressBar();
        self.overall_progress_bar.setValue(0);
        self.overall_progress_bar.setTextVisible(True);
        self.overall_progress_bar.setFormat("本次运行进度: %p% (%v/%m 份)");
        progress_layout.addWidget(self.overall_progress_bar)
        self.stats_label = QLabel("本次已完成: 0 份 | 成功率: N/A | 失败: 0");
        progress_layout.addWidget(self.stats_label)
        progress_group.setLayout(progress_layout);
        main_layout.addWidget(progress_group)
        log_group = QGroupBox("线程状态与日志");
        log_layout_for_group = QVBoxLayout();
        self.log_splitter = QSplitter(Qt.Vertical);
        self.thread_status_table = QTableWidget()
        self.thread_status_table.setColumnCount(4);
        self.thread_status_table.setHorizontalHeaderLabels(["线程ID", "状态", "完成数(本线程)", "最新消息"])
        header = self.thread_status_table.horizontalHeader();
        header.setSectionResizeMode(0, QHeaderView.Interactive);
        header.setSectionResizeMode(1, QHeaderView.Interactive);
        header.setSectionResizeMode(2, QHeaderView.Interactive);
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.thread_status_table.setColumnWidth(0, 120);
        self.thread_status_table.setColumnWidth(1, 180);
        self.thread_status_table.setColumnWidth(2, 180 * 2)
        self.thread_status_table.setEditTriggers(QTableWidget.NoEditTriggers);
        self.thread_status_table.setAlternatingRowColors(True)
        self.thread_status_table.verticalHeader().setDefaultSectionSize(45);
        self.thread_status_table.verticalHeader().setVisible(False)
        log_output_container = QWidget();
        log_output_vlayout = QVBoxLayout(log_output_container);
        log_output_vlayout.setContentsMargins(0, 0, 0, 0);
        log_output_vlayout.addWidget(QLabel("全局日志:"))
        self.global_log_output = QTextEdit();
        self.global_log_output.setReadOnly(True);
        self.global_log_output.setObjectName("StatusLog");
        log_output_vlayout.addWidget(self.global_log_output)
        self.log_splitter.addWidget(self.thread_status_table);
        self.log_splitter.addWidget(log_output_container);
        self.log_splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)])
        log_layout_for_group.addWidget(self.log_splitter);
        log_group.setLayout(log_layout_for_group);
        main_layout.addWidget(log_group, 1)

    def prepare_for_filling(self, url, parsed_questionnaire_data, user_raw_configurations_template,
                            basic_settings):  # (保持不变)
        self.current_questionnaire_url = url;
        self.parsed_questionnaire_data_cache = parsed_questionnaire_data;
        self.user_raw_configs_template_cache = user_raw_configurations_template
        self.basic_settings_cache = basic_settings;
        self.user_requested_fills_for_this_job = basic_settings.get("num_fills_total", 1)
        self.current_run_completed_fills = 0;
        self.current_run_failed_fills = 0;
        self.overall_progress_bar.setValue(0);
        self.overall_progress_bar.setFormat("本次运行进度: %p% (%v/%m 份)")
        self.stats_label.setText(f"本次已完成: 0 份 | 成功率: N/A | 失败: 0");
        self.thread_status_table.setRowCount(0)
        self.start_button.setEnabled(True);
        self.pause_resume_button.setEnabled(False);
        self.pause_resume_button.setText("暂停");
        self.stop_button.setEnabled(False)
        self.is_process_running = False;
        self.is_globally_paused = False;
        self.last_message_for_worker.clear()
        num_threads_display = self.basic_settings_cache.get("num_threads", 1);
        browser_type_display = self.basic_settings_cache.get("browser_type", "edge")
        self._log_global_message(
            f"配置已加载. URL: {url[:50]}..., 目标: {self.user_requested_fills_for_this_job}, 线程: {num_threads_display}, 浏览器: {browser_type_display.capitalize()}",
            level="system")

    def _log_global_message(self, message_content, level="info", worker_id=None):  # (保持不变)
        timestamp = time.strftime("%H:%M:%S", time.localtime());
        current_level_str = level if isinstance(level, str) else "info"
        color_map = {"error": "red", "warn": "orange", "success": "green", "info": "black", "system": "blue",
                     "captcha": "purple", "debug": "gray"}; # Added debug color
        log_color = color_map.get(current_level_str.lower(), "black")
        prefix = f"[线程 {worker_id}] " if worker_id is not None else "";
        message_to_log = str(message_content) if not isinstance(message_content, str) else message_content
        full_log_message = f"<font color='{log_color}'>[{timestamp}] [{current_level_str.upper()}] {prefix}{message_to_log}</font>"
        self.global_log_output.append(full_log_message);
        self.global_log_output.ensureCursorVisible()
        # Optionally print to console for easier debugging outside GUI
        # if current_level_str.lower() in ["error", "warn", "system", "info", "debug", "captcha"]:
        #     print(f"GLOBAL CONSOLE LOG [{current_level_str.upper()}] {prefix}{message_to_log}")


    # (*** 修改点：_start_filling_process 方法 ***)
    # 在创建 Worker 实例时传递共享的顺序填空索引字典和互斥锁
    # 同时修正 _add_ui_update_task 的调用参数
    def _start_filling_process(self):
        self._log_global_message("尝试启动填写过程...", level="system")
        if not self.main_window_ref:
            QMessageBox.critical(self, "严重错误", "主窗口引用丢失，无法启动。")
            self._log_global_message("启动失败:主窗口引用丢失", level="error")
            return
        if not all([self.current_questionnaire_url, self.parsed_questionnaire_data_cache,
                    self.user_raw_configs_template_cache, self.basic_settings_cache]):
            QMessageBox.warning(self, "无法开始", "问卷配置信息不完整。")
            self._log_global_message("启动失败：必要配置信息缺失。", level="error")
            return
        if self.is_process_running:
            QMessageBox.information(self, "提示", "填写过程已经在运行中。")
            return

        self.current_run_completed_fills = 0
        self.current_run_failed_fills = 0
        self.user_requested_fills_for_this_job = self.basic_settings_cache.get("num_fills_total", 1)  # 从缓存获取
        self.current_run_actual_target = self.user_requested_fills_for_this_job
        is_activated_globally = self.main_window_ref.is_activated if hasattr(self.main_window_ref, 'is_activated') else False # 增加检查
        global_remaining_free_fills = self.main_window_ref.get_remaining_free_fills() if hasattr(self.main_window_ref, 'get_remaining_free_fills') else 0 # 增加检查


        # 如果未激活，实际目标不能超过免费额度
        if not is_activated_globally:
             # 如果免费额度有限，实际目标是用户 requested 和 免费额度中较小的一个
             self.current_run_actual_target = min(self.user_requested_fills_for_this_job, global_remaining_free_fills)
             if self.current_run_actual_target < self.user_requested_fills_for_this_job:
                 self._log_global_message(f"警告: 未激活，本次填写目标限制为免费额度 {self.current_run_actual_target} 份。", level="warn")
        else:
             # 已激活，实际目标就是用户请求的目标份数
             self.current_run_actual_target = self.user_requested_fills_for_this_job


        if self.current_run_actual_target <= 0:
            msg = "免费额度已用尽。" if not is_activated_globally and global_remaining_free_fills <= 0 else "目标填写份数为0或无效。"
            QMessageBox.information(self, "无法开始", f"无法启动填写过程：{msg}")
            self._log_global_message(f"启动中止：{msg}", level="warn")
            self._finish_filling_process(message=f"启动中止：{msg}")
            return

        self.is_process_running = True
        self._update_control_buttons_state()
        self.overall_progress_bar.setMaximum(self.current_run_actual_target)
        self.overall_progress_bar.setValue(0)
        # Update overall progress display immediately
        self._update_overall_progress_display_internal()


        num_threads_user_requested = self.basic_settings_cache.get("num_threads", 1)  # 从缓存获取
        # 实际启动的线程数取决于用户请求数和目标份数（未激活时），但不超过请求数
        active_thread_count_for_this_run = min(num_threads_user_requested, self.current_run_actual_target) if not is_activated_globally else num_threads_user_requested
        active_thread_count_for_this_run = max(1, active_thread_count_for_this_run) # 至少一个线程（如果目标>0）

        # 计算每个线程分配的份数
        fills_per_thread = [0] * active_thread_count_for_this_run
        if active_thread_count_for_this_run > 0:
            base_fills = self.current_run_actual_target // active_thread_count_for_this_run
            extra_fills = self.current_run_actual_target % active_thread_count_for_this_run
            for i in range(active_thread_count_for_this_run):
                 fills_per_thread[i] = base_fills + (1 if i < extra_fills else 0)

        # 设置表格行数，包括所有请求的线程槽位
        self.thread_status_table.setRowCount(num_threads_user_requested)
        self.workers.clear()
        self.last_message_for_worker.clear()
        actual_workers_started_count = 0

        # --- 在启动 Worker 之前，清空共享的顺序填空索引字典 ---
        # 这样确保每次“开始填写”任务时，顺序填空都从每个问题的第一个答案开始。
        self._shared_sequential_indices.clear()
        self._log_global_message("顺序填空索引已重置为本次任务。", level="debug")
        # --- 清空共享索引结束 ---


        # --- 从 basic_settings_cache 获取浏览器配置 ---
        current_browser_type = self.basic_settings_cache.get("browser_type", "edge")
        # 注意键名应与 settings 中的一致，如果 settings 中保存的是 driver_path，这里就是 driver_path
        current_driver_path = self.basic_settings_cache.get("driver_path", None)
        # ---

        for i in range(num_threads_user_requested): # 遍历用户请求的线程槽位
            self.worker_id_counter += 1 # 为每个可能的Worker分配一个唯一的计数器ID
            current_processing_worker_id = self.worker_id_counter

            # 只有分配到任务的线程才真正创建 Worker 实例
            if i < active_thread_count_for_this_run and fills_per_thread[i] > 0:
                worker = FillerWorker(
                    worker_id=current_processing_worker_id,
                    url=self.current_questionnaire_url,
                    user_raw_configurations_template=self.user_raw_configs_template_cache,
                    num_fills_for_this_worker=fills_per_thread[i],
                    total_target_fills=self.current_run_actual_target,
                    # --- 传递正确的浏览器参数 ---
                    browser_type=current_browser_type,
                    driver_executable_path=current_driver_path, # 使用从 settings 获取的路径
                    # ---
                    headless=self.basic_settings_cache.get("headless_mode", True), # 修正键名，应与 settings 中的一致
                    proxy=self.basic_settings_cache.get("proxy", None), # 修正键名，应与 settings 中的一致
                    base_user_data_dir_path=self.main_window_ref.base_user_data_dir_for_workers if hasattr(self.main_window_ref, 'base_user_data_dir_for_workers') else None, # 从MainWindow获取共享的用户数据目录基础路径，并增加检查
                    # --- 关键修改：传递共享字典和互斥锁给 Worker ---
                    shared_sequential_indices=self._shared_sequential_indices,
                    sequential_indices_mutex=self._sequential_indices_mutex,
                    human_like_mode_config=self.basic_settings_cache.get("human_like_mode_config")
                )
                worker.progress_signal.connect(self._on_worker_progress)
                worker.single_fill_finished_signal.connect(self._on_worker_single_fill_finished)
                worker.worker_completed_all_fills_signal.connect(self._on_worker_completed_all)
                self.workers[current_processing_worker_id] = worker # 将实际启动的Worker存储到字典
                initial_msg = "准备启动..."
                self.last_message_for_worker[current_processing_worker_id] = initial_msg
                # Update table row for active worker - ensure 7 arguments are passed
                self._add_ui_update_task('table_row', current_processing_worker_id, i, "准备中...", 0,
                                         fills_per_thread[i], initial_msg, None) # <-- 添加 None 作为 color_override
                worker.start() # 启动 Worker 线程
                actual_workers_started_count += 1
                self._log_global_message(f"线程槽位 {i+1}: ID {current_processing_worker_id} 启动 ({current_browser_type}), 目标 {fills_per_thread[i]} 份。", level="info",
                                         worker_id=current_processing_worker_id)
            else:
                # 对于未分配任务的线程槽位，只更新表格显示状态
                placeholder_id_for_table = self.placeholder_worker_id_start - i
                status_text = "额度受限" if (
                            not is_activated_globally and i >= active_thread_count_for_this_run) else "空闲"
                message_text = "为节约免费次数未启动" if status_text == "额度受限" else "无任务分配"
                # Update table row for placeholder - ensure 7 arguments are passed
                self._add_ui_update_task('table_row', placeholder_id_for_table, i, status_text, 0, 0, message_text,
                                         (QColor(220, 220, 255) if status_text == "额度受限" else None)) # <-- Already had 7 arguments here

                self._log_global_message(f"线程槽位 {i+1} ({status_text}): {message_text}", level="info")

        # 在循环外部请求UI更新
        self.request_ui_update_signal.emit()

        # 如果没有 Worker 启动，提示用户
        if actual_workers_started_count == 0 and self.current_run_actual_target > 0:
            self._log_global_message("未能启动任何工作线程。", level="error")
            QMessageBox.warning(self, "启动失败", "没有工作线程成功启动。请检查配置，如驱动路径、代理或免费额度。", QMessageBox.Ok) # 更详细的提示
            self._finish_filling_process(message="未能启动工作线程。")


    def _find_row_for_worker(self, worker_id_to_find):  # (保持不变)
        for row in range(self.thread_status_table.rowCount()):
            item = self.thread_status_table.item(row, 0)
            if item and item.text() == str(worker_id_to_find): return row
        return -1

    def _add_ui_update_task(self, task_type, *args):
        self._ui_update_queue.append((task_type, args))  # (保持不变)

    def _perform_ui_updates_from_queue(self):  # (保持不变)
        for task_type, args in self._ui_update_queue:
            if task_type == 'table_row':
                self._update_thread_table_row_internal(*args)
            elif task_type == 'overall_progress':
                self._update_overall_progress_display_internal()
            elif task_type == 'control_buttons':
                self._update_control_buttons_state_internal()
        self._ui_update_queue.clear();
        app_instance = QApplication.instance();
        # processEvents() should be called outside this method or with care if called inside
        # to avoid re-entering event loop issues. Assuming the signal connected handles it.
        # if app_instance: app_instance.processEvents() # Removed this line as signal connection usually handles it

    def _update_thread_table_row_internal(self, worker_id_or_placeholder, row_index, status_text, completed_count,
                                          target_count, message, color_override=None):  # (保持不变)
        if row_index < 0 or row_index >= self.thread_status_table.rowCount(): return
        try:
            # Use placeholder if worker_id is negative (for non-started threads)
            display_worker_id = str(worker_id_or_placeholder) if worker_id_or_placeholder >= 0 else f"槽位 {row_index+1}"

            self.thread_status_table.setItem(row_index, 0, QTableWidgetItem(display_worker_id));
            self.thread_status_table.setItem(row_index, 1, QTableWidgetItem(status_text));
            # Only display completed/target for active workers
            completed_text = str(completed_count) if worker_id_or_placeholder >= 0 else "-"
            target_text = str(target_count) if worker_id_or_placeholder >= 0 else "-"
            self.thread_status_table.setItem(row_index, 2, QTableWidgetItem(f"{completed_text}/{target_text}"))

            msg_to_display = str(message);
            msg_item = QTableWidgetItem(msg_to_display);
            self.thread_status_table.setItem(row_index, 3, msg_item)

            final_bg_color = color_override
            if not final_bg_color: # If no specific color override, determine color based on status text
                status_lower = status_text.lower()
                if "错误" in status_lower or "失败" in status_lower or "中止" in status_lower:
                    final_bg_color = QColor(255, 200, 200) # Light red for error/fail
                elif "成功" in status_lower or "已完成" in status_lower:
                    final_bg_color = QColor(200, 255, 200) # Light green for success/completed
                elif "验证码" in status_lower or "手动操作" in status_lower:
                    final_bg_color = QColor(255, 230, 180) # Light orange/yellow for captcha
                elif "正在停止" in status_lower or "已停止" in status_lower:
                    final_bg_color = QColor(220, 220, 220) # Light gray for stopped
                elif "暂停" in status_lower:
                    final_bg_color = QColor(200, 220, 255) # Light blue for paused
                # else: default background (usually white)

            # Apply the background color to all columns in the row
            for col in range(self.thread_status_table.columnCount()):
                item = self.thread_status_table.item(row_index, col)
                if not item: # Create item if it doesn't exist (shouldn't happen with setItem above, but for safety)
                    item = QTableWidgetItem("")
                    self.thread_status_table.setItem(row_index, col, item)
                if final_bg_color: # Only set background if a color was determined
                    item.setBackground(QBrush(final_bg_color))
                else: # Otherwise, reset to default background (important if row was previously colored)
                     item.setBackground(QBrush(QColor(Qt.white))) # Or whatever your default is

        except Exception as e:
            print(f"ERROR in _update_thread_table_row_internal: {e}");traceback.print_exc()


    def _update_overall_progress_display_internal(self):  # (保持不变)
        if self.current_run_actual_target > 0:
            self.overall_progress_bar.setMaximum(self.current_run_actual_target)
            self.overall_progress_bar.setValue(self.current_run_completed_fills)
        else:
            self.overall_progress_bar.setMaximum(1) # Avoid division by zero if target is 0
            self.overall_progress_bar.setValue(0)

        total_attempted = self.current_run_completed_fills + self.current_run_failed_fills;
        success_rate_str = f"{((self.current_run_completed_fills / total_attempted) * 100):.1f}%" if total_attempted > 0 else "N/A"
        self.stats_label.setText(
            f"本次已完成: {self.current_run_completed_fills} 份 | 成功率: {success_rate_str} (总尝试: {total_attempted}) | 失败: {self.current_run_failed_fills}")

    def _update_control_buttons_state_internal(self):  # (保持不变)
        self.start_button.setEnabled(not self.is_process_running);
        self.pause_resume_button.setEnabled(self.is_process_running); # Enable pause/resume only if running
        self.pause_resume_button.setText("继续" if self.is_globally_paused and self.is_process_running else "暂停");
        self.stop_button.setEnabled(self.is_process_running) # Enable stop only if running

    def _update_control_buttons_state(self):
        self._add_ui_update_task('control_buttons');self.request_ui_update_signal.emit()  # (保持不变)

    def _on_worker_progress(self, worker_id, completed_count, target_count, msg_type_from_signal,
                            message_from_worker):  # (修改参数顺序，与信号发射一致)
        # Check if Worker ID is in the workers dictionary (exclude placeholder IDs)
        if worker_id not in self.workers: return

        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return # Should not happen

        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return # Should not happen for a valid worker_id

        current_msg_type_str = msg_type_from_signal if isinstance(msg_type_from_signal, str) else "info";
        status_text = "运行中" # Default status while processing
        if current_msg_type_str.lower() == "error":
            status_text = "错误"
        elif current_msg_type_str.lower() == "warn":
            status_text = "警告"
        elif current_msg_type_str.lower() == "captcha":
            status_text = "验证码"
        elif current_msg_type_str.lower() == "captcha_failed":
            status_text = "AI识别失败,请手动操作"
        # If globally paused, prepend the paused status
        if self.is_globally_paused and not status_text.startswith("已暂停"):
             status_text = f"已暂停 ({status_text})"
        elif not self.is_globally_paused and status_text.startswith("已暂停"):
            # If unpaused and status shows paused, try to restore original status
            match = re.match(r"已暂停 \((.*)\)", status_text)
            status_text = match.group(1) if match else "运行中" # Restore or default to running

        self.last_message_for_worker[worker_id] = message_from_worker

        # Update table row - ensure 7 arguments are passed (None for color_override, let internal decide)
        # Completed and target counts are now passed via the signal
        self._add_ui_update_task('table_row', worker_id, row_idx, status_text,
                                 completed_count, target_count,
                                 message_from_worker, None) # <-- Pass None as the 7th argument

        self._log_global_message(message_from_worker, level=current_msg_type_str, worker_id=worker_id);
        self.request_ui_update_signal.emit() # Request UI update


    def _on_worker_single_fill_finished(self, worker_id, success, message_or_url):  # (保持不变)
        # Check if Worker ID is in the workers dictionary
        if worker_id not in self.workers: return

        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return # Should not happen

        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return # Should not happen

        status_text_base = ""; log_level = ""
        if success:
            # In MainWindow, increment global fill count
            if self.main_window_ref and hasattr(self.main_window_ref, 'increment_global_fill_count'):
                 self.main_window_ref.increment_global_fill_count()
            self.current_run_completed_fills += 1
            status_text_base = "单次成功"
            log_level = "success"
        else:
            self.current_run_failed_fills += 1
            status_text_base = "单次失败"
            log_level = "error"

        # Update the worker's last message
        self.last_message_for_worker[worker_id] = message_or_url

        # Determine the final status for the table row
        final_status_for_table = status_text_base
        # If the worker has completed all its assigned tasks, override status
        # Use the counts from the worker reference, as they are updated before this signal
        if worker_ref.fills_completed_by_this_worker >= worker_ref.num_fills_to_complete_by_worker:
             final_status_for_table = "已完成(本线程)"

        # If globally paused, prepend paused status
        if self.is_globally_paused and not final_status_for_table.startswith("已暂停"):
             final_status_for_table = f"已暂停 ({final_status_for_table})"


        # Update table row - ensure 7 arguments are passed (None for color_override, let internal decide)
        self._add_ui_update_task('table_row', worker_id, row_idx, final_status_for_table,
                                 worker_ref.fills_completed_by_this_worker, worker_ref.num_fills_to_complete_by_worker,
                                 message_or_url, None) # <-- Pass None as the 7th argument


        self._log_global_message(f"线程 {worker_id}: 单次填写{('成功' if success else '失败')}。详情: {message_or_url}", level=log_level, worker_id=worker_id)

        self._add_ui_update_task('overall_progress') # Update overall progress display

        # Check for global stop conditions (total fills or free quota)
        should_stop_due_to_limits = False;
        stop_msg = ""

        # Check if free quota is exhausted (only if not activated and MainWindow provides check methods)
        if self.main_window_ref and hasattr(self.main_window_ref, 'is_activated') and not self.main_window_ref.is_activated:
            if hasattr(self.main_window_ref, 'get_remaining_free_fills') and self.main_window_ref.get_remaining_free_fills() <= 0:
                self._log_global_message("全局免费额度已用尽，任务将中止。", level="warn", worker_id=None)
                should_stop_due_to_limits = True
                stop_msg = "免费额度用尽。任务中止。"

        # Check if the target number of fills for this run has been reached
        if not should_stop_due_to_limits and self.current_run_completed_fills >= self.current_run_actual_target:
            self._log_global_message(f"已达到本次运行目标 {self.current_run_actual_target} 份。", level="info", worker_id=None)
            should_stop_due_to_limits = True
            stop_msg = f"已完成目标({self.current_run_actual_target}份)。任务中止。"

        # If a stop condition is met and the process is still marked as running, forcefully stop all Workers
        if should_stop_due_to_limits and self.is_process_running:
             self.stop_all_workers_forcefully(
                 is_target_reached=(self.current_run_completed_fills >= self.current_run_actual_target),
                 message_override=stop_msg)

        self.request_ui_update_signal.emit() # Request UI update

    def _on_worker_completed_all(self, worker_id):  # (保持不变)
        # Check if Worker ID is in the workers dictionary
        if worker_id not in self.workers: return

        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return # Should not happen

        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return # Should not happen

        completion_message = "此线程任务结束 (达到本线程目标份数)";
        self.last_message_for_worker[worker_id] = completion_message

        # Determine the final status for the table row (ensure not showing paused if it was paused)
        final_status_for_table = "已完成(本线程)"

        # Update table row - ensure 7 arguments are passed (None for color_override, let internal decide)
        self._add_ui_update_task('table_row', worker_id, row_idx, final_status_for_table,
                                 worker_ref.fills_completed_by_this_worker, worker_ref.num_fills_to_complete_by_worker,
                                 completion_message, None) # <-- Pass None as the 7th argument

        self._log_global_message(f"线程 {worker_id}: {completion_message}", level="info", worker_id=worker_id)

        # Check if all Worker threads have finished execution
        all_threads_really_finished = True
        for worker in self.workers.values():
            # isFinished() is a QThread method to check if the run() method has completed
            if worker.isRunning(): # If isRunning() is true, it's still active
                all_threads_really_finished = False
                break

        # If all Worker threads are finished and the process is still marked as running
        # (meaning it wasn't stopped by reaching total target or manual stop),
        # it indicates that all Workers naturally completed their assigned individual tasks.
        if all_threads_really_finished and self.is_process_running:
             # Now check if the total target has been met by the sum of completed fills
             if self.current_run_completed_fills >= self.current_run_actual_target:
                  final_msg = "所有 Worker 完成任务，已达到设定的总目标份数。"
                  self._log_global_message(final_msg, level="system", worker_id=None)
                  self._finish_filling_process(message=final_msg) # Use a success message
             else:
                  # If not all fills are completed globally, it means some Worker(s) finished their allocated portion
                  # but the total target wasn't reached, possibly due to other Workers being slower, failing, or stopping earlier.
                  # This is a successful completion of the allocated tasks for THIS worker, but not necessarily the global task.
                  # We should only fully finish the process if the global target is met.
                  # However, if ALL workers report completion, and the global target wasn't met,
                  # it means the global target was unattainable given the worker assignments, or some workers failed silently.
                  # Let's rely on the check in _on_worker_single_fill_finished for global target/quota checks
                  # and this method primarily for updating the worker's individual status.
                  # If all workers are finished, _finish_filling_process will be called eventually
                  # by the global target/quota check or manual stop, or by the last worker signaling completion
                  # if no other stop condition was met.
                  pass # Do nothing more here, let the global checks handle finishing


        self.request_ui_update_signal.emit() # Request UI update


    def _toggle_pause_resume(self):  # (保持不变)
        if not self.is_process_running or not self.workers: return
        self.is_globally_paused = not self.is_globally_paused;
        action_method_name = "pause_worker" if self.is_globally_paused else "resume_worker";
        log_action_text = '暂停' if self.is_globally_paused else '恢复'
        self._log_global_message(f"用户{log_action_text}所有线程。", level="system")
        for worker_id, worker in self.workers.items():
            if worker.isRunning():
                # Call the worker's pause/resume method
                getattr(worker, action_method_name)()
                # Update table status display
                row_idx = self._find_row_for_worker(worker_id)
                if row_idx != -1:
                    # Get current status text from the table
                    current_status_item = self.thread_status_table.item(row_idx, 1)
                    status_now = current_status_item.text() if current_status_item else "未知"

                    if self.is_globally_paused and not status_now.startswith("已暂停"):
                         # If pausing and current status is not '已暂停 (...)', prepend it
                         new_status = f"已暂停 ({status_now})"
                    elif not self.is_globally_paused and status_now.startswith("已暂停"):
                         # If resuming and current status is '已暂停 (...)', remove the prefix
                         match = re.match(r"已暂停 \((.*)\)", status_now)
                         new_status = match.group(1) if match else status_now # Restore or keep original if format doesn't match
                    else:
                         # Other cases (already error/completed, or resuming from non-paused state), keep current status
                         new_status = status_now

                    current_latest_message = self.last_message_for_worker.get(worker_id, "")

                    # Update table row - ensure 7 arguments are passed (None for color_override)
                    self._add_ui_update_task('table_row', worker_id, row_idx, new_status,
                                             worker.fills_completed_by_this_worker,
                                             worker.num_fills_to_complete_by_worker, current_latest_message, None) # <-- Pass None as the 7th argument


        self._update_control_buttons_state();
        self.request_ui_update_signal.emit()

    def _manual_stop_all_workers(self):  # (保持不变)
        if not self.is_process_running and not self.workers: self._log_global_message("没有正在运行的任务可停止。",
                                                                                      level="info");return
        reply = QMessageBox.question(self, '确认停止', "确定要停止所有正在进行的填写任务吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes: self.stop_all_workers_forcefully(is_target_reached=False,
                                                                      message_override="用户手动停止所有任务。")

    def stop_all_workers_forcefully(self, is_target_reached=False, message_override=None):  # (保持不变)
        # If process is already marked as not running, or worker list is empty, just update buttons and return
        if not self.is_process_running and not self.workers:
             self._update_control_buttons_state() # Ensure button states are correct
             return

        log_msg_base = message_override if message_override else (
            "已达到目标份数，正在停止 Worker。" if is_target_reached else "用户中止，正在停止 Worker。")
        self._log_global_message(log_msg_base + " 正在通知所有 Worker 停止...",
                                 level="warn" if not is_target_reached else "system")

        # First, set the flag and notify workers to stop
        self.is_process_running = False # Set process flag to not running
        self.is_globally_paused = False # Remove paused status when stopping

        workers_to_wait = []
        # Iterate over a copy of the workers dictionary to avoid issues if the dict changes during iteration
        for worker_id, worker in list(self.workers.items()):
            # Only attempt to stop and wait for workers that are actually running or started
            # Placeholder rows in table don't have worker objects in self.workers
            if isinstance(worker, QThread) and worker.isRunning():
                worker.is_running = False # Notify the Worker thread to stop
                workers_to_wait.append(worker)
                # Update the table status for these workers to 'Stopping...'
                row_idx = self._find_row_for_worker(worker_id)
                if row_idx != -1:
                     status_text = "正在停止"
                     # Use the last known message, or a default stopping message
                     current_latest_message = self.last_message_for_worker.get(worker_id, "接收到停止信号")
                     self.last_message_for_worker[worker_id] = current_latest_message # Keep the last message
                     # Update table row - ensure 7 arguments are passed (None for color_override)
                     self._add_ui_update_task('table_row', worker_id, row_idx, status_text,
                                              getattr(worker, 'fills_completed_by_this_worker', 0), # Use getattr for safety
                                              getattr(worker, 'num_fills_to_complete_by_worker', 0), # Use getattr for safety
                                              current_latest_message, None) # <-- Pass None as the 7th argument
            # Handle placeholder rows directly if the process is stopping
            elif isinstance(worker_id, int) and worker_id < 0:
                 row_idx = self._find_row_for_worker(worker_id)
                 if row_idx != -1:
                     # These were never running workers, just table representations
                     self._add_ui_update_task('table_row', worker_id, row_idx, "已停止", 0, 0, "任务未开始或已取消", None) # <-- Pass None


        self._update_control_buttons_state() # Update button states immediately to 'Stop' becomes disabled etc.
        self.request_ui_update_signal.emit() # Request UI update


        # Wait for Worker threads to actually finish
        if workers_to_wait:
            self._log_global_message(f"等待 {len(workers_to_wait)} 个 Worker 线程结束...", level="info")
            # Waiting in a loop is generally better for UI responsiveness than a single long wait
            # but requires careful implementation to not block the event loop completely.
            # For simplicity, we'll use wait() here, assuming stop_worker() makes threads exit reasonably fast.
            # In a production GUI, you might wait in a non-blocking way or in another short-lived thread.
            for worker in workers_to_wait:
                 try:
                     # worker.wait() is a blocking call.
                     # We rely on the worker's internal is_running checks in loops and sleeps to exit gracefully.
                     # If a worker is stuck (e.g., in a long Selenium wait that doesn't time out), wait() will block.
                     # A timeout can be added to wait(timeout_ms).
                     worker.wait(5000) # Wait up to 5 seconds per worker
                     if worker.isRunning():
                          # If still running after waiting, it might be stuck
                          self._log_global_message(f"警告: Worker {worker.worker_id} 在等待后仍然运行。可能需要手动终止或检查Worker内部逻辑。", level="warn")

                 except Exception as e_wait:
                     self._log_global_message(f"等待 Worker {worker.worker_id} 结束时出错: {e_wait}", level="error")

        self._log_global_message("所有 Worker 线程已处理停止请求或已结束。", level="system")

        # Finalize the process state
        self._finish_filling_process(message=log_msg_base)


    def _finish_filling_process(self, message="填写过程结束。"):  # (保持不变)
        # Ensure flags are correct, even if called outside stop_all_workers_forcefully
        self.is_process_running = False
        self.is_globally_paused = False

        self._update_control_buttons_state(); # Update button states
        self._log_global_message(message, level="system") # Log the final message

        # Update MainWindow's status bar
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
             self.main_window_ref.statusBar().showMessage(message, 5000) # Show for 5 seconds

        # Clean up the workers list
        self.workers.clear()
        # Clear the worker's last message cache
        self.last_message_for_worker.clear()

        # Ensure all rows in the UI table reflect a final state (Completed or Stopped)
        # This loop handles any rows that might have been left in an intermediate state
        for row in range(self.thread_status_table.rowCount()):
             worker_id_item = self.thread_status_table.item(row, 0)
             status_item = self.thread_status_table.item(row, 1)

             if worker_id_item and status_item:
                 display_id_text = worker_id_item.text()
                 current_status = status_item.text()

                 # Check if the current status is not a final state
                 # Final states usually indicate completion or a definite stop/error
                 intermediate_states = ["运行中", "准备中...", "正在停止", "已暂停", "验证码", "警告"]

                 if any(state in current_status for state in intermediate_states):
                      # Determine final status based on data if available, otherwise assume stopped
                      final_status = "已停止"
                      completed_count, target_count = 0, 0 # Default values

                      # Try to get completed/target counts if it was an active worker
                      if display_id_text.isdigit():
                          worker_id = int(display_id_text)
                          # Try to get counts from the table item if they were set
                          completed_item = self.thread_status_table.item(row, 2)
                          if completed_item:
                              try:
                                  parts = completed_item.text().split('/')
                                  if len(parts) == 2:
                                      completed_count = int(parts[0])
                                      target_count = int(parts[1])
                                      # If it was an active worker and completed its share, mark as completed
                                      if completed_count > 0 and target_count > 0 and completed_count >= target_count:
                                          final_status = "已完成(本线程)"
                              except ValueError:
                                  pass # Ignore parsing errors

                      final_message = self.last_message_for_worker.get(worker_id if display_id_text.isdigit() else display_id_text, "任务已结束或取消") # Get last msg or default

                      # Update the row with the final determined status
                      self._add_ui_update_task('table_row', int(display_id_text) if display_id_text.isdigit() else display_id_text,
                                               row, final_status, completed_count, target_count, final_message, None) # <-- Pass None


        # Request UI update to render the final table states
        self.request_ui_update_signal.emit()


    def closeEvent(self, event):  # (保持不变)
        if self.is_process_running:
             # Forcefully stop all Worker threads before the main application closes
             self.stop_all_workers_forcefully(is_target_reached=False, message_override="窗口关闭，任务中止。")
             # Note: worker.wait() in stop_all_workers_forcefully might block the UI
             # but it's necessary to ensure threads exit before the process terminates,
             # which could prevent resource leaks or crashes.
             # In a more complex scenario, you might manage this differently (e.g., ask user, wait in a non-blocking way).

        super().closeEvent(event)