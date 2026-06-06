"""
SDK 加载模块 - 设备 SDK 封装 (PyQt6 适配版)

扩展功能：实时预览、录像下载、文件查找
"""

import os
import sys
import ctypes
import threading
import logging
from pathlib import Path

from .path_resolver import get_sdk_path

logger = logging.getLogger(__name__)


# ==================== SDK 结构体定义 ====================

class NET_DVR_DEVICEINFO_V30(ctypes.Structure):
    """设备信息结构体"""
    _fields_ = [
        ("sSerialNumber", ctypes.c_ubyte * 48),
        ("byAlarmInPortNum", ctypes.c_byte),
        ("byAlarmOutPortNum", ctypes.c_byte),
        ("byDiskNum", ctypes.c_byte),
        ("byDVRType", ctypes.c_byte),
        ("byChanNum", ctypes.c_byte),
        ("byStartChan", ctypes.c_byte),
        ("byAudioChanNum", ctypes.c_byte),
        ("byIPChanNum", ctypes.c_byte),
        ("byZeroChanNum", ctypes.c_byte),
        ("byMainProto", ctypes.c_byte),
        ("bySubProto", ctypes.c_byte),
        ("bySupport", ctypes.c_byte),
        ("bySupport1", ctypes.c_byte),
        ("bySupport2", ctypes.c_byte),
        ("wDevType", ctypes.c_ushort),
        ("bySupport3", ctypes.c_byte),
        ("byMultiStreamProto", ctypes.c_byte),
        ("byStartDChan", ctypes.c_byte),
        ("byStartDTalkChan", ctypes.c_byte),
        ("byHighDChanNum", ctypes.c_byte),
        ("bySupport4", ctypes.c_byte),
        ("byLanguageType", ctypes.c_byte),
        ("byVoiceInChanNum", ctypes.c_byte),
        ("byStartVoiceInChanNo", ctypes.c_byte),
        ("byRes3", ctypes.c_byte * 2),
        ("byMirrorChanNum", ctypes.c_byte),
        ("wStartMirrorChanNo", ctypes.c_ushort),
        ("byRes2", ctypes.c_byte * 2),
    ]


class NET_DVR_TIME(ctypes.Structure):
    """时间结构体"""
    _fields_ = [
        ("dwYear", ctypes.c_uint),
        ("dwMonth", ctypes.c_uint),
        ("dwDay", ctypes.c_uint),
        ("dwHour", ctypes.c_uint),
        ("dwMinute", ctypes.c_uint),
        ("dwSecond", ctypes.c_uint),
    ]


class NET_DVR_FINDDATA_V30(ctypes.Structure):
    """录像文件查找结构体"""
    _fields_ = [
        ("sFileName", ctypes.c_char * 100),
        ("struStartTime", NET_DVR_TIME),
        ("struStopTime", NET_DVR_TIME),
        ("dwFileSize", ctypes.c_uint),
        ("sCardNum", ctypes.c_char * 32),
        ("byLocked", ctypes.c_byte),
        ("byFileType", ctypes.c_byte),
        ("byQuickSearch", ctypes.c_byte),
        ("byRes", ctypes.c_byte * 117),
    ]


class NET_DVR_FILECOND_V40(ctypes.Structure):
    """录像查找条件 V40"""
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("lChannel", ctypes.c_long),
        ("dwFileType", ctypes.c_uint32),
        ("dwIsLocked", ctypes.c_uint32),
        ("dwUseCardNo", ctypes.c_uint32),
        ("sCardNumber", ctypes.c_byte * 32),
        ("struStartTime", NET_DVR_TIME),
        ("struStopTime", NET_DVR_TIME),
        ("byDrawFrame", ctypes.c_byte),
        ("byFind", ctypes.c_byte),
        ("byStreamType", ctypes.c_byte),
        ("byAudioCond", ctypes.c_byte),
        ("byNeedCard", ctypes.c_byte),
        ("bySpecialFindInfoType", ctypes.c_byte),
        ("byStreamID", ctypes.c_byte * 32),
        ("byRes", ctypes.c_byte * 152),
    ]


