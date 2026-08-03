"""
AlphaPulse - 데이터 저장 파이프라인 (Repository)

DailyReport를 JSON 파일 및 SQLite DB에 저장합니다.
AlphaFuture, AlphaTrader 모듈이 이 저장소에서 데이터를 조회합니다.

파이프라인 데이터 구조:
- JSON: data/reports/YYYYMMDD_session.json (사람이 읽기 쉬운 전체 리포트)
- SQLite: data/alphapulse.db (구조화된 쿼리용)
  - reports: 리포트 메타데이터
  - news_groups: 그룹별 분석 결과
  - stock_recommendations: 종목 추천 이력
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from alphapulse.config import settings
from alphapulse.storage.models import DailyReport, NewsGroup, StockRecommend
from alphapulse.utils.logger import logger


class AlphaPulseRepository:
    """AlphaPulse 데이터 저장소 - JSON + SQLite 듀얼 파이프라인"""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        report_dir: Optional[Path] = None,
    ):
        self._db_path = db_path or settings.db_path_absolute
        self._report_dir = report_dir or settings.report_dir_path
        self._init_db()

    # ─────────────────────────────────────────────────────────────────
    # 공개 API (저장)
    # ─────────────────────────────────────────────────────────────────

    def save_report(self, report: DailyReport) -> None:
        """DailyReport를 JSON 파일 + SQLite DB에 모두 저장"""
        self._save_json(report)
        self._save_to_db(report)
        logger.info(f"리포트 저장 완료: {report.report_id}")

    # ─────────────────────────────────────────────────────────────────
    # 공개 API (조회) - AlphaFuture, AlphaTrader 연동용
    # ─────────────────────────────────────────────────────────────────

    def get_recent_reports(self, days: int = 7) -> List[dict]:
        """
        최근 N일간의 리포트 메타데이터 목록 반환.
        AlphaFuture에서 장기 트렌드 분석 원본 데이터로 활용.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM reports WHERE generated_at >= ? ORDER BY generated_at DESC",
                (cutoff,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_stock_recommendations(
        self,
        days: int = 30,
        market: Optional[str] = None,
        min_mentions: int = 1,
    ) -> List[dict]:
        """
        최근 N일간 언급된 종목 추천 이력 반환.
        AlphaTrader에서 기술적 분석 대상 종목 선정에 활용.

        Args:
            days: 조회 기간 (일)
            market: 시장 필터 ("KR" | "US" | None)
            min_mentions: 최소 언급 횟수 필터

        Returns:
            종목별 언급 횟수 및 이유 목록
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        query = """
            SELECT
                sr.ticker,
                sr.name,
                sr.market,
                COUNT(*) as mention_count,
                GROUP_CONCAT(sr.reason, ' | ') as reasons
            FROM stock_recommendations sr
            JOIN news_groups ng ON sr.group_id = ng.group_id
            JOIN reports r ON ng.report_id = r.report_id
            WHERE r.generated_at >= ?
        """
        params = [cutoff]
        if market:
            query += " AND sr.market = ?"
            params.append(market)
        query += " GROUP BY sr.ticker HAVING mention_count >= ? ORDER BY mention_count DESC"
        params.append(min_mentions)

        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_pipeline_data(self, report_id: str) -> Optional[dict]:
        """
        특정 리포트의 파이프라인 데이터 반환.
        AlphaFuture, AlphaTrader가 이 메서드로 데이터를 조회합니다.
        """
        json_files = list(self._report_dir.glob(f"*{report_id[:8]}*.json"))
        if json_files:
            try:
                with open(json_files[0], encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"JSON 파일 로드 실패: {e}")

        # DB 폴백
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT pipeline_data FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
            if row and row["pipeline_data"]:
                return json.loads(row["pipeline_data"])
        finally:
            conn.close()
        return None

    def get_weekly_news_groups(self, days: int = 6) -> List[dict]:
        """
        최근 N일간의 모든 뉴스 그룹 요약 데이터를 반환.
        주간 요약 브리핑 생성에 활용.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        query = """
            SELECT 
                ng.topic, 
                ng.summary, 
                ng.sentiment, 
                r.generated_at
            FROM news_groups ng
            JOIN reports r ON ng.report_id = r.report_id
            WHERE r.generated_at >= ?
            ORDER BY r.generated_at ASC
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, (cutoff,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_sector_trends(self, days: int = 14) -> dict:
        """
        최근 N일간 수혜/피해 업종 트렌드 반환.
        AlphaFuture 장기 산업 분석용.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self._get_connection()
        try:
            # news_groups의 beneficiary/harmed 업종 집계
            cursor = conn.execute(
                """
                SELECT ng.beneficiary_sectors, ng.harmed_sectors
                FROM news_groups ng
                JOIN reports r ON ng.report_id = r.report_id
                WHERE r.generated_at >= ?
                """,
                (cutoff,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        beneficiary_count: dict[str, int] = {}
        harmed_count: dict[str, int] = {}
        for row in rows:
            for sector in json.loads(row["beneficiary_sectors"] or "[]"):
                beneficiary_count[sector] = beneficiary_count.get(sector, 0) + 1
            for sector in json.loads(row["harmed_sectors"] or "[]"):
                harmed_count[sector] = harmed_count.get(sector, 0) + 1

        return {
            "period_days": days,
            "beneficiary": sorted(beneficiary_count.items(), key=lambda x: -x[1]),
            "harmed": sorted(harmed_count.items(), key=lambda x: -x[1]),
        }

    # ─────────────────────────────────────────────────────────────────
    # 내부 구현
    # ─────────────────────────────────────────────────────────────────

    def _save_json(self, report: DailyReport) -> None:
        """DailyReport를 JSON 파일로 저장"""
        filename = (
            f"{report.generated_at.strftime('%Y%m%d')}_{report.session}.json"
        )
        filepath = self._report_dir / filename

        # 전체 리포트 + 파이프라인 데이터
        output = {
            "report": report.model_dump(mode="json"),
            "pipeline": report.to_pipeline_dict(),
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        logger.debug(f"JSON 저장: {filepath}")

    def _save_to_db(self, report: DailyReport) -> None:
        """DailyReport를 SQLite DB에 저장"""
        conn = self._get_connection()
        try:
            pipeline_data = json.dumps(
                report.to_pipeline_dict(), ensure_ascii=False, default=str
            )
            # reports 테이블
            conn.execute(
                """
                INSERT OR REPLACE INTO reports
                (report_id, generated_at, session, total_articles_collected,
                 total_articles_after_dedup, status, pipeline_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.generated_at.isoformat(),
                    report.session,
                    report.total_articles_collected,
                    report.total_articles_after_dedup,
                    report.status,
                    pipeline_data,
                ),
            )

            # news_groups + stock_recommendations 테이블
            for group in report.groups:
                self._save_group(conn, group, report.report_id)

            conn.commit()
            logger.debug("SQLite 저장 완료")
        except Exception as e:
            conn.rollback()
            logger.error(f"SQLite 저장 실패: {e}")
            raise
        finally:
            conn.close()

    def _save_group(
        self, conn: sqlite3.Connection, group: NewsGroup, report_id: str
    ) -> None:
        """단일 뉴스 그룹을 DB에 저장"""
        conn.execute(
            """
            INSERT OR REPLACE INTO news_groups
            (group_id, report_id, topic, summary, sentiment,
             beneficiary_sectors, harmed_sectors, top_links)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group.group_id,
                report_id,
                group.topic,
                group.summary,
                group.sentiment,
                json.dumps(group.beneficiary_sectors, ensure_ascii=False),
                json.dumps(group.harmed_sectors, ensure_ascii=False),
                json.dumps(group.top_links),
            ),
        )

        # 종목 추천 저장
        all_stocks = [
            (s, "KR") for s in group.korean_stocks
        ] + [
            (s, "US") for s in group.us_stocks
        ]
        for stock, market in all_stocks:
            conn.execute(
                """
                INSERT OR IGNORE INTO stock_recommendations
                (group_id, ticker, name, market, reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group.group_id, stock.ticker, stock.name, market, stock.reason),
            )

    def _init_db(self) -> None:
        """SQLite 스키마 초기화"""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    session TEXT NOT NULL,
                    total_articles_collected INTEGER DEFAULT 0,
                    total_articles_after_dedup INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'success',
                    pipeline_data TEXT
                );

                CREATE TABLE IF NOT EXISTS news_groups (
                    group_id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    summary TEXT,
                    sentiment TEXT DEFAULT 'neutral',
                    beneficiary_sectors TEXT DEFAULT '[]',
                    harmed_sectors TEXT DEFAULT '[]',
                    top_links TEXT DEFAULT '[]',
                    FOREIGN KEY (report_id) REFERENCES reports(report_id)
                );

                CREATE TABLE IF NOT EXISTS stock_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    reason TEXT,
                    FOREIGN KEY (group_id) REFERENCES news_groups(group_id),
                    UNIQUE(group_id, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_reports_generated_at
                    ON reports(generated_at);
                CREATE INDEX IF NOT EXISTS idx_stock_reco_ticker
                    ON stock_recommendations(ticker);
                CREATE INDEX IF NOT EXISTS idx_stock_reco_market
                    ON stock_recommendations(market);
            """)
            conn.commit()
            logger.debug("SQLite 스키마 초기화 완료")
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """SQLite 연결 반환 (Row factory 설정)"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn
