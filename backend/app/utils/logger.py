#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : logger.py
@Time    : 2026/9/20 16:33
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""

import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT_PATH = Path(os.path.abspath(__file__)).parent.parent.parent
LOG_BASE_PATH = ROOT_PATH / "logs"

class DailyFileHandler(logging.Handler):
    """
    按天分文件的日志处理器：
    - 文件名形如 2024-09-20.log
    - 每天自动切换到新文件
    - 自动清理超过保留天数的旧文件
    """

    def __init__(self, log_dir: str, retention_days: int = 7, encoding: str = "utf-8"):
        super().__init__()
        self.log_dir = log_dir
        self.retention_days = retention_days
        self.encoding = encoding
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        self._current_date = None
        self._stream = None
        self._switch_stream()

    # ---------- 内部方法 ----------
    def _get_file_path(self, date_str: str) -> str:
        return os.path.join(self.log_dir, f"{date_str}.log")

    def _switch_stream(self):
        """如果日期变了或流被外部关闭（如dictConfig），切换/重新打开文件句柄并清理过期日志"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._stream is None or today != self._current_date:
            if self._stream:
                self._stream.close()
            self._current_date = today
            self._stream = open(self._get_file_path(today), "a", encoding=self.encoding)
            self._cleanup()

    def _cleanup(self):
        """删除超过保留天数的日志文件"""
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) \
                 - timedelta(days=self.retention_days - 1)
        for fname in os.listdir(self.log_dir):
            if not fname.endswith(".log"):
                continue
            date_str = fname[:-4]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    os.remove(os.path.join(self.log_dir, fname))
                except OSError:
                    pass

    # ---------- logging.Handler 接口 ----------
    def emit(self, record: logging.LogRecord):
        try:
            self._switch_stream()
            msg = self.format(record)
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        if self._stream:
            self._stream.close()
            self._stream = None
        super().close()


class LogManager:
    """
    日志管理工具类（单例复用）。

    用法：
        logger = LogManager.get_logger("myapp")
        logger.info("...")
        logger.error("...")
    """

    DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

    _loggers = {}
    _lock = threading.Lock()

    @classmethod
    def get_logger(
        cls,
        name: str = "app",
        log_dir: str = ROOT_PATH / "logs",
        retention_days: int = 7,
        file_level: int = logging.INFO,
        console_level: int = logging.ERROR,
        fmt: str = None,
        datefmt: str = None,
    ) -> logging.Logger:
        """
        :param name:            logger 名称（也是日志文件中 name 字段）
        :param log_dir:         日志目录
        :param retention_days:  日志保留天数（默认 7 天）
        :param file_level:      写入文件的最低级别（默认 INFO）
        :param console_level:   输出到终端的最低级别（默认 ERROR）
        :param fmt:             日志格式，默认使用 DEFAULT_FORMAT
        :param datefmt:         时间格式，默认使用 DEFAULT_DATEFMT
        """
        with cls._lock:
            if name in cls._loggers:
                return cls._loggers[name]

            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)      # 总开关，向下放行
            logger.propagate = False            # 防止被 root logger 重复输出

            formatter = logging.Formatter(
                fmt or cls.DEFAULT_FORMAT,
                datefmt or cls.DEFAULT_DATEFMT,
            )

            # --- 文件处理器：INFO 及以上，按天分文件 ---
            file_handler = DailyFileHandler(log_dir, retention_days)
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # --- 终端处理器：ERROR 及以上 ---
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(console_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

            cls._loggers[name] = logger
            return logger


_logger = None
def get_logger(name: str = "app", **kwargs) -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = LogManager.get_logger(name, **kwargs)
    return _logger


# ================= 使用示例 =================
if __name__ == "__main__":
    logger = LogManager.get_logger(
        name=__name__,
        retention_days=7,
    )

    logger.debug("这条只会被过滤掉（logger 总级别 DEBUG，但 handler 最低 INFO）")
    logger.info("这是一条 info，写入日志文件，终端不显示")
    logger.warning("这是一条 warning，写入日志文件，终端不显示")
    logger.error("这是一条 error，同时写入文件和终端")
    logger.critical("这是一条 critical，同时写入文件和终端")

    # 模拟异常
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("发生异常：")