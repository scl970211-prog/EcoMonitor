# -*- coding: utf-8 -*-
"""
录像搜索模块
使用设备 SDK V40 接口搜索录像文件
"""

import ctypes
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

from .sdk_loader import SDKLoader, NET_DVR_TIME, NET_DVR_FILECOND_V40, NET_DVR_FINDDATA_V40

logger = logging.getLogger(__name__)


@dataclass
class RecordFile:
    """录像文件信息"""
    filename: str
    channel: int
    start_time: datetime
    end_time: datetime
    size: int  # bytes
    locked: bool = False
    file_type: int = 0


def _datetime_to_net_dvr_time(dt: datetime) -> NET_DVR_TIME:
    """将 Python datetime 转换为 NET_DVR_TIME"""
    t = NET_DVR_TIME()
    t.dwYear = dt.year
    t.dwMonth = dt.month
    t.dwDay = dt.day
    t.dwHour = dt.hour
    t.dwMinute = dt.minute
    t.dwSecond = dt.second
    return t


def _net_dvr_time_to_datetime(t: NET_DVR_TIME) -> datetime:
    """将 NET_DVR_TIME 转换为 Python datetime"""
    return datetime(
        int(t.dwYear), int(t.dwMonth), int(t.dwDay),
        int(t.dwHour), int(t.dwMinute), int(t.dwSecond)
    )


class VideoSearcher:
    """录像搜索器（V40 接口）"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self._sdk = SDKLoader()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
    
    def search_by_time_v40(self, channel: int, start_time: datetime, end_time: datetime) -> List[RecordFile]:
        """
        按时间范围搜索录像文件（V40 接口）
        
        Args:
            channel: 通道号
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[RecordFile]: 录像文件列表
        """
        if not self._sdk.is_loaded:
            logger.error("SDK 未加载")
            return []
        
        try:
            # 构建查找条件
            cond = NET_DVR_FILECOND_V40()
            cond.dwSize = ctypes.sizeof(NET_DVR_FILECOND_V40)
            cond.lChannel = channel
            cond.dwFileType = 0xFF  # 所有类型
            cond.dwIsLocked = 0xFFFFFFFF  # 不区分锁定状态
            cond.dwUseCardNo = 0
            cond.byDrawFrame = 0
            cond.byFind = 0
            cond.byStreamType = 0
            cond.byAudioCond = 0
            cond.byNeedCard = 0
            cond.bySpecialFindInfoType = 0
            cond.struStartTime = _datetime_to_net_dvr_time(start_time)
            cond.struStopTime = _datetime_to_net_dvr_time(end_time)
            
            # 开始查找
            find_handle = self._sdk.NET_DVR_FindFile_V40(self.user_id, cond)
            if find_handle < 0:
                error_code = self._sdk.get_last_error()
                logger.error(f"NET_DVR_FindFile_V40 失败，错误码: {error_code}")
                return []
            
            files: List[RecordFile] = []
            
            while True:
                file_data = NET_DVR_FINDDATA_V40()
                file_data.dwSize = ctypes.sizeof(NET_DVR_FINDDATA_V40)
                result = self._sdk.NET_DVR_FindNextFile_V40(find_handle, file_data)
                
                if result == 1000:  # NET_DVR_FILE_SUCCESS
                    try:
                        filename = file_data.sFileName.decode('gbk').rstrip('\x00')
                    except UnicodeDecodeError:
                        filename = file_data.sFileName.decode('utf-8', errors='ignore').rstrip('\x00')
                    
                    file_start = _net_dvr_time_to_datetime(file_data.struStartTime)
                    file_end = _net_dvr_time_to_datetime(file_data.struStopTime)
                    
                    # 过滤掉超出查询范围的文件
                    if file_end < start_time or file_start > end_time:
                        continue
                    
                    files.append(RecordFile(
                        filename=filename,
                        channel=channel,
                        start_time=file_start,
                        end_time=file_end,
                        size=int(file_data.dwFileSize),
                        locked=bool(file_data.byLocked),
                        file_type=int(file_data.byFileType)
                    ))
                elif result == 1001:  # NET_DVR_FILE_NOFIND
                    break
                elif result == 1002:  # NET_DVR_ISFINDING
                    continue
                elif result == 1003:  # NET_DVR_NOMOREFILE
                    break
                else:
                    logger.warning(f"FindNextFile 返回未知结果: {result}")
                    break
            
            # 关闭查找
            self._sdk.NET_DVR_FindClose(find_handle)
            
            logger.info(f"通道 {channel} 搜索到 {len(files)} 个录像文件")
            return files
            
        except Exception as e:
            logger.exception(f"搜索录像失败: {e}")
            return []


def search_device_recordings(device, channels: List[int], start_time: datetime, end_time: datetime) -> Dict[int, List[RecordFile]]:
    """
    搜索多个通道的录像
    
    Args:
        device: 已登录的设备对象（需有 user_id 属性）
        channels: 通道号列表
        start_time: 开始时间
        end_time: 结束时间
        
    Returns:
        Dict[int, List[RecordFile]]: 通道号 -> 文件列表
    """
    results: Dict[int, List[RecordFile]] = {}
    user_id = getattr(device, 'user_id', None)
    if user_id is None:
        logger.error("设备对象缺少 user_id")
        return results
    
    with VideoSearcher(user_id) as searcher:
        for channel in channels:
            files = searcher.search_by_time_v40(channel, start_time, end_time)
            if files:
                results[channel] = files
    
    return results
