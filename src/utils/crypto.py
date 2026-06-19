# -*- coding: utf-8 -*-
"""
密码加密/解密工具
使用 Fernet 对称加密
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet

try:
    from ..core.path_resolver import get_data_dir
except ImportError:
    from src.core.path_resolver import get_data_dir

_DEFAULT_KEY_FILE = str(get_data_dir() / ".key")

_key_file: str = _DEFAULT_KEY_FILE


def set_key_file(path: str) -> None:
    """设置密钥文件路径，主要用于测试或自定义数据目录。"""
    global _key_file
    _key_file = path


def reset_key_file() -> None:
    """重置为默认密钥文件路径。"""
    global _key_file
    _key_file = _DEFAULT_KEY_FILE


def _get_or_create_key() -> bytes:
    """获取或创建加密密钥"""
    if os.path.exists(_key_file) and os.path.getsize(_key_file) > 0:
        with open(_key_file, 'rb') as f:
            return f.read()
    key = Fernet.generate_key()
    key_dir = Path(_key_file).parent
    key_dir.mkdir(parents=True, exist_ok=True)
    with open(_key_file, 'wb') as f:
        f.write(key)
    _restrict_key_acl(_key_file)
    return key


def _restrict_key_acl(path: str):
    """限制密钥文件仅当前用户可读写（最佳 effort）。"""
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def encrypt_password(password: str) -> str:
    """加密密码"""
    if not password:
        return ""
    f = Fernet(_get_or_create_key())
    return f.encrypt(password.encode('utf-8')).decode('ascii')


def decrypt_password(token: str) -> str:
    """解密密码"""
    if not token:
        return ""
    f = Fernet(_get_or_create_key())
    return f.decrypt(token.encode('ascii')).decode('utf-8')


class CryptoManager:
    """可实例化的加密管理器，便于测试与多环境使用。"""

    def __init__(self, key_file: str = None):
        self._key_file = key_file or _DEFAULT_KEY_FILE

    def _get_or_create_key(self) -> bytes:
        if os.path.exists(self._key_file) and os.path.getsize(self._key_file) > 0:
            with open(self._key_file, 'rb') as f:
                return f.read()
        key = Fernet.generate_key()
        key_dir = Path(self._key_file).parent
        key_dir.mkdir(parents=True, exist_ok=True)
        with open(self._key_file, 'wb') as f:
            f.write(key)
        _restrict_key_acl(self._key_file)
        return key

    def encrypt(self, text: str) -> str:
        if not text:
            return ""
        f = Fernet(self._get_or_create_key())
        return f.encrypt(text.encode('utf-8')).decode('ascii')

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        f = Fernet(self._get_or_create_key())
        return f.decrypt(token.encode('ascii')).decode('utf-8')
