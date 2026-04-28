import logging
import os
import sys
import copy
from logging.handlers import RotatingFileHandler
from datetime import datetime


class InstantRotatingFileHandler(RotatingFileHandler):
    """实时写入的 RotatingFileHandler，每次日志都立即 flush"""
    def emit(self, record):
        super().emit(record)
        self.flush()


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器（仅用于控制台输出）"""

    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
    }
    RESET = '\033[0m'

    def format(self, record):
        # 创建记录的副本，避免修改原始记录影响其他处理器
        record_copy = copy.copy(record)
        # 添加颜色到级别名称
        if record_copy.levelname in self.COLORS:
            record_copy.levelname = f"{self.COLORS[record_copy.levelname]}{record_copy.levelname}{self.RESET}"
        return super().format(record_copy)


def setup_logging(log_dir: str = "logs", log_level: str = "INFO"):
    """配置日志系统

    Args:
        log_dir: 日志文件目录
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 控制台日志格式（简洁，带颜色）
    console_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    # 文件日志格式（详细，包含文件位置）
    file_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 清除已有的处理器
    root_logger.handlers.clear()

    # 控制台处理器（彩色输出）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter(console_format, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器 - 按日期命名，实时写入，详细格式
    log_file = os.path.join(
        log_dir,
        f"app_{datetime.now().strftime('%Y-%m-%d')}.log"
    )
    file_handler = InstantRotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(file_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 错误日志单独文件
    error_log_file = os.path.join(
        log_dir,
        f"error_{datetime.now().strftime('%Y-%m-%d')}.log"
    )
    error_handler = InstantRotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(file_format, datefmt=date_format)
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)

    # 设置第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器

    Args:
        name: 日志器名称，通常使用 __name__

    Returns:
        Logger 实例
    """
    return logging.getLogger(name)
