"""
AlphaPulse - 핵심 파이프라인

뉴스 수집 → 중복 제거 → 그룹화/요약 → 종목 분석 → 리포트 생성 → 발송 → 저장
전체 파이프라인을 순서대로 실행하는 오케스트레이터입니다.
"""

from __future__ import annotations

import time
import pytz
import traceback
from datetime import datetime
from typing import Optional

from alphapulse.analyzers.llm_factory import get_llm
from alphapulse.analyzers.news_grouper import NewsGrouper
from alphapulse.analyzers.stock_analyzer import StockAnalyzer
from alphapulse.collectors.collector_factory import get_collectors
from alphapulse.config import settings
from alphapulse.reporters.report_builder import ReportBuilder
from alphapulse.senders.telegram_sender import TelegramSender
from alphapulse.storage.repository import AlphaPulseRepository
from alphapulse.utils.deduplicator import Deduplicator
from alphapulse.utils.logger import logger, setup_logger


def run_pipeline(session: Optional[str] = None, send_telegram: bool = True) -> bool:
    """
    AlphaPulse 전체 파이프라인 실행.

    Args:
        session: "morning" | "evening" | None (자동 결정)
        send_telegram: 텔레그램 발송 여부 (테스트 시 False)

    Returns:
        성공 여부
    """
    start_time = datetime.now(pytz.timezone('Asia/Seoul'))
    logger.info("=" * 60)
    logger.info("AlphaPulse 파이프라인 시작")
    logger.info(f"  시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  세션: {session or '자동'}")
    logger.info("=" * 60)

    try:
        # ── Step 1: 뉴스 수집 ─────────────────────────────────────────
        logger.info("[Step 1] 뉴스 수집 시작")
        collectors = get_collectors()
        all_articles = []
        for collector in collectors:
            logger.info(f"  수집기: {collector.source_name}")
            articles = collector.collect()
            all_articles.extend(articles)
            logger.info(f"  → {len(articles)}개 수집")

        total_collected = len(all_articles)
        logger.info(f"[Step 1] 완료: 총 {total_collected}개 수집")

        if total_collected == 0:
            logger.warning("수집된 기사가 없습니다. 파이프라인 중단.")
            return False

        # ── Step 2: 중복 제거 ──────────────────────────────────────────
        logger.info("[Step 2] 중복 제거 시작")
        deduplicator = Deduplicator(similarity_threshold=0.80)
        unique_articles = deduplicator.deduplicate(all_articles)

        # 최대 기사 수 제한
        if len(unique_articles) > settings.max_articles:
            unique_articles = unique_articles[: settings.max_articles]
            logger.info(f"  최대 {settings.max_articles}개로 제한")

        total_after_dedup = len(unique_articles)
        logger.info(f"[Step 2] 완료: {total_collected} → {total_after_dedup}개")

        # ── Step 3: LLM 초기화 ────────────────────────────────────────
        logger.info("[Step 3] LLM 초기화")
        llm = get_llm()
        logger.info(f"  LLM: {llm.provider_name}")

        # ── Step 4: 뉴스 그룹화 & 요약 ────────────────────────────────
        logger.info("[Step 4] 뉴스 그룹화 & 요약 시작")
        grouper = NewsGrouper(llm=llm, num_groups=settings.num_groups)
        groups = grouper.group_and_summarize(unique_articles)
        logger.info(f"[Step 4] 완료: {len(groups)}개 그룹 생성")

        if not groups:
            logger.warning("생성된 뉴스 그룹이 없습니다.")
            return False

        # ── Step 5: 종목 영향 분석 ────────────────────────────────────
        logger.info("[Step 5] 종목 영향 분석 시작")
        analyzer = StockAnalyzer(llm=llm)
        analyzed_groups = analyzer.analyze_groups(groups)
        logger.info(f"[Step 5] 완료: {len(analyzed_groups)}개 그룹 분석")

        # ── Step 6: 리포트 생성 ────────────────────────────────────────
        logger.info("[Step 6] 리포트 생성")
        builder = ReportBuilder()
        report = builder.build(
            groups=analyzed_groups,
            total_collected=total_collected,
            total_after_dedup=total_after_dedup,
            session=session,
        )

        # ── Step 7: 데이터 저장 ────────────────────────────────────────
        logger.info("[Step 7] 데이터 저장")
        repo = AlphaPulseRepository()
        repo.save_report(report)

        # ── Step 8: 텔레그램 발송 ─────────────────────────────────────
        if send_telegram:
            logger.info("[Step 8] 텔레그램 발송")
            sender = TelegramSender()
            success = sender.send_report(report)
            if not success:
                logger.warning("텔레그램 발송 부분 실패 (리포트는 저장됨)")
        else:
            logger.info("[Step 8] 텔레그램 발송 건너뜀 (--no-send 모드)")
            success = True

        # ── 완료 ──────────────────────────────────────────────────────
        elapsed = (datetime.now(pytz.timezone('Asia/Seoul')) - start_time).total_seconds()
        logger.info("=" * 60)
        logger.info(f"AlphaPulse 파이프라인 완료: {elapsed:.1f}초 소요")
        logger.info(f"  리포트 ID: {report.report_id}")
        logger.info(f"  그룹 수: {len(report.groups)}개")
        logger.info("=" * 60)
        return success

    except Exception as e:
        logger.error(f"파이프라인 실패: {e}\n{traceback.format_exc()}")
        return False

def run_weekly_pipeline(send_telegram: bool = True) -> bool:
    """
    AlphaPulse 주간 요약 파이프라인 실행.
    """
    start_time = datetime.now(pytz.timezone('Asia/Seoul'))
    logger.info("=" * 60)
    logger.info("AlphaPulse 주간 파이프라인 시작")
    logger.info(f"  시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        repo = AlphaPulseRepository()
        weekly_data = repo.get_weekly_news_groups(days=6)
        
        if not weekly_data:
            logger.warning("주간 요약을 위한 뉴스 데이터가 없습니다.")
            return False

        logger.info(f"[Step 1] 주간 데이터 수집 완료: {len(weekly_data)}개 뉴스 그룹")
        
        llm = get_llm()
        from alphapulse.analyzers.weekly_summarizer import WeeklySummarizer
        summarizer = WeeklySummarizer(llm=llm)
        
        logger.info("[Step 2] 주간 요약 생성 시작")
        groups = summarizer.summarize_weekly(weekly_data)
        
        if not groups:
            logger.warning("주간 요약 생성 실패.")
            return False
            
        logger.info("[Step 3] 리포트 생성")
        builder = ReportBuilder()
        report = builder.build(
            groups=groups,
            total_collected=len(weekly_data),
            total_after_dedup=len(weekly_data),
            session="weekly",
        )
        
        logger.info("[Step 4] 데이터 저장")
        repo.save_report(report)
        
        if send_telegram:
            logger.info("[Step 5] 텔레그램 발송")
            sender = TelegramSender()
            success = sender.send_report(report)
        else:
            success = True

        elapsed = (datetime.now(pytz.timezone('Asia/Seoul')) - start_time).total_seconds()
        logger.info("=" * 60)
        logger.info(f"AlphaPulse 주간 파이프라인 완료: {elapsed:.1f}초 소요")
        logger.info("=" * 60)
        return success

    except Exception as e:
        logger.error(f"주간 파이프라인 실패: {e}\n{traceback.format_exc()}")
        return False
