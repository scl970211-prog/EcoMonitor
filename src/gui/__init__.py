"""
GUI 模块

主窗口等大型组件采用延迟导入，避免在仅需要常量或控件时加载全部 Qt 界面。
"""

_LAZY_IMPORTS = {
    "MainWindow": (".main_window", "MainWindow"),
}


def __getattr__(name: str):
    """延迟加载主窗口。"""
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module 'src.gui' has no attribute '{name}'")
    module_path, attr_name = _LAZY_IMPORTS[name]
    import importlib

    full_module_path = f"src.gui{module_path}"
    module = importlib.import_module(full_module_path)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = ["MainWindow"]
