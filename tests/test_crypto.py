# -*- coding: utf-8 -*-
"""
密码加密模块测试
"""

import os
import tempfile

import pytest

from src.utils.crypto import CryptoManager, encrypt_password, decrypt_password, set_key_file, reset_key_file


@pytest.fixture
def temp_key_file():
    """提供临时密钥文件，并在测试后清理。"""
    fd, path = tempfile.mkstemp(suffix=".key")
    os.close(fd)
    try:
        set_key_file(path)
        yield path
    finally:
        reset_key_file()
        if os.path.exists(path):
            os.remove(path)


class TestCryptoManager:
    def test_encrypt_decrypt_roundtrip(self, temp_key_file):
        manager = CryptoManager(temp_key_file)
        original = "my_secret_password_123"
        encrypted = manager.encrypt(original)
        assert encrypted != original
        assert manager.decrypt(encrypted) == original

    def test_encrypt_empty_returns_empty(self, temp_key_file):
        manager = CryptoManager(temp_key_file)
        assert manager.encrypt("") == ""
        assert manager.decrypt("") == ""

    def test_unicode_password(self, temp_key_file):
        manager = CryptoManager(temp_key_file)
        original = "中文密码测试!@#$"
        encrypted = manager.encrypt(original)
        assert manager.decrypt(encrypted) == original


class TestModuleLevelFunctions:
    def test_module_encrypt_decrypt(self, temp_key_file):
        original = "module_level_secret"
        encrypted = encrypt_password(original)
        assert encrypted != original
        assert decrypt_password(encrypted) == original
