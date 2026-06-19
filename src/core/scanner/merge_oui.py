# -*- coding: utf-8 -*-
"""
合并OUI数据库脚本 - 合并原始条目和扩充条目
"""
import ast
import logging
import os
import re

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # 读取当前文件（包含扩充的数据）
    with open('src/core/scanner/device_info.py', 'r', encoding='utf-8') as f:
        current_content = f.read()
    
    # 读取备份文件（原始数据）
    backup_path = 'src/core/scanner/device_info_backup.py'
    if not os.path.exists(backup_path):
        logger.warning("备份文件不存在: %s", backup_path)
        logger.info("跳过合并，仅验证当前数据库。")
        import sys
        sys.path.insert(0, '.')
        from src.core.scanner.device_info import DEFAULT_OUI_DB
        test_macs = ['00:50:56', '00:0C:29', '00:1C:C4', '00:E0:6F', 'C8:3E:99']
        logger.info("\n验证关键条目:")
        for mac in test_macs:
            vendor = DEFAULT_OUI_DB.get(mac, 'NOT FOUND')
            logger.info("  %s -> %s", mac, vendor)
        return

    with open(backup_path, 'r', encoding='utf-8') as f:
        backup_content = f.read()
    
    # 提取备份中的原始 DEFAULT_OUI_DB
    start = backup_content.find('DEFAULT_OUI_DB = {')
    # 找到匹配的结束括号
    brace_count = 0
    end = start
    for i, c in enumerate(backup_content[start:]):
        if c == '{':
            brace_count += 1
        elif c == '}':
            brace_count -= 1
            if brace_count == 0:
                end = start + i + 1
                break
    
    original_dict = ast.literal_eval(backup_content[start:end].split('=', 1)[1].strip())
    logger.info("原始条目数: %d", len(original_dict))
    
    # 提取当前文件中的扩充数据
    start2 = current_content.find('DEFAULT_OUI_DB = {')
    brace_count = 0
    end2 = start2
    for i, c in enumerate(current_content[start2:]):
        if c == '{':
            brace_count += 1
        elif c == '}':
            brace_count -= 1
            if brace_count == 0:
                end2 = start2 + i + 1
                break
    
    expanded_dict = ast.literal_eval(current_content[start2:end2].split('=', 1)[1].strip())
    logger.info("扩充条目数: %d", len(expanded_dict))
    
    # 合并两个字典（原始条目优先）
    merged_dict = {**expanded_dict, **original_dict}
    logger.info("合并后条目数: %d", len(merged_dict))
    
    # 按MAC前缀排序
    sorted_items = sorted(merged_dict.items(), key=lambda x: x[0])
    
    # 生成新的数据库内容
    lines = ['DEFAULT_OUI_DB = {']
    
    # 按厂商分组
    current_vendor = None
    for mac, vendor in sorted_items:
        if vendor != current_vendor:
            lines.append(f'    # {vendor}')
            current_vendor = vendor
        lines.append(f'    "{mac}": "{vendor}",')
    
    lines.append('}')
    
    new_db = '\n'.join(lines)
    
    # 替换原文件中的数据库
    new_content = current_content[:start2] + new_db + current_content[end2:]
    
    # 写回文件
    with open('src/core/scanner/device_info.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    logger.info("OUI数据库合并完成！")

    # 验证关键条目
    import sys
    sys.path.insert(0, '.')
    from src.core.scanner.device_info import DEFAULT_OUI_DB

    test_macs = ['00:50:56', '00:0C:29', '00:1C:C4', '00:E0:6F', 'C8:3E:99']
    logger.info("\n验证关键条目:")
    for mac in test_macs:
        vendor = DEFAULT_OUI_DB.get(mac, 'NOT FOUND')
        logger.info("  %s -> %s", mac, vendor)

if __name__ == "__main__":
    main()
