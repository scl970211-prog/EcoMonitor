# -*- coding: utf-8 -*-
"""
打包后清理脚本 - 删除不影响功能的大体积文件

清理项（安全）：
1. Qt 翻译文件：仅保留中文(zh_CN, zh_TW)和英文(en)
2. opengl32sw.dll：纯2D GUI无需Software OpenGL回退
3. Qt6Pdf.dll：程序无PDF显示功能
4. 多余图片格式插件：仅保留 ico/jpeg/png/svg
5. Qt帮助翻译文件
6. ffprobe.exe：_get_video_duration 已支持 ffmpeg 回退
"""

import sys
from pathlib import Path


def cleanup(dist_dir: Path) -> dict:
    saved = 0
    removed_files = []

    internal = dist_dir / "_internal"
    if not internal.exists():
        print(f"[ERROR] 未找到 _internal 目录: {internal}")
        return {"saved_mb": 0, "removed": []}

    # 1. Qt 翻译文件 - 只保留中文和英文
    trans_dir = internal / "PyQt6" / "Qt6" / "translations"
    if trans_dir.exists():
        keep_langs = ("_zh_CN.qm", "_zh_TW.qm", "_en.qm")
        for f in trans_dir.glob("*.qm"):
            if not f.name.endswith(keep_langs):
                saved += f.stat().st_size
                removed_files.append(str(f.relative_to(dist_dir)))
                f.unlink()

    # 2. 删除 opengl32sw.dll
    opengl = internal / "PyQt6" / "Qt6" / "bin" / "opengl32sw.dll"
    if opengl.exists():
        saved += opengl.stat().st_size
        removed_files.append(str(opengl.relative_to(dist_dir)))
        opengl.unlink()

    # 3. 删除 Qt6Pdf.dll
    pdf_dll = internal / "PyQt6" / "Qt6" / "bin" / "Qt6Pdf.dll"
    if pdf_dll.exists():
        saved += pdf_dll.stat().st_size
        removed_files.append(str(pdf_dll.relative_to(dist_dir)))
        pdf_dll.unlink()

    # 4. 删除多余图片格式插件
    img_dir = internal / "PyQt6" / "Qt6" / "plugins" / "imageformats"
    if img_dir.exists():
        keep = {"qico.dll", "qjpeg.dll", "qpng.dll", "qsvg.dll"}
        for f in img_dir.glob("*.dll"):
            if f.name not in keep:
                saved += f.stat().st_size
                removed_files.append(str(f.relative_to(dist_dir)))
                f.unlink()

    # 5. 删除 ffprobe.exe（ffmpeg 可回退获取时长）
    ffprobe = internal / "sdk" / "tools" / "FormatConvert" / "ffprobe.exe"
    if ffprobe.exists():
        saved += ffprobe.stat().st_size
        removed_files.append(str(ffprobe.relative_to(dist_dir)))
        ffprobe.unlink()

    # 6. 清理空目录
    import os
    for root, dirs, files in os.walk(str(internal), topdown=False):
        for d in dirs:
            dpath = Path(root) / d
            try:
                if dpath.exists() and not any(dpath.iterdir()):
                    dpath.rmdir()
            except OSError:
                pass

    saved_mb = saved / (1024 * 1024)
    return {"saved_mb": saved_mb, "removed": removed_files}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        dist_dir = Path(sys.argv[1])
    else:
        # 默认路径：从 build 目录向上找到 dist
        dist_dir = Path(__file__).parent.parent / "dist" / "EcoMonitor"

    print(f"[清理] 目标目录: {dist_dir}")
    result = cleanup(dist_dir)
    print(f"[清理] 删除文件数: {len(result['removed'])}")
    print(f"[清理] 节省空间: {result['saved_mb']:.1f} MB")
    if result['removed']:
        print("[清理] 删除的文件:")
        for f in result['removed'][:10]:
            print(f"  - {f}")
        if len(result['removed']) > 10:
            print(f"  ... 等共 {len(result['removed'])} 个文件")
