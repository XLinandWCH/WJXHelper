# widgets_filling_process.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QProgressBar, QTextEdit, QGroupBox, QSpinBox, QFormLayout,
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QSizePolicy, QSplitter)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer  # QTimer在这里似乎未使用
from PyQt5.QtGui import QColor
import time
import random
import traceback  # 导入 traceback

from filler_worker import FillerWorker  # 确保 FillerWorker 已更新


class FillingProcessWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window_ref = parent  # 指向主窗口
        self._init_ui()

        self.workers = {}  # 存储活动的工作线程
        self.worker_id_counter = 0  # 用于生成唯一的worker ID
        self.total_fills_target = 0  # 本次任务的总目标填写份数
        self.total_fills_completed = 0  # 已成功完成的份数
        self.total_fills_failed = 0  # 已失败的份数

        self.current_questionnaire_url = None  # 当前问卷URL
        self.parsed_questionnaire_data_cache = None  # 解析后的问卷结构缓存
        self.user_raw_configs_template_cache = None  # 用户配置模板缓存
        self.basic_settings_cache = None  # 基本设置缓存 (线程数、代理等)

        self.is_globally_paused = False  # 全局暂停标志
        self.is_process_running = False  # 填写过程是否正在运行

    def _init_ui(self):
        # (UI代码与你提供的一致，为简洁省略，确保它包含 self.log_splitter 的正确设置)
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

    # *** 关键修改：确保参数名 user_raw_configurations_template 与 MainWindow 中调用时一致 ***
    def prepare_for_filling(self, url, parsed_questionnaire_data, user_raw_configurations_template, basic_settings):
        print("FillingProcessWidget: prepare_for_filling called.")  # 调试信息
        self.current_questionnaire_url = url
        self.parsed_questionnaire_data_cache = parsed_questionnaire_data
        self.user_raw_configs_template_cache = user_raw_configurations_template  # 存储模板
        self.basic_settings_cache = basic_settings

        # --- 调试打印 ---
        print(f"  URL received: {self.current_questionnaire_url[:60]}...")
        print(f"  Parsed Data Cache Type: {type(self.parsed_questionnaire_data_cache)}")
        print(f"  User Raw Configs Template Cache Type: {type(self.user_raw_configs_template_cache)}")
        if isinstance(self.user_raw_configs_template_cache, list) and self.user_raw_configs_template_cache:
            print(f"    Template Cache Length: {len(self.user_raw_configs_template_cache)}")
            print(f"    First item of template cache (example): {self.user_raw_configs_template_cache[0]}")
        elif self.user_raw_configs_template_cache is None:
            print("    User Raw Configs Template Cache is None!")
        print(f"  Basic Settings Cache: {self.basic_settings_cache}")
        # --- 结束调试打印 ---

        # 重置统计数据和UI元素
        self.total_fills_target = basic_settings.get("num_fills_total", 1)  # 从缓存获取目标数
        self.total_fills_completed = 0
        self.total_fills_failed = 0
        self.overall_progress_bar.setMaximum(self.total_fills_target if self.total_fills_target > 0 else 1)
        self.overall_progress_bar.setValue(0)
        self.stats_label.setText(f"已完成: 0 份 | 成功率: N/A | 预计剩余时间: N/A")
        self.thread_status_table.setRowCount(0)  # 清空表格
        self.global_log_output.clear()  # 清空日志

        # 重置控制按钮状态
        self.start_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.is_process_running = False
        self.is_globally_paused = False
        self.pause_resume_button.setText("暂停")

        self._log_global_message(
            f"配置已加载。问卷URL: {url[:50]}...，目标份数: {self.total_fills_target}，线程数: {basic_settings.get('num_threads', 1)}")

    def _log_global_message(self, message, level="info"):
        # (代码不变)
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
        print("FillingProcessWidget: _start_filling_process called.")  # 调试信息
        # 再次检查所有必需的缓存数据是否存在
        if not self.current_questionnaire_url or \
                not self.parsed_questionnaire_data_cache or \
                not self.user_raw_configs_template_cache or \
                not self.basic_settings_cache:
            QMessageBox.warning(self, "无法开始", "问卷配置信息不完整，请返回“问卷配置”页面并重新加载问卷和检查设置。")
            self._log_global_message("启动失败：必要配置信息缺失。", "error")
            return

        if self.is_process_running:  # 如果已经在运行，则不重复启动
            QMessageBox.information(self, "提示", "填写过程已经在运行中。")
            return

        # 从缓存中获取配置
        num_threads = self.basic_settings_cache.get("num_threads", 1)
        self.total_fills_target = self.basic_settings_cache.get("num_fills_total", 1)

        if self.total_fills_target <= 0:  # 目标份数必须大于0
            QMessageBox.warning(self, "提示", "目标填写份数必须大于0。")
            return

        if self.total_fills_completed >= self.total_fills_target:  # 如果已完成目标
            QMessageBox.information(self, "提示", "已达到目标填写份数。如需重新开始，请调整目标份数或重置进度。")
            return

        print(f"  Attempting to start with {num_threads} threads, target {self.total_fills_target} fills.")  # 调试信息

        # 更新UI状态
        self.is_process_running = True
        self.start_button.setEnabled(False)
        self.pause_resume_button.setEnabled(True)
        self.pause_resume_button.setText("暂停")
        self.is_globally_paused = False  # 重置暂停状态
        self.stop_button.setEnabled(True)

        self.overall_progress_bar.setMaximum(self.total_fills_target)
        self._update_overall_progress_display()  # 更新进度条显示

        # 计算实际需要启动的线程数和每个线程的任务量
        remaining_target_fills = self.total_fills_target - self.total_fills_completed
        actual_num_threads_to_start = min(num_threads, remaining_target_fills)

        if actual_num_threads_to_start <= 0:  # 如果没有需要启动的线程
            self._log_global_message("没有需要启动的线程 (可能已完成或目标份数为0)。", "warn")
            self._finish_filling_process(message="没有任务需要执行。")  # 结束流程
            return

        fills_per_thread = remaining_target_fills // actual_num_threads_to_start
        extra_fills = remaining_target_fills % actual_num_threads_to_start  # 分配剩余任务

        self.thread_status_table.setRowCount(actual_num_threads_to_start)  # 设置表格行数

        self.workers.clear()  # 清空旧的 worker 引用，避免重复

        for i in range(actual_num_threads_to_start):
            self.worker_id_counter += 1  # 生成新 worker ID
            worker_id = self.worker_id_counter
            num_fills_for_this_thread = fills_per_thread + (1 if i < extra_fills else 0)

            if num_fills_for_this_thread == 0: continue  # 如果此线程无任务，跳过

            # --- 调试打印 Worker 参数 ---
            print(f"  Creating Worker {worker_id}:")
            print(f"    URL: {self.current_questionnaire_url[:60]}...")
            print(f"    Num Fills for this worker: {num_fills_for_this_thread}")
            print(f"    Headless: {self.basic_settings_cache.get('headless', True)}")
            print(f"    Proxy: {self.basic_settings_cache.get('proxy')}")
            print(f"    Driver Path: {self.basic_settings_cache.get('msedgedriver_path')}")
            print(f"    User Raw Configs Template Cache Type for Worker: {type(self.user_raw_configs_template_cache)}")
            if isinstance(self.user_raw_configs_template_cache, list) and self.user_raw_configs_template_cache:
                print(f"      First item of template cache being passed: {self.user_raw_configs_template_cache[0]}")
            # --- 结束调试打印 ---

            # *** 关键：确保传递正确的 user_raw_configs_template_cache 给 Worker ***
            worker = FillerWorker(
                worker_id=worker_id,
                url=self.current_questionnaire_url,
                user_raw_configurations_template=self.user_raw_configs_template_cache,  # 使用缓存的模板
                num_fills_for_this_worker=num_fills_for_this_thread,
                total_target_fills=self.total_fills_target,  # 传递总目标（Worker内部未使用此参数）
                headless=self.basic_settings_cache.get("headless", True),
                proxy=self.basic_settings_cache.get("proxy"),
                msedgedriver_path=self.basic_settings_cache.get("msedgedriver_path")
            )
            # 连接Worker的信号到槽函数
            worker.progress_signal.connect(self._on_worker_progress)
            worker.single_fill_finished_signal.connect(self._on_worker_single_fill_finished)
            worker.worker_completed_all_fills_signal.connect(self._on_worker_completed_all)

            self.workers[worker_id] = worker  # 存储Worker实例
            # 更新线程状态表中的行
            self._update_thread_table_row(worker_id, i, "准备中...", 0, num_fills_for_this_thread, "")
            worker.start()  # 启动线程
            self._log_global_message(f"启动线程 {worker_id}，目标填写 {num_fills_for_this_thread} 份。")

        if not self.workers:  # 如果未能启动任何线程
            self._log_global_message("未能启动任何工作线程。", "error")
            self._finish_filling_process(message="未能启动工作线程。")

    def _find_row_for_worker(self, worker_id):
        # (代码不变)
        for row in range(self.thread_status_table.rowCount()):
            item = self.thread_status_table.item(row, 0)
            if item and int(item.text()) == worker_id: return row
        return -1

    def _update_thread_table_row(self, worker_id, row_index, status_text, completed_count, target_count, message,
                                 progress_val=None):
        # (代码不变)
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
        # 简单的根据消息类型设置背景色
        if msg_type_from_message := message.split("] ")[-1].split(":")[0].strip(
                '[] ').lower() if "] " in message else "":
            if "error" == msg_type_from_message or "失败" in status_text:
                bg_color = QColor(255, 220, 220)
            elif "success" == msg_type_from_message or "成功" in status_text:
                bg_color = QColor(220, 255, 220)
        for col in range(self.thread_status_table.columnCount()):
            table_item = self.thread_status_table.item(row_index, col)
            if table_item: table_item.setBackground(bg_color)

    def _on_worker_progress(self, worker_id, current_done_by_worker, target_for_worker, msg_type, message):
        # (代码不变)
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
                                      message)
        self._log_global_message(f"线程 {worker_id}: {message}", msg_type)

    def _on_worker_single_fill_finished(self, worker_id, success, message_or_url):
        # (代码不变)
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return
        completed_by_worker = worker_ref.fills_completed_by_this_worker  # 这个值在worker内部已更新
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
        if self.total_fills_completed >= self.total_fills_target and self.is_process_running:
            self._log_global_message(f"已达到总目标 {self.total_fills_target} 份，正在停止所有线程...", "info")
            self.stop_all_workers_forcefully(is_target_reached=True)

    def _on_worker_completed_all(self, worker_id):
        # (代码不变)
        row_idx = self._find_row_for_worker(worker_id)
        if row_idx == -1: return
        worker_ref = self.workers.get(worker_id)
        if not worker_ref: return
        completed_by_worker = worker_ref.fills_completed_by_this_worker
        target_for_worker = worker_ref.num_fills_to_complete_by_worker
        self._update_thread_table_row(worker_id, row_idx, "已完成(本线程)", completed_by_worker, target_for_worker,
                                      "此线程任务结束")
        self._log_global_message(f"线程 {worker_id} 已完成其全部分配任务。", "info")
        # 检查是否所有线程都完成了
        all_threads_finished_or_stopped = True
        for w_id, w_instance in self.workers.items():
            if w_instance.isRunning():  # 只要有一个还在运行，就不是全部完成
                all_threads_finished_or_stopped = False
                break
        if all_threads_finished_or_stopped and self.is_process_running:  # 确保是在运行状态下检查
            self._log_global_message("所有线程均已完成其任务或已停止。", "info")
            self._finish_filling_process(message="所有任务完成。")

    def _update_overall_progress_display(self):
        # (代码不变)
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
        # (代码不变)
        if not self.is_process_running or not self.workers: return
        self.is_globally_paused = not self.is_globally_paused
        action_method_name = "pause_worker" if self.is_globally_paused else "resume_worker"
        button_text = "继续" if self.is_globally_paused else "暂停"
        log_message = "所有线程已暂停。" if self.is_globally_paused else "所有线程已恢复。"
        self.pause_resume_button.setText(button_text)
        self._log_global_message(log_message, "info")
        for worker in self.workers.values():
            if worker.isRunning(): getattr(worker, action_method_name)()

    def _stop_all_workers(self):
        # (代码不变)
        if not self.is_process_running and not self.workers:
            self._log_global_message("没有正在运行的任务可停止。", "info")
            return
        reply = QMessageBox.question(self, '确认停止', "确定要停止所有正在进行的填写任务吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.stop_all_workers_forcefully()

    def stop_all_workers_forcefully(self, is_target_reached=False):
        # (代码不变)
        if not self.workers and not self.is_process_running: return
        self._log_global_message("正在停止所有工作线程...", "warn")
        for worker_id, worker in list(self.workers.items()):  # 使用list转换，因为可能在迭代中修改字典
            if worker.isRunning():
                worker.stop_worker()  # 请求线程停止
            # 更新表格显示状态为已停止
            row_idx = self._find_row_for_worker(worker_id)
            if row_idx != -1:
                self._update_thread_table_row(worker_id, row_idx, "已停止",
                                              worker.fills_completed_by_this_worker,
                                              worker.num_fills_to_complete_by_worker,
                                              "用户或系统中止")
        # self.workers.clear() # 清空worker字典，旧的线程对象会在其run方法结束后自然销毁
        # 流程结束的判断和UI更新
        if not is_target_reached:
            self._finish_filling_process(message="用户手动停止了所有任务。")
        else:
            self._finish_filling_process(message="已达到目标份数，所有任务结束。")

    def _finish_filling_process(self, message="填写过程结束。"):
        # (代码不变)
        self.is_process_running = False
        self.is_globally_paused = False  # 确保暂停状态也重置
        self.start_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.setText("暂停")
        self.stop_button.setEnabled(False)
        self._log_global_message(message, "info")
        if self.main_window_ref and hasattr(self.main_window_ref, 'statusBar'):
            self.main_window_ref.statusBar().showMessage(message, 5000)  # 显示5秒

    def closeEvent(self, event):  # 这个方法通常在 QWidget 关闭时不会被直接调用，QMainWindow的closeEvent更常用
        # (代码不变)
        if self.is_process_running:  # 如果仍在运行，则强制停止
            self.stop_all_workers_forcefully()
        super().closeEvent(event)

