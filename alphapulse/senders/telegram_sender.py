"""
AlphaPulse - 텔레그램 봇 발송기

python-telegram-bot 라이브러리를 사용하여 분석 리포트를 텔레그램 채널/그룹에 발송합니다.
인라인 버튼으로 원본 기사 링크를 제공합니다.
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional, Tuple

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from alphapulse.config import settings
from alphapulse.reporters.formatter import TelegramFormatter
from alphapulse.senders.base_sender import BaseSender
from alphapulse.storage.models import DailyReport
from alphapulse.utils.logger import logger


class TelegramSender(BaseSender):
    """텔레그램 봇 발송기"""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        message_interval: float = 0.8,
    ):
        """
        Args:
            bot_token: 텔레그램 봇 토큰 (None이면 settings에서 로드)
            chat_id: 발송 대상 채팅 ID (None이면 settings에서 로드)
            message_interval: 메시지 간 발송 간격 (초) - Rate Limit 방지
        """
        self._bot_token = bot_token or settings.telegram_bot_token
        if chat_id:
            self._chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()]
        else:
            self._chat_ids = settings.telegram_chat_id_list
        self._message_interval = message_interval
        self._formatter = TelegramFormatter()
        self._bot = Bot(token=self._bot_token)

    @property
    def sender_name(self) -> str:
        return "Telegram Bot"

    def send_report(self, report: DailyReport) -> bool:
        """
        DailyReport를 텔레그램으로 발송합니다.

        Returns:
            전체 발송 성공 여부
        """
        logger.info(f"텔레그램 발송 시작: 리포트 ID={report.report_id}")

        # 동기 실행을 위한 asyncio event loop
        try:
            success = asyncio.run(self._send_report_async(report))
            if success:
                logger.info("텔레그램 발송 완료")
            else:
                logger.error("텔레그램 발송 부분 실패")
            return success
        except Exception as e:
            logger.error(f"텔레그램 발송 실패: {e}")
            return False

    async def _send_report_async(self, report: DailyReport) -> bool:
        """비동기 리포트 발송"""
        messages = self._formatter.format_report(report)
        success_count = 0

        for chat_id in self._chat_ids:
            for idx, (text, link_urls) in enumerate(messages):
                try:
                    # 인라인 버튼 생성 (원본 링크)
                    reply_markup = None
                    if link_urls:
                        buttons = [
                            InlineKeyboardButton(
                                text=f"📰 원문{i + 1} 보기",
                                url=url,
                            )
                            for i, url in enumerate(link_urls[:2])
                        ]
                        reply_markup = InlineKeyboardMarkup([buttons])

                    await self._bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=reply_markup,
                        disable_web_page_preview=False,
                    )
                    success_count += 1
                    logger.debug(f"[{chat_id}] 메시지 {idx + 1}/{len(messages)} 발송 성공")

                    # 메시지 간 간격
                    if idx < len(messages) - 1:
                        await asyncio.sleep(self._message_interval)

                except RetryAfter as e:
                    # Rate Limit: 요청된 시간만큼 대기 후 재시도
                    wait_time = e.retry_after + 1
                    logger.warning(f"[{chat_id}] Rate Limit: {wait_time}초 대기 후 재시도")
                    await asyncio.sleep(wait_time)
                    try:
                        await self._bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            parse_mode=ParseMode.MARKDOWN_V2,
                            reply_markup=reply_markup,
                        )
                        success_count += 1
                    except Exception as retry_e:
                        logger.error(f"[{chat_id}] 재시도 실패: {retry_e}")

                except TelegramError as e:
                    logger.error(f"[{chat_id}] 메시지 {idx + 1} 발송 실패 (TelegramError): {e}")
                    # MarkdownV2 파싱 오류 시 일반 텍스트로 재시도
                    if "parse" in str(e).lower() or "can't parse" in str(e).lower():
                        try:
                            plain_text = self._strip_markdown(text)
                            await self._bot.send_message(
                                chat_id=chat_id,
                                text=plain_text,
                                reply_markup=reply_markup,
                            )
                            success_count += 1
                            logger.info(f"[{chat_id}] 메시지 {idx + 1} 일반 텍스트로 재발송 성공")
                        except Exception as plain_e:
                            logger.error(f"[{chat_id}] 일반 텍스트 재발송도 실패: {plain_e}")

                except Exception as e:
                    logger.error(f"[{chat_id}] 메시지 {idx + 1} 예외: {e}")

        return success_count == len(messages) * len(self._chat_ids)

    def _strip_markdown(self, text: str) -> str:
        """MarkdownV2 이스케이프 제거 (폴백용)"""
        import re
        # 이스케이프 문자 제거
        text = re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!])", r"\1", text)
        # 볼드/이탤릭 마커 제거
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        return text

    async def send_test_message(self) -> bool:
        """연결 테스트용 메시지 발송"""
        all_success = True
        for chat_id in self._chat_ids:
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text="✅ AlphaPulse 봇 연결 테스트 성공!",
                )
                logger.info(f"[{chat_id}] 테스트 메시지 발송 성공")
            except Exception as e:
                logger.error(f"[{chat_id}] 테스트 메시지 발송 실패: {e}")
                all_success = False
        return all_success

    def test_connection(self) -> bool:
        """동기 연결 테스트"""
        return asyncio.run(self.send_test_message())
