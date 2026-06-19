# -*- coding: utf-8 -*-
"""
宽带测速标签页 - 专业仪表盘版
基于 speedtest.net Ookla 测速节点实现
"""

import logging
import math
import os
import random
import socket
import string
import threading
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import Enum

from PyQt6.QtCore import QObject, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from .. import icons
from ..icons import Icon, set_button_icon
from ..theme import get_theme_manager, set_status_style
from ..widgets.speed_chart import SpeedChartWidget
from ..widgets.speed_gauge import SpeedGauge, SpeedPhase

# 取消实时绘图：禁用 matplotlib 集成（按需可恢复）
FigureCanvas = None
plt = None
_HAS_MPL = False
logger = logging.getLogger(__name__)

class SpeedTestState(Enum):
    """测速界面状态"""

    IDLE = "idle"
    TESTING = "testing"
    DONE = "done"
    ERROR = "error"


def _build_opener():
    """创建不跟随系统代理的 urllib opener"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch(url: str, timeout: float = 10.0) -> bytes:
    """发送 HTTP GET 请求"""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        opener = _build_opener()
        req = urllib.request.Request(url)
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        req.add_header("Accept", "*/*")
        req.add_header("Accept-Encoding", "identity")
        req.add_header("Connection", "keep-alive")
        return opener.open(req, timeout=timeout).read()
    finally:
        socket.setdefaulttimeout(old_timeout)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine 公式计算两点间距离（km）"""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class _Signaler(QObject):
    """跨线程信号"""

    log = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int)
    phase = pyqtSignal(str)       # 当前测速阶段
    latency = pyqtSignal(float)   # 最佳节点延迟
    speed_update = pyqtSignal(float)
    curve_update = pyqtSignal(float, float)  # download, upload
    label_text = pyqtSignal(object, str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)
    add_history = pyqtSignal(float, float, float, str)


