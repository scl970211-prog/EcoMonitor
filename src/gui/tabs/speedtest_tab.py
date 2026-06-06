# -*- coding: utf-8 -*-
"""
宽带测速标签页 - 参考 speedtest.cn / speedtest.net 专业测速
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

from PyQt6.QtCore import QObject, Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)

# 禁用系统代理，避免错误的代理配置导致连接失败
for _proxy_key in (
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
):
    os.environ.pop(_proxy_key, None)


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
    speed_update = pyqtSignal(float)  # 实时下载速度 Mbps
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
        self._init_ui()
        self._init_signaler()

    def _init_signaler(self):
        self._signaler = _Signaler()
        self._signaler.log.connect(self._on_log)
        self._signaler.status.connect(self._on_status)
        self._signaler.progress.connect(self._on_progress)
        self._signaler.speed_update.connect(self._on_speed_update)
        self._signaler.label_text.connect(self._on_label_text)
        self._signaler.finished.connect(self._on_test_finished)
        self._signaler.failed.connect(self._on_test_failed)
        self._signaler.add_history.connect(self._add_history)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 按钮行
        top = QHBoxLayout()
        self.test_btn = QPushButton("🚀 开始测速")
        self.test_btn.setMinimumHeight(40)
        self.test_btn.setMinimumWidth(140)
        self.test_btn.clicked.connect(self._on_start_test)
        top.addWidget(self.test_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_test)
        top.addWidget(self.stop_btn)
        top.addStretch()

        self.status_label = QLabel("点击「开始测速」测试您的网络带宽")
        self.status_label.setStyleSheet("font-size: 12px; color: #666;")
        top.addWidget(self.status_label)
        layout.addLayout(top)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # 结果区域
        result_group = QGroupBox("测速结果")
        result_layout = QHBoxLayout(result_group)

        def _make_result_box(title, label_name, color):
            box = QVBoxLayout()
            box.addWidget(QLabel(title), alignment=Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel("--")
            lbl.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {color};")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(lbl)
            box.addWidget(QLabel("Mbps" if "速度" in title else "ms" if "延迟" in title else ""),
                          alignment=Qt.AlignmentFlag.AlignCenter)
            setattr(self, label_name, lbl)
            result_layout.addLayout(box)

        _make_result_box("下载速度", "download_label", "#2196F3")
        _make_result_box("上传速度", "upload_label", "#4CAF50")
        _make_result_box("网络延迟", "ping_label", "#FF9800")

        isp_layout = QVBoxLayout()
        isp_layout.addWidget(QLabel("运营商/节点"), alignment=Qt.AlignmentFlag.AlignCenter)
        self.isp_label = QLabel("--")
        self.isp_label.setStyleSheet("font-size: 14px; color: #666;")
        self.isp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        isp_layout.addWidget(self.isp_label)
        isp_layout.addWidget(QLabel(""), alignment=Qt.AlignmentFlag.AlignCenter)
        result_layout.addLayout(isp_layout)

        layout.addWidget(result_group)

        # 历史记录
        history_group = QGroupBox("测速历史")
        history_layout = QVBoxLayout(history_group)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            ["时间", "下载(Mbps)", "上传(Mbps)", "延迟(ms)", "运营商/节点"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self.history_table)
        clear_btn = QPushButton("清空历史")
        clear_btn.clicked.connect(self._on_clear_history)
        history_layout.addWidget(clear_btn)
        layout.addWidget(history_group)

        # 日志
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(180)
        self.detail_text.setPlaceholderText("测速详细日志...")
        layout.addWidget(self.detail_text)

        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 0)
        layout.setStretch(3, 1)
        layout.setStretch(4, 1)

    # ---- 信号槽 ----

    def _on_log(self, text: str):
        self.detail_text.append(text)
        self.detail_text.verticalScrollBar().setValue(
            self.detail_text.verticalScrollBar().maximum()
        )

    def _on_status(self, text: str):
        self.status_label.setText(text)

    def _on_progress(self, value: int):
        self.progress_bar.setValue(value)

    def _on_speed_update(self, speed: float):
        """实时速度更新"""
        self.download_label.setText(f"{speed:.1f}")

    def _on_label_text(self, label, text: str):
        label.setText(text)

    # ---- 测速控制 ----

    def _on_start_test(self):
        if self._is_testing:
            return
        self._is_testing = True
        self._stop_event.clear()
        self.test_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("准备测速...")
        self.status_label.setStyleSheet("color: #2196F3;")

        self.download_label.setText("--")
        self.upload_label.setText("--")
        self.ping_label.setText("--")
        self.isp_label.setText("--")
        self.detail_text.clear()

        thread = threading.Thread(target=self._test_worker, daemon=True)
        thread.start()

    def _on_stop_test(self):
        self._stop_event.set()
        self._is_testing = False
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet("color: #999;")

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
        self._signaler.progress.emit(20)

        # 4. 下载测速（多线程）
        self._signaler.status.emit("正在测试下载速度...")
        dl_url = best_server["url"].replace("upload.php", "download")
        dl_speed = self._test_download(dl_url)
        if self._stop_event.is_set():
            return None

        self._signaler.progress.emit(60)
        self._signaler.log.emit(f"下载速度: {dl_speed:.2f} Mbps")

        # 5. 上传测速（多线程）
        self._signaler.status.emit("正在测试上传速度...")
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
        self._signaler.label_text.emit(self.isp_label, result["isp"])

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
        row = self.history_table.rowCount()
        self.history_table.insertRow(0)
        self.history_table.setItem(0, 0, QTableWidgetItem(datetime.now().strftime("%m-%d %H:%M")))
        self.history_table.setItem(0, 1, QTableWidgetItem(str(download)))
        self.history_table.setItem(0, 2, QTableWidgetItem(str(upload)))
        self.history_table.setItem(0, 3, QTableWidgetItem(str(ping)))
        self.history_table.setItem(0, 4, QTableWidgetItem(str(isp)))
        if self.history_table.rowCount() > 50:
            self.history_table.removeRow(self.history_table.rowCount() - 1)

    def _on_test_finished(self, result: dict):
        self._is_testing = False
        self.test_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText("测速完成")
        self.status_label.setStyleSheet("color: #4CAF50;")
        self.download_label.setText(str(result.get("download", "--")))
        self.upload_label.setText(str(result.get("upload", "--")))
        self.ping_label.setText(str(result.get("ping", "--")))

    def _on_test_failed(self, error_msg: str):
        self._is_testing = False
        self.test_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"测速失败: {error_msg}")
        self.status_label.setStyleSheet("color: #f44336;")

    def _on_clear_history(self):
        self.history_table.setRowCount(0)
