"""
AlphaPulse - 로깅 설정 모듈

loguru 기반 구조화 로깅을 설정합니다.
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_dir: Path, level: str = "INFO") -> None:
    """로거 초기화 - 콘솔 + 파일 동시 출력"""
    logger.remove()  # 기본 핸들러 제거

    # 콘솔 출력 (컬러)
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 파일 출력 (일별 로테이션)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "alphapulse_{time:YYYY-MM-DD}.log",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",     # 매일 자정 로테이션
        retention="30 days",  # 30일 보관
        encoding="utf-8",
    )


# 편의를 위해 logger 직접 export
__all__ = ["logger", "setup_logger"]
