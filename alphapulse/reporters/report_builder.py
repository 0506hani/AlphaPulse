"""
AlphaPulse - 리포트 빌더

수집·분석된 데이터를 DailyReport 객체로 조립합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from alphapulse.storage.models import DailyReport, NewsGroup
from alphapulse.utils.logger import logger


import pytz

def determine_session() -> str:
    """현재 시각 기준으로 세션 결정"""
    hour = datetime.now(pytz.timezone('Asia/Seoul')).hour
    return "morning" if 5 <= hour < 14 else "evening"


class ReportBuilder:
    """DailyReport 객체 조립기"""

    def build(
        self,
        groups: List[NewsGroup],
        total_collected: int,
        total_after_dedup: int,
        session: str | None = None,
    ) -> DailyReport:
        """
        분석 완료된 그룹에서 DailyReport 생성.

        Args:
            groups: 종목 분석까지 완료된 NewsGroup 목록
            total_collected: 초기 수집 기사 수
            total_after_dedup: 중복 제거 후 기사 수
            session: "morning" | "evening" (None이면 자동 결정)

        Returns:
            완성된 DailyReport 객체
        """
        session = session or determine_session()
        report = DailyReport(
            session=session,
            groups=groups,
            total_articles_collected=total_collected,
            total_articles_after_dedup=total_after_dedup,
            status="success" if groups else "partial",
        )
        logger.info(
            f"리포트 생성 완료: ID={report.report_id}, "
            f"세션={session}, 그룹={len(groups)}개"
        )
        return report