class NET_DVR_FINDDATA_V40(ctypes.Structure):
    """录像文件信息 V40"""
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("sFileName", ctypes.c_char * 100),
        ("struStartTime", NET_DVR_TIME),
        ("struStopTime", NET_DVR_TIME),
        ("dwFileSize", ctypes.c_uint32),
        ("sCardNum", ctypes.c_char * 32),
        ("byLocked", ctypes.c_byte),
        ("byFileType", ctypes.c_byte),
        ("byQuickSearch", ctypes.c_byte),
        ("byStreamType", ctypes.c_byte),
        ("byAudioStream", ctypes.c_byte),
        ("byRes1", ctypes.c_byte * 123),
    ]


class NET_DVR_PREVIEWINFO(ctypes.Structure):
    """预览参数结构体"""
    _fields_ = [
        ("lChannel", ctypes.c_long),           # 通道号
        ("dwStreamType", ctypes.c_uint),       # 码流类型：0-主码流，1-子码流，2-三码流
        ("dwLinkMode", ctypes.c_uint),         # 连接方式：0-TCP，1-UDP，2-多播，3-RTP
        ("hPlayWnd", ctypes.c_void_p),         # 播放窗口句柄
        ("bBlocked", ctypes.c_bool),           # 是否阻塞取流
        ("bPassbackRecord", ctypes.c_bool),    # 是否支持录像回传
        ("byPreviewMode", ctypes.c_byte),      # 预览模式
        ("byStreamID", ctypes.c_byte * 32),    # 流ID
        ("byProtoType", ctypes.c_byte),        # 应用层协议类型
        ("byRes1", ctypes.c_byte * 2),
        ("dwDisplayBufNum", ctypes.c_uint),    # 播放库播放缓冲区最大缓冲帧数
        ("byRes", ctypes.c_byte * 216),
    ]


class NET_DVR_VOD_PARA(ctypes.Structure):
    """录像下载参数结构体"""
    _fields_ = [
        ("dwSize", ctypes.c_uint),
        ("struBeginTime", NET_DVR_TIME),
        ("struEndTime", NET_DVR_TIME),
        ("hWnd", ctypes.c_void_p),
        ("byDrawFrame", ctypes.c_byte),
        ("byRes", ctypes.c_byte * 35),
    ]


class NET_DVR_PLAYCOND(ctypes.Structure):
    """远程回放/下载条件结构体"""
    _fields_ = [
        ("dwSize", ctypes.c_uint),
        ("dwChannel", ctypes.c_uint),
        ("struStartTime", NET_DVR_TIME),
        ("struStopTime", NET_DVR_TIME),
        ("byDrawFrame", ctypes.c_byte),
        ("byStreamType", ctypes.c_byte),
        ("byStreamID", ctypes.c_byte * 32),
        ("byRes", ctypes.c_byte * 47),
    ]


# ==================== 回调函数类型定义 ====================

# 实时流回调函数
REALDATACALLBACK = ctypes.CFUNCTYPE(
    None,
    ctypes.c_long,          # lRealHandle
    ctypes.c_uint,          # dwDataType
    ctypes.POINTER(ctypes.c_ubyte),  # pBuffer
    ctypes.c_uint,          # dwBufSize
    ctypes.c_void_p         # pUser
)

# 回放/下载进度回调
PLAYDATACALLBACK = ctypes.CFUNCTYPE(
    None,
    ctypes.c_long,          # lPlayHandle
    ctypes.c_uint,          # dwDataType
    ctypes.POINTER(ctypes.c_ubyte),  # pBuffer
    ctypes.c_uint,          # dwBufSize
    ctypes.c_void_p         # pUser
)

