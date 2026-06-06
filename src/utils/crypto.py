# -*- coding: utf-8 -*-
"""
密码加密/解密工具
使用 Fernet 对称加密
"""

import os
import base64
from cryptography.fernet import Fernet

_KEY_FILE = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'EcoMonitor',
    '.key'
)


def _get_or_create_key() -> bytes:
    """获取或创建加密密钥"""
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, 'rb') as f:
            return f.read()
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    with open(_KEY_FILE, 'wb') as f:
        f.write(key)
    return key


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
