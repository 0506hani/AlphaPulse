"""
AlphaPulse - APScheduler 기반 자동 실행 스케줄러

월~토 오전 7시, 오후 6시에 파이프라인을 자동 실행합니다.
실패 시 최대 3회 재시도 (지수 백오프).
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from alphapulse.config import settings
from alphapulse.utils.logger import logger


class JobScheduler:
    """APScheduler 기반 자동 실행 스케줄러"""

    def __init__(self, pipeline_fn: Callable[[], bool]):
        """
        Args:
            pipeline_fn: 실행할 파이프라인 함수 () -> bool (성공 여부 반환)
        """
        self._pipeline_fn = pipeline_fn
        self._scheduler = BlockingScheduler(timezone=settings.timezone)
        self._health_file = settings.cache_dir_path / "health.json"

        morning_hour, morning_minute = self._parse_time(settings.schedule_morning)
        evening_hour, evening_minute = self._parse_time(settings.schedule_evening)

        # 오전 스케줄: 월~토 (0~5)
        self._scheduler.add_job(
            func=self._run_with_retry,
            trigger=CronTrigger(
                day_of_week="mon-sat",
                hour=morning_hour,
                minute=morning_minute,
                timezone=settings.timezone,
            ),
            kwargs={"session": "morning"},
            id="alphapulse_morning",
            name="AlphaPulse 오전 리포트",
            max_instances=1,
            coalesce=True,  # 누적 실행 방지
        )

        # 오후 스케줄: 월~토 (0~5)
        self._scheduler.add_job(
            func=self._run_with_retry,
            trigger=CronTrigger(
                day_of_week="mon-sat",
                hour=evening_hour,
                minute=evening_minute,
                timezone=settings.timezone,
            ),
            kwargs={"session": "evening"},
            id="alphapulse_evening",
            name="AlphaPulse 오후 리포트",
            max_instances=1,
            coalesce=True,
        )

    def start(self) -> None:
        """스케줄러 시작 (블로킹)"""
        logger.info("=" * 50)
        logger.info("AlphaPulse 스케줄러 시작")
        logger.info(f"  타임존: {settings.timezone}")
        logger.info(f"  오전: 월~토 {settings.schedule_morning}")
        logger.info(f"  오후: 월~토 {settings.schedule_evening}")
        logger.info("=" * 50)

        try:
            self._scheduler.start()
        except KeyboardInterrupt:
            logger.info("스케줄러 종료 (Ctrl+C)")
            self._scheduler.shutdown(wait=False)

    def _run_with_retry(self, session: str = "auto", max_retries: int = 3) -> None:
        """파이프라인 실행 + 실패 시 재시도"""
        logger.info(f"[스케줄러] {session} 파이프라인 실행 시작")

        for attempt in range(1, max_retries + 1):
            try:
                success = self._pipeline_fn()
                status = "success" if success else "partial"
                self._write_health(session, status, attempt)
                logger.info(f"[스케줄러] 실행 완료: status={status}, 시도={attempt}")
                return
            except Exception as e:
                logger.error(
                    f"[스케줄러] 시도 {attempt}/{max_retries} 실패: {e}\n"
                    + traceback.format_exc()
                )
                if attempt < max_retries:
                    import time
                    wait = 60 * (2 ** (attempt - 1))  # 1분, 2분, 4분
                    logger.info(f"{wait}초 후 재시도...")
                    time.sleep(wait)

        self._write_health(session, "failed", max_retries)
        logger.error(f"[스케줄러] 최대 재시도 초과: session={session}")

    def _write_health(self, session: str, status: str, attempts: int) -> None:
        """헬스 체크 파일 갱신"""
        health = {
            "last_run": datetime.now().isoformat(),
            "session": session,
            "status": status,
            "attempts": attempts,
        }
        try:
            with open(self._health_file, "w", encoding="utf-8") as f:
                json.dump(health, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"헬스 파일 쓰기 실패: {e}")

    def read_health(self) -> dict:
        """마지막 실행 상태 조회"""
        try:
            if self._health_file.exists():
                with open(self._health_file, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"status": "unknown", "last_run": None}

    @staticmethod
    def _parse_time(time_str: str) -> tuple[int, int]:
        """'HH:MM' 형식 파싱"""
        try:
            h, m = time_str.strip().split(":")
            return int(h), int(m)
        except Exception:
            return 7, 0  # 기본값
