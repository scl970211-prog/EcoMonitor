# -*- coding: utf-8 -*-
"""
终端调试标签页 - SSH/Telnet 通用设备调试
参考 SecureCRT 功能，使用 Paramiko/telnetlib 实现
"""

import logging
import socket
import subprocess
import threading
import time
import platform

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QTextEdit,
    QMessageBox, QGroupBox, QSplitter, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject
from PyQt6.QtGui import QFont, QTextCursor

from ...utils.config import get_config
from ..theme import set_status_style, terminal_color

logger = logging.getLogger(__name__)

try:
    import paramiko
except Exception:  # pragma: no cover - 可选依赖
    paramiko = None


class _ConfirmHostKeyPolicy(paramiko.MissingHostKeyPolicy if paramiko else object):
    """连接未知 SSH 主机时提示用户确认主机密钥。"""

    def __init__(self, parent_widget: QWidget):
        super().__init__()
        self._parent = parent_widget

    def missing_host_key(self, client, hostname, key):
        if paramiko is None:
            return
        fingerprint = key.get_fingerprint().hex(":").upper()
        msg = (
            f"主机 {hostname} 的 SSH 公钥指纹尚未记录：\n\n"
            f"{fingerprint}\n\n"
            "是否信任并继续连接？"
        )
        reply = QMessageBox.question(
            self._parent,
            "确认主机密钥",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            raise paramiko.SSHException(f"用户拒绝 {hostname} 的主机密钥")
        client.get_host_keys().add(hostname, key.get_name(), key)


class _Signaler(QObject):
    append_text = pyqtSignal(str, str)
    disconnect = pyqtSignal()


class TerminalTab(QWidget):
    """终端调试标签页"""
    
    log_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._ssh_client = None
        self._telnet_client = None
        self._transport = None
        self._channel = None
        self._is_connected = False
        self._receive_thread = None
        self._stop_receive = False
        
        self._signaler = _Signaler()
        self._signaler.append_text.connect(self._do_append_terminal)
        self._signaler.disconnect.connect(self._on_disconnect)
        
        self._init_ui()
        self._load_sessions()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # 左侧：连接配置
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # 右侧：终端
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # 连接配置组
        conn_group = QGroupBox("连接配置")
        conn_layout = QVBoxLayout(conn_group)
        
        # 协议选择
        proto_layout = QHBoxLayout()
        proto_layout.addWidget(QLabel("协议:"))
        self.proto_combo = QComboBox()
        self.proto_combo.addItems(["SSH", "Telnet"])
        self.proto_combo.currentTextChanged.connect(self._on_protocol_changed)
        proto_layout.addWidget(self.proto_combo)
        conn_layout.addLayout(proto_layout)
        
        # 主机
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("主机:"))
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("192.168.1.1")
        host_layout.addWidget(self.host_input)
        conn_layout.addLayout(host_layout)
        
        # 端口
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("端口:"))
        self.port_input = QLineEdit("22")
        self.port_input.setMaximumWidth(80)
        port_layout.addWidget(self.port_input)
        port_layout.addStretch()
        conn_layout.addLayout(port_layout)
        
        # 用户名
        user_layout = QHBoxLayout()
        user_layout.addWidget(QLabel("用户:"))
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("admin")
        user_layout.addWidget(self.user_input)
        conn_layout.addLayout(user_layout)
        
        # 密码
        pwd_layout = QHBoxLayout()
        pwd_layout.addWidget(QLabel("密码:"))
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_layout.addWidget(self.pwd_input)
        conn_layout.addLayout(pwd_layout)
        
        # 保存会话
        self.save_session_cb = QCheckBox("保存会话")
        conn_layout.addWidget(self.save_session_cb)
        
        # 连接/断开按钮
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setMinimumHeight(32)
        self.connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.setMinimumHeight(32)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        btn_layout.addWidget(self.disconnect_btn)
        conn_layout.addLayout(btn_layout)
        
        layout.addWidget(conn_group)
        
        # 保存的会话组
        session_group = QGroupBox("保存的会话")
        session_layout = QVBoxLayout(session_group)
        
        self.session_combo = QComboBox()
        self.session_combo.addItem("-- 选择会话 --")
        self.session_combo.currentIndexChanged.connect(self._on_session_selected)
        session_layout.addWidget(self.session_combo)
        
        session_btn_layout = QHBoxLayout()
        self.delete_session_btn = QPushButton("删除")
        self.delete_session_btn.clicked.connect(self._on_delete_session)
        session_btn_layout.addWidget(self.delete_session_btn)
        session_btn_layout.addStretch()
        session_layout.addLayout(session_btn_layout)
        
        layout.addWidget(session_group)
        
        # 状态
        self.status_label = QLabel("未连接")
        set_status_style(self.status_label, "offline")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板（终端）"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # 终端输出
        self.terminal_output = QTextEdit()
        self.terminal_output.setObjectName("terminal")
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setFont(QFont("Consolas", 10))
        layout.addWidget(self.terminal_output)
        
        # 命令输入
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("命令:"))
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("输入命令后按回车执行...")
        self.cmd_input.returnPressed.connect(self._on_send_command)
        self.cmd_input.setEnabled(False)
        input_layout.addWidget(self.cmd_input)
        
        self.send_btn = QPushButton("发送")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self._on_send_command)
        input_layout.addWidget(self.send_btn)
        
        self.clear_btn = QPushButton("清屏")
        self.clear_btn.clicked.connect(self._on_clear_terminal)
        input_layout.addWidget(self.clear_btn)
        
        layout.addLayout(input_layout)
        return panel
    
    def _on_protocol_changed(self, protocol: str):
        """协议改变"""
        if protocol == "SSH":
            self.port_input.setText("22")
        else:
            self.port_input.setText("23")
    
    def _on_connect(self):
        """连接设备"""
        host = self.host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "警告", "请输入主机地址")
            return
        
        protocol = self.proto_combo.currentText()
        try:
            port = int(self.port_input.text().strip())
        except ValueError:
            port = 22 if protocol == "SSH" else 23
        
        username = self.user_input.text().strip()
        password = self.pwd_input.text().strip()
        
        if protocol == "SSH":
            self._connect_ssh(host, port, username, password)
        else:
            self._connect_telnet(host, port, username, password)
    
    def _connect_ssh(self, host: str, port: int, username: str, password: str):
        """连接 SSH"""
        try:
            import paramiko
        except ImportError:
            QMessageBox.critical(
                self, "依赖缺失",
                "未安装 paramiko 库，无法使用 SSH 功能。\n"
                "请运行: pip install paramiko"
            )
            return
        
        try:
            self._append_terminal(f"[INFO] 正在连接 SSH {host}:{port} ...\n", terminal_color("info"))
            
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(_ConfirmHostKeyPolicy(self))
            self._ssh_client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=10,
                banner_timeout=10
            )
            
            self._channel = self._ssh_client.invoke_shell(term='xterm', width=120, height=40)
            self._channel.settimeout(0.1)
            
            self._is_connected = True
            self._stop_receive = False
            self._receive_thread = threading.Thread(target=self._receive_ssh_data, daemon=True)
            self._receive_thread.start()
            
            self._update_ui_connected(True)
            self._append_terminal(f"[OK] SSH 连接成功: {host}:{port}\n", terminal_color("success"))
            
            if self.save_session_cb.isChecked():
                self._save_session("SSH", host, port, username)
            
        except Exception as e:
            self._append_terminal(f"[ERROR] SSH 连接失败: {e}\n", terminal_color("error"))
            QMessageBox.critical(self, "连接失败", f"SSH 连接失败:\n{e}")
            self._cleanup_connection()
    
    def _connect_telnet(self, host: str, port: int, username: str, password: str):
        """连接 Telnet"""
        try:
            import telnetlib
        except ImportError:
            QMessageBox.critical(self, "依赖缺失", "telnetlib 不可用")
            return
        
        try:
            self._append_terminal(f"[INFO] 正在连接 Telnet {host}:{port} ...\n", terminal_color("info"))
            
            self._telnet_client = telnetlib.Telnet(host, port, timeout=10)
            
            self._is_connected = True
            self._stop_receive = False
            self._receive_thread = threading.Thread(
                target=self._receive_telnet_data, daemon=True
            )
            self._receive_thread.start()
            
            self._update_ui_connected(True)
            self._append_terminal(f"[OK] Telnet 连接成功: {host}:{port}\n", terminal_color("success"))
            
            if username:
                time.sleep(0.5)
                self._telnet_client.write(username.encode('ascii') + b'\n')
            if password:
                time.sleep(0.3)
                self._telnet_client.write(password.encode('ascii') + b'\n')
            
            if self.save_session_cb.isChecked():
                self._save_session("Telnet", host, port, username)
                
        except Exception as e:
            self._append_terminal(f"[ERROR] Telnet 连接失败: {e}\n", terminal_color("error"))
            QMessageBox.critical(self, "连接失败", f"Telnet 连接失败:\n{e}")
            self._cleanup_connection()
    
    def _receive_ssh_data(self):
        """后台线程接收 SSH 数据"""
        while self._is_connected and not self._stop_receive:
            try:
                if self._channel and self._channel.recv_ready():
                    data = self._channel.recv(4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        self._append_terminal(text)
                    else:
                        break
                else:
                    time.sleep(0.05)
            except socket.timeout:
                continue
            except Exception:
                break
        
        if self._is_connected:
            self._append_terminal("\n[DISCONNECTED] 连接已断开\n", terminal_color("error"))
            self._signaler.disconnect.emit()
    
    def _receive_telnet_data(self):
        """后台线程接收 Telnet 数据"""
        while self._is_connected and not self._stop_receive:
            try:
                data = self._telnet_client.read_very_eager()
                if data:
                    text = data.decode('utf-8', errors='replace')
                    self._append_terminal(text)
                time.sleep(0.1)
            except EOFError:
                break
            except Exception:
                break
        
        if self._is_connected:
            self._append_terminal("\n[DISCONNECTED] 连接已断开\n", terminal_color("error"))
            self._signaler.disconnect.emit()
    
    def _on_send_command(self):
        """发送命令"""
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        
        if not self._is_connected:
            return
        
        try:
            if self.proto_combo.currentText() == "SSH" and self._channel:
                self._channel.send(cmd + '\n')
            elif self._telnet_client:
                self._telnet_client.write(cmd.encode('utf-8') + b'\n')
            
            self.cmd_input.clear()
        except Exception as e:
            self._append_terminal(f"\n[ERROR] 发送失败: {e}\n", terminal_color("error"))
    
    def _on_disconnect(self):
        """断开连接"""
        self._stop_receive = True
        self._is_connected = False
        
        self._cleanup_connection()
        self._update_ui_connected(False)
        self.status_label.setText("未连接")
        set_status_style(self.status_label, "offline")
        self._append_terminal("[INFO] 已断开连接\n", terminal_color("warning"))
    
    def _cleanup_connection(self):
        """清理连接资源"""
        try:
            if self._channel:
                self._channel.close()
        except Exception:
            pass
        self._channel = None
        
        try:
            if self._ssh_client:
                self._ssh_client.close()
        except Exception:
            pass
        self._ssh_client = None
        
        try:
            if self._telnet_client:
                self._telnet_client.close()
        except Exception:
            pass
        self._telnet_client = None
    
    def _update_ui_connected(self, connected: bool):
        """更新UI连接状态"""
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        self.cmd_input.setEnabled(connected)
        self.send_btn.setEnabled(connected)
        self.host_input.setEnabled(not connected)
        self.port_input.setEnabled(not connected)
        self.user_input.setEnabled(not connected)
        self.pwd_input.setEnabled(not connected)
        self.proto_combo.setEnabled(not connected)
        
        if connected:
            self.status_label.setText("已连接")
            set_status_style(self.status_label, "online", bold=True)
        else:
            self.status_label.setText("未连接")
            set_status_style(self.status_label, "offline")
    
    def _append_terminal(self, text: str, color: str = None):
        """追加文本到终端"""
        if threading.current_thread() is threading.main_thread():
            self._do_append_terminal(text, color or "")
        else:
            self._signaler.append_text.emit(text, color or "")
    
    def _do_append_terminal(self, text: str, color: str):
        """在主线程追加文本到终端（槽函数）"""
        cursor = self.terminal_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if color:
            # 使用 HTML 插入带颜色文本
            html = f'<span style="color:{color};">{text.replace(chr(10), "<br>")}</span>'
            self.terminal_output.insertHtml(html)
        else:
            # 处理特殊字符，保留 ANSI 颜色代码的基本处理
            safe_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            safe_text = safe_text.replace('\n', '<br>').replace(' ', '&nbsp;')
            self.terminal_output.insertHtml(f'<span style="color:{terminal_color("text")};">{safe_text}</span>')
        
        # 自动滚动到底部
        scrollbar = self.terminal_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _on_clear_terminal(self):
        """清屏"""
        self.terminal_output.clear()
    
    def _save_session(self, protocol: str, host: str, port: int, username: str):
        """保存会话"""
        sessions = self._config.get("terminal.sessions", [])
        # 去重
        for s in sessions:
            if s.get("host") == host and s.get("port") == port and s.get("protocol") == protocol:
                return
        
        sessions.append({
            "protocol": protocol,
            "host": host,
            "port": port,
            "username": username,
            "name": f"{protocol}://{host}:{port}"
        })
        self._config.set("terminal.sessions", sessions)
        self._load_sessions()
    
    def _load_sessions(self):
        """加载保存的会话"""
        self.session_combo.clear()
        self.session_combo.addItem("-- 选择会话 --")
        
        sessions = self._config.get("terminal.sessions", [])
        for s in sessions:
            self.session_combo.addItem(s.get("name", f"{s['protocol']}://{s['host']}:{s['port']}"))
    
    def _on_session_selected(self, index: int):
        """选择会话"""
        if index <= 0:
            return
        
        sessions = self._config.get("terminal.sessions", [])
        if index - 1 < len(sessions):
            s = sessions[index - 1]
            self.proto_combo.setCurrentText(s.get("protocol", "SSH"))
            self.host_input.setText(s.get("host", ""))
            self.port_input.setText(str(s.get("port", 22)))
            self.user_input.setText(s.get("username", ""))
    
    def _on_delete_session(self):
        """删除会话"""
        index = self.session_combo.currentIndex()
        if index <= 0:
            return
        
        sessions = self._config.get("terminal.sessions", [])
        if index - 1 < len(sessions):
            sessions.pop(index - 1)
            self._config.set("terminal.sessions", sessions)
            self._load_sessions()
    
    def closeEvent(self, event):
        """关闭事件"""
        self._on_disconnect()
        super().closeEvent(event)