class SpeedtestTab(QWidget):
    """宽带测速标签页"""

    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._is_testing = False
        self._stop_event = threading.Event()
        self._history_counter = 0
        self._state = SpeedTestState.IDLE
        self._current_phase = SpeedPhase.IDLE
        self._last_result = None
        self._init_ui()
        self._init_signaler()

    def _init_signaler(self):
        self._signaler = _Signaler()
        self._signaler.log.connect(self._on_log)
        self._signaler.status.connect(self._on_status)
        self._signaler.progress.connect(self._on_progress)
        self._signaler.phase.connect(self._on_phase)
        self._signaler.latency.connect(self._on_latency)
        self._signaler.speed_update.connect(self._on_speed_update)
        self._signaler.curve_update.connect(self._on_curve_update)
        self._signaler.label_text.connect(self._on_label_text)
        self._signaler.finished.connect(self._on_test_finished)
        self._signaler.failed.connect(self._on_test_failed)
        self._signaler.add_history.connect(self._add_history)

    # ---- UI 构建 ----

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        layout.addLayout(self._build_header())
        layout.addWidget(self._build_progress_bar())
        layout.addLayout(self._build_stage(), 4)
        layout.addLayout(self._build_metrics(), 1)
        layout.addLayout(self._build_history_and_log(), 2)

    def _build_header(self):
        layout = QHBoxLayout()
        layout.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)
        title = QLabel("网络测速")
        title.setObjectName("speedPageTitle")
        left.addWidget(title)

        self.status_label = QLabel("点击「开始测速」测试当前网络带宽")
        self.status_label.setObjectName("speedStatusLabel")
        self.status_label.setWordWrap(True)
        left.addWidget(self.status_label)

        layout.addLayout(left, 1)

        self.start_btn = QPushButton("开始测速")
        self.start_btn.setObjectName("speedStartBtn")
        self.start_btn.setMinimumHeight(44)
        self.start_btn.setMinimumWidth(140)
        set_button_icon(self.start_btn, Icon.SPEED, size=18, color=QColor("white"))
        self.start_btn.clicked.connect(self._on_start_test)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("speedStopBtn")
        self.stop_btn.setMinimumHeight(44)
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        set_button_icon(self.stop_btn, Icon.CANCEL, size=16, color=QColor("white"))
        self.stop_btn.clicked.connect(self._on_stop_test)
        layout.addWidget(self.stop_btn)

        return layout

    def _build_progress_bar(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("speedProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(6)
        return self.progress_bar

    def _build_stage(self):
        layout = QGridLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        self.gauge = SpeedGauge()
        self.gauge.setMinimumSize(300, 300)
        layout.addWidget(self.gauge, 0, 0)

        self.chart = SpeedChartWidget(max_points=80)
        self.chart.setMinimumSize(360, 280)
        layout.addWidget(self.chart, 0, 1)

        layout.setColumnStretch(0, 4)
        layout.setColumnStretch(1, 6)
        return layout

    def _build_metrics(self):
        layout = QHBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        self.download_card = self._make_metric_card(
            "▼ 下载速度", "download", "speedCardValueDownload"
        )
        self.upload_card = self._make_metric_card(
            "▲ 上传速度", "upload", "speedCardValueUpload"
        )
        self.ping_card = self._make_metric_card(
            "◉ 网络延迟", "ping", "speedCardValuePing"
        )

        layout.addWidget(self.download_card)
        layout.addWidget(self.upload_card)
        layout.addWidget(self.ping_card)
        return layout

    def _make_metric_card(self, title: str, name: str, value_object_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName("speedCard")
        card.setMinimumHeight(110)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setFrameShadow(QFrame.Shadow.Plain)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("speedCardTitle")
        vbox.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        value_label = QLabel("--")
        value_label.setObjectName(value_object_name)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(value_label, alignment=Qt.AlignmentFlag.AlignCenter)

        unit = "Mbps" if name in ("download", "upload") else "ms"
        unit_label = QLabel(unit)
        unit_label.setObjectName("speedCardUnit")
        unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(unit_label, alignment=Qt.AlignmentFlag.AlignCenter)

        vbox.addStretch()
        setattr(self, f"{name}_label", value_label)
        return card

    def _build_history_and_log(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 历史表格
        self.history_table = QTableWidget()
        self.history_table.setObjectName("speedHistoryTable")
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(
            ["次数", "时间", "下载(Mbps)", "上传(Mbps)", "延迟(ms)", "运营商/节点"]
        )
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setMaximumHeight(160)
        main_layout.addWidget(self.history_table)

        # 日志展开/收起
        toolbar = QHBoxLayout()
        toolbar.addStretch()

        self.clear_history_btn = QPushButton("清空历史")
        self.clear_history_btn.setObjectName("smallBtn")
        self.clear_history_btn.setFixedHeight(30)
        self.clear_history_btn.clicked.connect(self._on_clear_history)
        toolbar.addWidget(self.clear_history_btn)

        self.log_toggle_btn = QPushButton("展开日志")
        self.log_toggle_btn.setObjectName("smallBtn")
        self.log_toggle_btn.setFixedHeight(30)
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.toggled.connect(self._on_toggle_log)
        toolbar.addWidget(self.log_toggle_btn)

        main_layout.addLayout(toolbar)

        self.detail_text = QTextEdit()
        self.detail_text.setObjectName("speedLogPanel")
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("测速详细日志...")
        self.detail_text.setMinimumHeight(160)
        self.detail_text.setVisible(False)
        main_layout.addWidget(self.detail_text)

        return main_layout

    # ---- 状态机 ----

    def _set_state(self, state: SpeedTestState, message: str = ""):
        self._state = state
        if state == SpeedTestState.IDLE:
            self.start_btn.setText("开始测速")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.gauge.set_phase(SpeedPhase.IDLE)
            set_status_style(self.status_label, "info")
        elif state == SpeedTestState.TESTING:
            self.start_btn.setText("停止测速")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            set_status_style(self.status_label, "loading")
        elif state == SpeedTestState.DONE:
            self.start_btn.setText("重新测速")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.gauge.set_phase(SpeedPhase.DONE)
            set_status_style(self.status_label, "success")
        elif state == SpeedTestState.ERROR:
            self.start_btn.setText("重新测速")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.gauge.set_phase(SpeedPhase.ERROR)
            set_status_style(self.status_label, "error")

        if message:
            self.status_label.setText(message)

        # 刷新按钮样式使 QSS ID 变化生效
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    # ---- 信号槽 ----

    def _on_log(self, text: str):
        self.detail_text.append(text)
        scrollbar = self.detail_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_status(self, text: str):
        self.status_label.setText(text)

    def _on_progress(self, value: int):
        self.progress_bar.setValue(value)

    def _on_phase(self, phase_name: str):
        try:
            phase = SpeedPhase(phase_name)
        except ValueError:
            return
        self._current_phase = phase
        self.gauge.set_phase(phase)
        if phase in (SpeedPhase.DOWNLOAD, SpeedPhase.UPLOAD):
            self.gauge.set_value(0.0, animate=False)
            self.gauge.set_progress(0.0, animate=False)

    def _on_latency(self, latency: float):
        self.gauge.set_value(latency)
        self.gauge.set_progress(min(1.0, latency / 100.0))
        self.ping_label.setText(f"{latency:.1f}")

    def _on_speed_update(self, speed: float):
        if self._current_phase == SpeedPhase.DOWNLOAD:
            self.gauge.set_value(speed)
            self.gauge.set_progress(speed / max(1.0, self.gauge._max_value))

    def _on_curve_update(self, download: float, upload: float):
        try:
            if download > 0:
                self.chart.add_download_point(download)
            if upload > 0:
                self.chart.add_upload_point(upload)
                if self._current_phase == SpeedPhase.UPLOAD:
                    self.gauge.set_value(upload)
                    self.gauge.set_progress(upload / max(1.0, self.gauge._max_value))
        except Exception:
            pass

    def _on_label_text(self, label, text: str):
        label.setText(text)

    # ---- 测速控制 ----

    def _on_start_test(self):
        if self._state == SpeedTestState.TESTING:
            self._on_stop_test()
            return
        if self._is_testing:
            return
        self._is_testing = True
        self._stop_event.clear()
        self._reset_ui()
        self._set_state(SpeedTestState.TESTING, "准备测速...")

        thread = threading.Thread(target=self._test_worker, daemon=True)
        thread.start()

    def _on_stop_test(self):
        self._stop_event.set()
        self._is_testing = False
        self._set_state(SpeedTestState.IDLE, "已停止")

    def _reset_ui(self):
        self.progress_bar.setValue(0)
        self.download_label.setText("--")
        self.upload_label.setText("--")
        self.ping_label.setText("--")
        self.detail_text.clear()
        self.gauge.reset()
        self.chart.reset()

    def _test_worker(self):
        try:
            result = self._run_speedtest()
            if result:
                self._signaler.finished.emit(result)
            else:
                self._signaler.failed.emit("测速未完成")
        except Exception as e:
            self._signaler.log.emit(f"测速异常: {e}")
            self._signaler.log.emit(traceback.format_exc())
            self._signaler.failed.emit(str(e))

    # ---- 核心测速逻辑 ----

    def _run_speedtest(self) -> dict:
        """
        完整的 speedtest 流程：
        1. 获取客户端配置（IP、经纬度）
        2. 获取服务器列表
        3. 筛选最近的服务器并测延迟
        4. 选择最佳服务器
        5. 多线程下载测速
        6. 多线程上传测速
        """
        # 1. 获取配置
        self._signaler.status.emit("正在获取网络配置...")
        self._signaler.progress.emit(5)
        try:
            config_xml = _fetch("http://www.speedtest.net/speedtest-config.php", timeout=10)
            root = ET.fromstring(config_xml)
            client = root.find("client")
            client_lat = float(client.get("lat", 0))
            client_lon = float(client.get("lon", 0))
            client_isp = client.get("isp", "未知")
            client_ip = client.get("ip", "")
            self._signaler.log.emit(f"本机IP: {client_ip}, 运营商: {client_isp}")
        except Exception as e:
            self._signaler.log.emit(f"获取配置失败: {e}")
            client_lat, client_lon = 0, 0
            client_isp = "未知"

        # 2. 获取服务器列表
        self._signaler.status.emit("正在获取测速节点...")
        self._signaler.progress.emit(10)
        try:
            servers_xml = _fetch("http://www.speedtest.net/speedtest-servers-static.php", timeout=15)
            servers_root = ET.fromstring(servers_xml)
            servers = []
            for s in servers_root.findall("servers/server"):
                url = s.get("url", "")
                if not url or "upload.php" not in url:
                    continue
                lat = float(s.get("lat", 0))
                lon = float(s.get("lon", 0))
                dist = _haversine(client_lat, client_lon, lat, lon) if client_lat else 99999
                servers.append({
                    "url": url,
                    "name": s.get("name", ""),
                    "sponsor": s.get("sponsor", ""),
                    "country": s.get("country", ""),
                    "dist": dist,
                })
            self._signaler.log.emit(f"发现 {len(servers)} 个测速节点")
        except Exception as e:
            self._signaler.log.emit(f"获取节点失败: {e}")
            return None

        if not servers:
            self._signaler.log.emit("没有可用测速节点")
            return None

        # 按距离排序，取前10个测延迟
        servers.sort(key=lambda x: x["dist"])
        candidates = servers[:10]

        # 3. 测延迟
        self._signaler.status.emit("正在探测最佳节点...")
        self._signaler.phase.emit(SpeedPhase.LATENCY.value)
        self._signaler.progress.emit(15)
        best_server = None
        best_latency = float("inf")
        for s in candidates:
            if self._stop_event.is_set():
                return None
            latency = self._test_latency(s["url"])
            if latency > 0 and latency < best_latency:
                best_latency = latency
                best_server = s
            self._signaler.log.emit(
                f"  {s['sponsor']} - {s['name']}: {latency:.1f}ms"
            )

        if not best_server:
            self._signaler.log.emit("所有节点延迟测试失败")
            return None

        self._signaler.log.emit(
            f"最佳节点: {best_server['sponsor']} - {best_server['name']} "
            f"(延迟: {best_latency:.1f}ms, 距离: {best_server['dist']:.0f}km)"
        )
        self._signaler.latency.emit(best_latency)
        self._signaler.progress.emit(20)

        # 4. 下载测速（多线程）
        self._signaler.status.emit("正在测试下载速度...")
        self._signaler.phase.emit(SpeedPhase.DOWNLOAD.value)
        dl_url = best_server["url"].replace("upload.php", "download")
        dl_speed = self._test_download(dl_url)
        if self._stop_event.is_set():
            return None

        self._signaler.progress.emit(60)
        self._signaler.log.emit(f"下载速度: {dl_speed:.2f} Mbps")

        # 5. 上传测速（多线程）
        self._signaler.status.emit("正在测试上传速度...")
        self._signaler.phase.emit(SpeedPhase.UPLOAD.value)
        ul_speed = self._test_upload(best_server["url"])
        if self._stop_event.is_set():
            return None

        self._signaler.progress.emit(90)
        self._signaler.log.emit(f"上传速度: {ul_speed:.2f} Mbps")

        # 结果
        result = {
            "download": round(dl_speed, 2),
            "upload": round(ul_speed, 2),
            "ping": round(best_latency, 1),
            "isp": f"{client_isp} / {best_server['sponsor']}",
        }

        # 更新UI
        self._signaler.label_text.emit(self.download_label, str(result["download"]))
        self._signaler.label_text.emit(self.upload_label, str(result["upload"]))
        self._signaler.label_text.emit(self.ping_label, str(result["ping"]))

        self._signaler.add_history.emit(
            result["download"], result["upload"], result["ping"], result["isp"]
        )

        return result

    def _test_latency(self, upload_url: str) -> float:
        """测试节点延迟（ms），单次测试"""
        base_url = upload_url.replace("upload.php", "latency.txt")
        try:
            start = time.time()
            _fetch(base_url + f"?x={random.random()}", timeout=3)
            return (time.time() - start) * 1000
        except Exception:
            return -1

    def _test_download(self, base_url: str) -> float:
        """
        多线程下载测速
        使用 4 个线程并行下载，持续 8 秒，实时计算速度
        """
        sizes = [250000, 500000, 1000000, 2500000, 5000000, 10000000, 25000000, 50000000]
        total_bytes = 0
        start_time = time.time()
        stop_time = start_time + 8  # 测速 8 秒
        lock = threading.Lock()

        def worker():
            nonlocal total_bytes
            while time.time() < stop_time and not self._stop_event.is_set():
                size = random.choice(sizes)
                url = f"{base_url}?size={size}&x={random.random()}"
                try:
                    data = _fetch(url, timeout=12)
                    with lock:
                        total_bytes += len(data)
                except Exception:
                    pass

        # 启动 4 个下载线程
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(4)]
        for t in threads:
            t.start()

        # 实时更新速度
        while time.time() < stop_time and not self._stop_event.is_set():
            elapsed = time.time() - start_time
            if elapsed > 0:
                with lock:
                    current_speed = (total_bytes * 8) / elapsed / 1_000_000
                self._signaler.speed_update.emit(current_speed)
                self._signaler.curve_update.emit(current_speed, 0.0)
                self._signaler.progress.emit(20 + int(min(elapsed / 8, 1) * 35))
            time.sleep(0.3)

        for t in threads:
            t.join(timeout=2)

        elapsed = time.time() - start_time
        if elapsed > 0:
            return (total_bytes * 8) / elapsed / 1_000_000
        return 0

    def _test_upload(self, upload_url: str) -> float:
        """
        多线程上传测速
        使用 4 个线程并行 POST 数据，持续 6 秒
        """
        total_bytes = 0
        start_time = time.time()
        stop_time = start_time + 6
        lock = threading.Lock()

        # 预生成随机数据块
        data_250k = "".join(random.choices(string.ascii_letters + string.digits, k=250000)).encode()
        data_500k = "".join(random.choices(string.ascii_letters + string.digits, k=500000)).encode()
        data_1m = "".join(random.choices(string.ascii_letters + string.digits, k=1000000)).encode()
        upload_chunks = [data_250k, data_500k, data_1m]

        def worker():
            nonlocal total_bytes
            while time.time() < stop_time and not self._stop_event.is_set():
                chunk = random.choice(upload_chunks)
                try:
                    opener = _build_opener()
                    req = urllib.request.Request(upload_url, data=chunk)
                    req.add_header(
                        "User-Agent",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    )
                    req.add_header("Content-Type", "application/x-www-form-urlencoded")
                    req.add_header("Accept-Encoding", "identity")
                    req.add_header("Connection", "keep-alive")
                    opener.open(req, timeout=12)
                    with lock:
                        total_bytes += len(chunk)
                except Exception:
                    pass

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(4)]
        for t in threads:
            t.start()

        while time.time() < stop_time and not self._stop_event.is_set():
            elapsed = time.time() - start_time
            if elapsed > 0:
                with lock:
                    current_speed = (total_bytes * 8) / elapsed / 1_000_000
                self._signaler.curve_update.emit(0.0, current_speed)
                self._signaler.progress.emit(55 + int(min(elapsed / 6, 1) * 30))
            time.sleep(0.3)

        for t in threads:
            t.join(timeout=2)

        elapsed = time.time() - start_time
        if elapsed > 0:
            return (total_bytes * 8) / elapsed / 1_000_000
        return 0

    # ---- 历史记录 ----

    def _add_history(self, download: float, upload: float, ping: float, isp: str):
        # 序号自增
        self._history_counter += 1
        self.history_table.insertRow(0)
        self.history_table.setItem(0, 0, QTableWidgetItem(str(self._history_counter)))
        self.history_table.setItem(0, 1, QTableWidgetItem(datetime.now().strftime("%m-%d %H:%M")))
        self.history_table.setItem(0, 2, QTableWidgetItem(str(download)))
        self.history_table.setItem(0, 3, QTableWidgetItem(str(upload)))
        self.history_table.setItem(0, 4, QTableWidgetItem(str(ping)))
        self.history_table.setItem(0, 5, QTableWidgetItem(str(isp)))
        if self.history_table.rowCount() > 200:
            self.history_table.removeRow(self.history_table.rowCount() - 1)

    def _on_test_finished(self, result: dict):
        self._is_testing = False
        self._last_result = result
        self._set_state(
            SpeedTestState.DONE,
            f"测速完成 · 下载 {result.get('download', '--')} Mbps / 上传 {result.get('upload', '--')} Mbps",
        )
        self.gauge.set_value(result.get("download", 0.0))
        self.gauge.set_progress(1.0)
        self.download_label.setText(str(result.get("download", "--")))
        self.upload_label.setText(str(result.get("upload", "--")))
        self.ping_label.setText(str(result.get("ping", "--")))
        self.progress_bar.setValue(100)

    def _on_test_failed(self, error_msg: str):
        self._is_testing = False
        self._set_state(SpeedTestState.ERROR, f"测速失败: {error_msg}")
        self.progress_bar.setValue(0)

    def _on_clear_history(self):
        self.history_table.setRowCount(0)

    def _on_toggle_log(self, checked: bool):
        self.detail_text.setVisible(checked)
        self.log_toggle_btn.setText("收起日志" if checked else "展开日志")
