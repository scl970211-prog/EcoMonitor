"""
配置管理模块 - 统一的配置管理 (PyQt6 整合版)
"""

import json
import logging
import base64
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from ..core.path_resolver import get_config_path
from .crypto import encrypt_password, decrypt_password

logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_CONFIG = {
    "auto_login_enabled": True,
    "connection": {
        "auto_connect": False,
    },
    "device": {
        "ip": "",
        "port": 8000,
        "http_port": 80,
        "username": "admin",
        "password": "",
        "auto_connect": False
    },
    "scanner": {
        "auto_range": True,
        "use_arp": True,
        "use_ping": True,
        "use_tcp": True,
        "timeout": 1.0,
        "selected_cidr": ""
    },
    "preview": {
        "default_layout": 4,
        "saved_bindings": [],
        "default_channel": 1,
        "auto_play": True,
        "auto_play_all": False,
        "grid_layout": "2x2",  # 1x1, 1x2, 2x2, 1+2, 2x4, 3x3, 4x4
        "restore_on_connect": True,
        "device_layouts": {}
    },
    "download": {
        "output_dir": "",
        "concurrent": 2,
        "auto_convert": True,
        "delete_after_convert": False
    },
    "ui": {
        "window_width": 1400,
        "window_height": 900,
        "log_level": "INFO",
        "main_splitter_state": ""
    }
}


class Config:
    """配置管理器 (单例)"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._config_path = get_config_path()
        self._config = self._load()
        self._initialized = True
    
    def _load(self) -> dict:
        """加载配置"""
        if not self._config_path.exists():
            logger.info("配置文件不存在，使用默认配置")
            return self._create_default()
        
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # 合并默认配置，确保新字段存在
                merged = self._merge_defaults(DEFAULT_CONFIG, loaded)
                return merged
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self._create_default()
    
    def _save(self):
        """保存配置"""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    def _create_default(self) -> dict:
        """创建默认配置"""
        config = deepcopy(DEFAULT_CONFIG)
        # 保存默认配置
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存默认配置失败: {e}")
        return config
    
    def _merge_defaults(self, defaults: dict, loaded: dict) -> dict:
        """递归合并默认配置和已加载配置"""
        result = {}
        for key, loaded_value in loaded.items():
            if key not in defaults:
                result[key] = loaded_value
        for key, default_value in defaults.items():
            if key in loaded:
                if isinstance(default_value, dict) and isinstance(loaded[key], dict):
                    result[key] = self._merge_defaults(default_value, loaded[key])
                else:
                    result[key] = loaded[key]
            else:
                result[key] = default_value
        return result
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key_path: 键路径，如 "device.ip" 或 "scanner.timeout"
            default: 默认值
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        # 解密密码字段（优先尝试 Fernet，兼容旧版 Base64）
        if key_path == "device.password" and value:
            try:
                return decrypt_password(value)
            except Exception:
                try:
                    return base64.b64decode(value.encode()).decode('utf-8')
                except Exception:
                    return value
        
        return value
    
    def set(self, key_path: str, value: Any):
        """
        设置配置值
        
        Args:
            key_path: 键路径，如 "device.ip"
            value: 值
        """
        keys = key_path.split('.')
        config = self._config
        
        # 加密密码字段
        if key_path == "device.password" and value:
            value = encrypt_password(value)
        
        # 遍历到父级
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # 设置值
        config[keys[-1]] = value
        
        # 自动保存
        self._save()
    
    def save_device_settings(self, ip: str, port: int, username: str, password: str, http_port: Optional[int] = None):
        """保存设备连接设置"""
        self.set("device.ip", ip)
        self.set("device.port", port)
        if http_port is not None:
            self.set("device.http_port", http_port)
        self.set("device.username", username)
        self.set("device.password", password)
    
    def get_device_settings(self) -> dict:
        """获取设备连接设置"""
        return {
            "ip": self.get("device.ip", ""),
            "port": self.get("device.port", 8000),
            "http_port": self.get("device.http_port", 80),
            "username": self.get("device.username", "admin"),
            "password": self.get("device.password", "")
        }

    def set_device_layout(self, device_id: str, layout: int, bindings: list):
        """保存设备预览布局"""
        if not device_id:
            return

        preview = self._config.setdefault("preview", {})
        layouts = preview.setdefault("device_layouts", {})
        layouts[device_id] = {
            "layout": layout,
            "bindings": [list(binding) for binding in bindings],
        }
        self._save()

    def get_device_layout(self, device_id: str) -> Optional[dict]:
        """获取设备预览布局"""
        if not device_id:
            return None

        layouts = self._config.get("preview", {}).get("device_layouts", {})
        layout = layouts.get(device_id)
        return deepcopy(layout) if layout else None
    
    def reset(self):
        """重置为默认配置"""
        self._config = deepcopy(DEFAULT_CONFIG)
        self._save()
        logger.info("配置已重置为默认值")


# 便捷函数
def get_config() -> Config:
    """获取配置实例"""
    return Config()