# 进度回调函数
POSCALLBACK = ctypes.CFUNCTYPE(
    None,
    ctypes.c_long,          # lPlayHandle
    ctypes.c_uint,          # dwTotalSize
    ctypes.c_uint,          # dwDownLoadSize
    ctypes.c_void_p         # pUser
)


def get_error_message(error_code: int) -> str:
    """获取错误码对应的错误信息"""
    error_messages = {
        0: "没有错误",
        1: "用户名密码错误",
        2: "权限不足",
        3: "SDK未初始化",
        4: "版本不匹配",
        5: "连接设备失败",
        6: "设备未登录",
        7: "参数错误",
        8: "设备无此功能",
        9: "SDK资源不足",
        10: "设备资源不足",
        11: "设备操作失败",
        12: "网络错误",
        13: "设备正在处理",
        14: "设备命令执行失败",
        15: "串口操作失败",
        16: "用户ID或密码错误",
        17: "设备忙",
        18: "无此文件",
        19: "没有权限",
    }
    return error_messages.get(error_code, f"未知错误 (代码: {error_code})")


class SDKLoader:
    """SDK 加载器 (单例模式)"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._sdk = None
        self._loaded = False
        self._callbacks = {}
        self._initialized = True
        logger.debug("SDKLoader 初始化完成")
    
    def load(self) -> bool:
        """加载 SDK"""
        if self._loaded and self._sdk:
            return True
        
        try:
            sdk_path = get_sdk_path()
            
            # 添加 SDK 目录到 DLL 搜索路径
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(str(sdk_path))
            
            # ===== 新增：确保 HCNetSDKCom 子目录可被 Windows 找到 =====
            sdk_com_path = sdk_path / "HCNetSDKCom"
            paths_to_add = [str(sdk_path)]
            if sdk_com_path.exists():
                paths_to_add.append(str(sdk_com_path))
            current_path = os.environ.get("PATH", "")
            # 避免重复追加
            new_path_prefix = os.pathsep.join(paths_to_add)
            if not current_path.startswith(new_path_prefix):
                os.environ["PATH"] = new_path_prefix + os.pathsep + current_path
            # ==========================================================
            
            # 设置工作目录为 SDK 目录
            original_dir = os.getcwd()
            os.chdir(sdk_path)
            
            try:
                # 加载主 DLL
                dll_path = sdk_path / "HCNetSDK.dll"
                if not dll_path.exists():
                    raise FileNotFoundError(f"SDK DLL 未找到: {dll_path}")
                
                self._sdk = ctypes.WinDLL(str(dll_path))
                self._setup_common_api()
                
                # 初始化 SDK
                self._sdk.NET_DVR_Init()
                
                # 设置连接超时和重连
                self._sdk.NET_DVR_SetConnectTime(5000, 3)
                self._sdk.NET_DVR_SetReconnect(10000, True)
                
                # 设置日志
                log_path = sdk_path / "logs"
                log_path.mkdir(exist_ok=True)
                self._sdk.NET_DVR_SetLogToFile(3, str(log_path), True)
                
                self._loaded = True
                logger.info("SDK 加载成功")
                return True
                
            finally:
                os.chdir(original_dir)
                
        except Exception as e:
            logger.error(f"SDK 加载失败: {e}")
            self._loaded = False
            return False

    def _setup_common_api(self):
        """补齐多个模块共用的 SDK 函数原型。"""
        if not self._sdk:
            return

        try:
            self._sdk.NET_DVR_GetDVRConfig.argtypes = [
                ctypes.c_long,
                ctypes.c_uint32,
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32),
            ]
            self._sdk.NET_DVR_GetDVRConfig.restype = ctypes.c_bool
        except Exception:
            pass

        try:
            self._sdk.NET_DVR_RealPlay_V40.argtypes = [
                ctypes.c_long,
                ctypes.POINTER(NET_DVR_PREVIEWINFO),
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            self._sdk.NET_DVR_RealPlay_V40.restype = ctypes.c_long
            self._sdk.NET_DVR_StopRealPlay.argtypes = [ctypes.c_long]
            self._sdk.NET_DVR_StopRealPlay.restype = ctypes.c_bool
        except Exception:
            pass

        try:
            self._sdk.NET_DVR_GetFileByName.argtypes = [
                ctypes.c_long,
                ctypes.c_char_p,
                ctypes.c_char_p,
            ]
            self._sdk.NET_DVR_GetFileByName.restype = ctypes.c_long
        except Exception:
            pass
    
    def cleanup(self):
        """清理 SDK 资源"""
        if self._sdk and self._loaded:
            try:
                self._sdk.NET_DVR_Cleanup()
                logger.info("SDK 清理完成")
            except Exception as e:
                logger.error(f"SDK 清理失败: {e}")
            finally:
                self._loaded = False
                self._sdk = None
    
    @property
    def sdk(self):
        """获取 SDK 实例"""
        if not self._loaded:
            self.load()
        return self._sdk
    
    @property
    def is_loaded(self) -> bool:
        """SDK 是否已加载"""
        return self._loaded and self._sdk is not None
    
    def get_sdk_version(self) -> str:
        """获取 SDK 版本"""
        if not self.is_loaded:
            return "SDK 未加载"
        
        try:
            self._sdk.NET_DVR_GetSDKVersion.restype = ctypes.c_uint
            version = self._sdk.NET_DVR_GetSDKVersion()
            
            major = (version >> 24) & 0xFF
            minor = (version >> 16) & 0xFF
            build = version & 0xFFFF
            
            return f"V{major}.{minor}.{build}"
        except Exception as e:
            logger.error(f"获取 SDK 版本失败: {e}")
            return "未知版本"
    
    def get_last_error(self) -> int:
        """获取最后错误码"""
        if self._sdk:
            return self._sdk.NET_DVR_GetLastError()
        return -1
    
    # ==================== 预览相关 API ====================
    
    def real_play(self, user_id: int, preview_info: NET_DVR_PREVIEWINFO) -> int:
        """
        开始实时预览
        
        Args:
            user_id: 用户ID
            preview_info: 预览参数
        
        Returns:
            预览句柄，失败返回 -1
        """
        if not self._sdk:
            return -1
        
        try:
            self._sdk.NET_DVR_RealPlay_V40.argtypes = [ctypes.c_long, ctypes.POINTER(NET_DVR_PREVIEWINFO), REALDATACALLBACK, ctypes.c_void_p]
            self._sdk.NET_DVR_RealPlay_V40.restype = ctypes.c_long
            
            handle = self._sdk.NET_DVR_RealPlay_V40(user_id, ctypes.byref(preview_info), None, None)
            return handle
        except Exception as e:
            logger.error(f"开始预览失败: {e}")
            return -1
    
    def stop_real_play(self, handle: int) -> bool:
        """停止实时预览"""
        if not self._sdk or handle < 0:
            return False
        
        try:
            return self._sdk.NET_DVR_StopRealPlay(handle)
        except Exception as e:
            logger.error(f"停止预览失败: {e}")
            return False
    
    # ==================== 下载相关 API ====================
    
    def get_file_by_time(self, user_id: int, save_path: str, play_cond: NET_DVR_PLAYCOND) -> int:
        """
        按时间下载录像
        
        Args:
            user_id: 用户ID
            save_path: 保存路径
            play_cond: 回放条件
        
        Returns:
            下载句柄，失败返回 -1
        """
        if not self._sdk:
            return -1
        
        try:
            self._sdk.NET_DVR_GetFileByTime_V40.argtypes = [
                ctypes.c_long,
                ctypes.c_char_p,
                ctypes.POINTER(NET_DVR_PLAYCOND)
            ]
            self._sdk.NET_DVR_GetFileByTime_V40.restype = ctypes.c_long
            
            handle = self._sdk.NET_DVR_GetFileByTime_V40(
                user_id,
                save_path.encode('gb2312'),  # SDK 使用 GB2312
                ctypes.byref(play_cond)
            )
            return handle
        except Exception as e:
            logger.error(f"开始下载失败: {e}")
            return -1
    
    def play_back_control(self, handle: int, control_code: int, param: int = 0) -> bool:
        """
        回放/下载控制
        
        Args:
            handle: 回放/下载句柄
            control_code: 控制命令
                1 - 开始播放/下载
                2 - 停止
                3 - 暂停
                4 - 恢复
            param: 参数
        """
        if not self._sdk or handle < 0:
            return False
        
        try:
            return self._sdk.NET_DVR_PlayBackControl(handle, control_code, param, None)
        except Exception as e:
            logger.error(f"下载控制失败: {e}")
            return False
    
    def stop_get_file(self, handle: int) -> bool:
        """停止下载"""
        if not self._sdk or handle < 0:
            return False
        
        try:
            return self._sdk.NET_DVR_StopGetFile(handle)
        except Exception as e:
            logger.error(f"停止下载失败: {e}")
            return False
    
    def get_download_pos(self, handle: int) -> int:
        """
        获取下载进度
        
        Returns:
            0-100: 进度百分比
            -1: 失败
            100: 完成
            200: 异常
        """
        if not self._sdk or handle < 0:
            return -1
        
        try:
            return self._sdk.NET_DVR_GetDownloadPos(handle)
        except Exception as e:
            logger.error(f"获取下载进度失败: {e}")
            return -1
    
    # ==================== 录像查找 API ====================
    
    def find_file(self, user_id: int, channel: int, start_time: NET_DVR_TIME, end_time: NET_DVR_TIME) -> int:
        """
        查找录像文件
        
        Returns:
            查找句柄，失败返回 -1
        """
        if not self._sdk:
            return -1
        
        try:
            self._sdk.NET_DVR_FindFile_V30.argtypes = [
                ctypes.c_long, ctypes.c_long,
                ctypes.c_uint,
                ctypes.POINTER(NET_DVR_TIME),
                ctypes.POINTER(NET_DVR_TIME)
            ]
            self._sdk.NET_DVR_FindFile_V30.restype = ctypes.c_long
            
            handle = self._sdk.NET_DVR_FindFile_V30(
                user_id, channel, 0xff,  # 0xff = 所有录像类型
                ctypes.byref(start_time),
                ctypes.byref(end_time)
            )
            return handle
        except Exception as e:
            logger.error(f"查找录像失败: {e}")
            return -1
    
    def find_next_file(self, find_handle: int, file_data: NET_DVR_FINDDATA_V30) -> int:
        """
        查找下一个文件
        
        Returns:
            1000 - 成功
            1001 - 没有更多文件
            -1 - 失败
        """
        if not self._sdk:
            return -1
        
        try:
            self._sdk.NET_DVR_FindNextFile_V30.argtypes = [ctypes.c_long, ctypes.POINTER(NET_DVR_FINDDATA_V30)]
            self._sdk.NET_DVR_FindNextFile_V30.restype = ctypes.c_long
            
            return self._sdk.NET_DVR_FindNextFile_V30(find_handle, ctypes.byref(file_data))
        except Exception as e:
            logger.error(f"查找下一个文件失败: {e}")
            return -1
    
    def find_close(self, find_handle: int) -> bool:
        """关闭查找"""
        if not self._sdk:
            return False
        
        try:
            return self._sdk.NET_DVR_FindClose_V30(find_handle)
        except Exception as e:
            logger.error(f"关闭查找失败: {e}")
            return False
    
    # ==================== 旧版查找 API 兼容 ====================
    
    def NET_DVR_FindFile(self, user_id: int, channel: int, file_type: int,
                         start_time, end_time) -> int:
        """旧版查找录像文件"""
        if not self._sdk:
            return -1
        try:
            self._sdk.NET_DVR_FindFile.argtypes = [
                ctypes.c_long, ctypes.c_long, ctypes.c_uint,
                ctypes.c_void_p, ctypes.c_void_p
            ]
            self._sdk.NET_DVR_FindFile.restype = ctypes.c_long
            
            return self._sdk.NET_DVR_FindFile(
                user_id, channel, file_type,
                ctypes.byref(start_time) if start_time else None,
                ctypes.byref(end_time) if end_time else None
            )
        except Exception as e:
            logger.error(f"NET_DVR_FindFile 失败: {e}")
            return -1
    
    def NET_DVR_FindNextFile(self, find_handle: int, file_data) -> int:
        """查找下一个文件"""
        if not self._sdk:
            return -1
        try:
            self._sdk.NET_DVR_FindNextFile.argtypes = [ctypes.c_long, ctypes.c_void_p]
            self._sdk.NET_DVR_FindNextFile.restype = ctypes.c_long
            return self._sdk.NET_DVR_FindNextFile(find_handle, ctypes.byref(file_data))
        except Exception as e:
            logger.error(f"NET_DVR_FindNextFile 失败: {e}")
            return -1
    
    def NET_DVR_FindClose(self, find_handle: int) -> bool:
        """关闭查找"""
        if not self._sdk:
            return False
        try:
            return self._sdk.NET_DVR_FindClose(find_handle)
        except Exception as e:
            logger.error(f"NET_DVR_FindClose 失败: {e}")
            return False
    
    def NET_DVR_FindFile_V40(self, user_id: int, search_cond) -> int:
        """V40 查找录像"""
        if not self._sdk:
            return -1
        try:
            self._sdk.NET_DVR_FindFile_V40.argtypes = [ctypes.c_long, ctypes.c_void_p]
            self._sdk.NET_DVR_FindFile_V40.restype = ctypes.c_long
            return self._sdk.NET_DVR_FindFile_V40(user_id, ctypes.byref(search_cond))
        except Exception as e:
            logger.error(f"NET_DVR_FindFile_V40 失败: {e}")
            return -1
    
    def NET_DVR_FindNextFile_V40(self, find_handle: int, file_data) -> int:
        """V40 查找下一个"""
        if not self._sdk:
            return -1
        try:
            self._sdk.NET_DVR_FindNextFile_V40.argtypes = [ctypes.c_long, ctypes.c_void_p]
            self._sdk.NET_DVR_FindNextFile_V40.restype = ctypes.c_long
            return self._sdk.NET_DVR_FindNextFile_V40(find_handle, ctypes.byref(file_data))
        except Exception as e:
            logger.error(f"NET_DVR_FindNextFile_V40 失败: {e}")
            return -1
    
    def NET_DVR_RealPlayPause(self, handle: int, control: int) -> bool:
        """暂停/恢复预览"""
        if not self._sdk:
            return False
        try:
            # 使用 NET_DVR_ClientPushInfo 或类似的控制命令
            # 这里使用 PlayBackControl 作为替代
            return self._sdk.NET_DVR_PlayBackControl(handle, 3 if control else 4, 0, None)
        except Exception as e:
            logger.error(f"暂停/恢复预览失败: {e}")
            return False
    
    # ==================== 结构体类属性 ====================
    
    @property
    def NET_DVR_TIME(self):
        return NET_DVR_TIME
    
    @property
    def NET_DVR_FINDDATA_V30(self):
        return NET_DVR_FINDDATA_V30
    
    @property
    def NET_DVR_PREVIEWINFO(self):
        return NET_DVR_PREVIEWINFO
    
    @property
    def NET_DVR_PLAYCOND(self):
        return NET_DVR_PLAYCOND
