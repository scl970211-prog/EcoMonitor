"""
格式转换器，使用 FFmpeg 将 DAV 转为 MP4。
"""

import logging
import math
import os
import platform
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .path_resolver import PathResolver

logger = logging.getLogger(__name__)


class FormatConverter:
    """
    视频录像格式转换器。

    优先走"无损封装"这条最快路径；
    如果输入流兼容性较差，再自动降级到更稳的方案，
    尽量让 MP4 转换在后台无感完成。
    """

    def __init__(self, ffmpeg_path: str = None):
        self.tool_path = str(PathResolver.get_format_convert_path())
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()

        if not self.ffmpeg_path:
            logger.warning("FFmpeg 未找到，转换功能不可用")
            logger.warning("请运行 download_ffmpeg.py 安装 FFmpeg")

    @staticmethod
    def _report_progress(progress_callback, progress: int) -> bool:
        if not progress_callback:
            return True
        return progress_callback(progress) is not False

    def _find_ffmpeg(self) -> Optional[str]:
        possible_paths = []
        for base_dir in PathResolver.get_resource_dirs():
            possible_paths.extend(
                [
                    base_dir / "sdk" / "tools" / "FormatConvert" / "ffmpeg.exe",
                    base_dir / "tools" / "ffmpeg.exe",
                ]
            )

        for path in possible_paths:
            if path.exists():
                return str(path)

        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path
        return None

    def convert(
        self,
        input_path: str,
        output_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        timeout: int = 3600,
    ) -> bool:
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg 未安装，请先运行 download_ffmpeg.py")

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        file_size = os.path.getsize(input_path)
        if file_size < 1024:
            raise ValueError(f"输入文件太小 ({file_size} 字节)，可能无效")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            if progress_callback:
                self._report_progress(progress_callback, 100)
            logger.info("转换输出已存在，直接复用: %s", output_path)
            return True

        return self._convert_with_ffmpeg(input_path, output_path, progress_callback, timeout)

    def convert_to_mp4(
        self,
        input_path: str,
        output_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        timeout: int = 3600,
    ) -> bool:
        """兼容 API，转发到 convert()."""
        return self.convert(
            input_path=input_path,
            output_path=output_path,
            progress_callback=progress_callback,
            timeout=timeout,
        )

    @staticmethod
    def _get_startup_info():
        """获取适用于 Windows 的 startupinfo，用于隐藏控制台窗口"""
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            return startupinfo
        return None

    def _run_ffmpeg(
        self,
        cmd: List[str],
        output_path: str,
        progress_callback: Optional[Callable[[int], None]],
        timeout: int,
        expected_duration: Optional[float] = None,
        progress_offset: float = 0.0,
        progress_span: float = 100.0,
    ) -> bool:
        process = None
        timer = None
        tail_lines: List[str] = []
        
        try:
            # 在 Windows 上隐藏控制台窗口
            startupinfo = self._get_startup_info()
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
                startupinfo=startupinfo,
            )

            # 设置超时定时器
            timer = threading.Timer(timeout, lambda: self._kill_process(process))
            timer.start()
            
            last_progress = -1

            for line in process.stdout:
                tail_lines.append(line.rstrip())
                if len(tail_lines) > 30:
                    tail_lines.pop(0)

                if progress_callback and (not expected_duration or expected_duration <= 0):
                    base_progress = min(int(progress_offset), 99)
                    if base_progress != last_progress:
                        if not self._report_progress(progress_callback, base_progress):
                            raise RuntimeError("Conversion cancelled")
                        last_progress = base_progress

                time_match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                if time_match and expected_duration and expected_duration > 0:
                    hours = int(time_match.group(1))
                    minutes = int(time_match.group(2))
                    seconds = float(time_match.group(3))
                    current_time = hours * 3600 + minutes * 60 + seconds
                    segment_progress = min(current_time / expected_duration, 0.99)
                    total_progress = min(
                        int(progress_offset + segment_progress * progress_span),
                        min(int(progress_offset + progress_span), 99),
                    )

                    if total_progress != last_progress and progress_callback:
                        if not self._report_progress(progress_callback, total_progress):
                            raise RuntimeError("Conversion cancelled")
                        last_progress = total_progress

            # 取消超时定时器
            if timer:
                timer.cancel()
                timer = None

            # 等待进程结束，使用较短的超时
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._kill_process(process)
                raise RuntimeError("FFmpeg 进程未在预期时间内结束")

            if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                if progress_callback:
                    final_progress = min(int(progress_offset + progress_span), 100)
                    if not self._report_progress(progress_callback, final_progress):
                        raise RuntimeError("Conversion cancelled")
                return True

            error_tail = "\n".join(tail_lines[-10:])
            raise RuntimeError(f"FFmpeg 返回错误: {process.returncode}\n{error_tail}".strip())
        finally:
            # 确保资源被清理
            if timer:
                timer.cancel()
            if process:
                self._cleanup_process(process)

    @staticmethod
    def _kill_process(process: subprocess.Popen) -> None:
        """安全终止进程"""
        try:
            process.kill()
        except Exception:
            pass

    @staticmethod
    def _cleanup_process(process: subprocess.Popen) -> None:
        """清理进程资源"""
        try:
            # 关闭管道（stderr 已与 stdout 合并，只需关闭 stdout）
            if process.stdout:
                process.stdout.close()
            # 确保进程已终止
            if process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
            # 等待进程结束，避免僵尸进程
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        except Exception:
            pass

    def _build_conversion_profiles(self, input_path: str, temp_output_path: str) -> List[Tuple[str, List[str]]]:
        common = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-i",
            input_path,
        ]
        return [
            (
                "无损封装",
                common
                + [
                    "-map",
                    "0",
                    "-dn",
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    "-avoid_negative_ts",
                    "make_zero",
                    temp_output_path,
                ],
            ),
            (
                "仅视频无损封装",
                common
                + [
                    "-map",
                    "0:v:0",
                    "-an",
                    "-c:v",
                    "copy",
                    "-movflags",
                    "+faststart",
                    "-avoid_negative_ts",
                    "make_zero",
                    temp_output_path,
                ],
            ),
            (
                "快速稳定转码",
                common
                + [
                    "-map",
                    "0:v:0",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    temp_output_path,
                ],
            ),
        ]

    def _convert_with_ffmpeg(
        self,
        input_path: str,
        output_path: str,
        progress_callback: Optional[Callable[[int], None]],
        timeout: int,
    ) -> bool:
        duration = self._get_video_duration(input_path)
        output_path_obj = Path(output_path)
        # 使用 .tmp.mp4 作为临时扩展名，确保 FFmpeg 能识别格式
        temp_output_path = str(output_path_obj.with_suffix(".tmp.mp4"))

        if os.path.exists(temp_output_path):
            try:
                os.remove(temp_output_path)
            except OSError:
                pass

        profiles = self._build_conversion_profiles(input_path, temp_output_path)
        last_error: Optional[Exception] = None

        for profile_name, cmd in profiles:
            logger.info(
                "MP4 后处理开始: %s -> %s，策略=%s",
                os.path.basename(input_path),
                os.path.basename(output_path),
                profile_name,
            )
            try:
                if os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
                success = self._run_ffmpeg(
                    cmd,
                    temp_output_path,
                    progress_callback,
                    timeout,
                    expected_duration=duration,
                    progress_offset=0.0,
                    progress_span=100.0,
                )
                if success:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    os.replace(temp_output_path, output_path)
                    logger.info("转换成功: %s，策略=%s", output_path, profile_name)
                    return True
            except Exception as exc:
                last_error = exc
                logger.warning("转换策略失败: %s，错误: %s", profile_name, exc)
            finally:
                if os.path.exists(temp_output_path):
                    try:
                        os.remove(temp_output_path)
                    except OSError:
                        pass

        raise RuntimeError(f"MP4 后处理失败: {last_error}") from last_error

    def convert_with_split(
        self,
        input_path: str,
        output_dir: str,
        base_filename: str,
        split_size_gb: float = 4.0,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[str]:
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg 未安装")

        split_bytes = split_size_gb * 1024 * 1024 * 1024
        file_size = os.path.getsize(input_path)
        if file_size <= split_bytes:
            output_path = os.path.join(output_dir, f"{base_filename}.mp4")
            self.convert(input_path, output_path, progress_callback)
            return [output_path]

        duration = self._get_video_duration(input_path)
        if not duration:
            # 无法获取时长时，直接转换整个文件（无法计算分段）
            output_path = os.path.join(output_dir, f"{base_filename}.mp4")
            self.convert(input_path, output_path, progress_callback, timeout=3600)
            return [output_path]

        num_parts = math.ceil(file_size / split_bytes)
        segment_duration = duration / num_parts
        output_files = []

        for index in range(num_parts):
            start_time = index * segment_duration
            output_path = os.path.join(output_dir, f"{base_filename}_part{index + 1:03d}.mp4")
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-ss",
                str(start_time),
                "-t",
                str(segment_duration),
                "-i",
                input_path,
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                output_path,
            ]
            if self._run_ffmpeg(
                cmd,
                output_path,
                progress_callback,
                3600,
                expected_duration=segment_duration,
                progress_offset=(100.0 * index) / num_parts,
                progress_span=100.0 / num_parts,
            ):
                output_files.append(output_path)
        return output_files

    def _get_video_duration(self, input_path: str) -> Optional[float]:
        if not self.ffmpeg_path:
            return None

        ffmpeg_file = Path(self.ffmpeg_path)
        ffprobe_path = ffmpeg_file.with_name("ffprobe.exe" if ffmpeg_file.name.lower() == "ffmpeg.exe" else "ffprobe")

        # 优先使用 ffprobe（精确、快速）
        if ffprobe_path.exists():
            try:
                cmd = [
                    str(ffprobe_path),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    input_path,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30,
                    startupinfo=self._get_startup_info()
                )
                if result.returncode == 0:
                    return float(result.stdout.strip())
            except Exception:
                pass

        # 回退：用 ffmpeg -i 解析时长（无 ffprobe 时可用，体积更小）
        try:
            cmd = [
                self.ffmpeg_path,
                "-i",
                input_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                startupinfo=self._get_startup_info()
            )
            # ffmpeg 输出在 stderr，示例: Duration: 00:05:23.12, start: 0.000000
            match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", result.stderr)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                return hours * 3600 + minutes * 60 + seconds
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        return bool(self.ffmpeg_path)

    def get_version(self) -> Optional[str]:
        if not self.ffmpeg_path:
            return None

        try:
            result = subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.split("\n")[0]
        except Exception:
            pass
        return None
