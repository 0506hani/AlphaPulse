"""
AlphaVerse - AlphaPulse 메인 진입점

사용법:
  python main.py run              # 즉시 파이프라인 1회 실행 (텔레그램 발송 포함)
  python main.py run --no-send    # 즉시 실행 (텔레그램 발송 제외, 테스트용)
  python main.py schedule         # 스케줄러 시작 (월~토 07:00, 18:00 자동 실행)
  python main.py status           # 마지막 실행 상태 조회
  python main.py test-telegram    # 텔레그램 봇 연결 테스트
"""

import argparse
import io
import json
import sys
from pathlib import Path

# Windows CP949 콘솔 환경에서 이모지/한글 출력 시 UnicodeEncodeError 방지
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from alphapulse.config import settings
from alphapulse.utils.logger import logger, setup_logger


def cmd_run(args: argparse.Namespace) -> None:
    """즉시 파이프라인 실행"""
    setup_logger(settings.log_dir_path)
    logger.info(f"AlphaPulse 즉시 실행 모드 (send={not args.no_send})")

    # 필수 환경변수 검증
    try:
        if not args.no_send:
            settings.validate_required()
        elif not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY 미설정 — LLM 호출 실패할 수 있습니다.")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    from alphapulse.pipeline import run_pipeline, run_weekly_pipeline
    
    if getattr(args, 'weekly', False):
        success = run_weekly_pipeline(send_telegram=not args.no_send)
    else:
        success = run_pipeline(
            session=args.session,
            send_telegram=not args.no_send,
        )
    sys.exit(0 if success else 1)


def cmd_schedule(args: argparse.Namespace) -> None:
    """스케줄러 시작"""
    setup_logger(settings.log_dir_path)
    logger.info("AlphaPulse 스케줄 모드 시작")

    try:
        settings.validate_required()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    from alphapulse.pipeline import run_pipeline
    from alphapulse.scheduler.job_scheduler import JobScheduler

    scheduler = JobScheduler(pipeline_fn=run_pipeline)
    scheduler.start()


def cmd_status(args: argparse.Namespace) -> None:
    """마지막 실행 상태 출력"""
    from alphapulse.pipeline import run_pipeline
    from alphapulse.scheduler.job_scheduler import JobScheduler

    # 헬스 파일 조회
    health_file = settings.cache_dir_path / "health.json"
    if health_file.exists():
        with open(health_file, encoding="utf-8") as f:
            health = json.load(f)
        print("\n=== AlphaPulse 마지막 실행 상태 ===")
        print(f"  실행 시각: {health.get('last_run', 'N/A')}")
        print(f"  세션:      {health.get('session', 'N/A')}")
        print(f"  상태:      {health.get('status', 'N/A')}")
        print(f"  시도 횟수: {health.get('attempts', 'N/A')}")
    else:
        print("\n아직 실행 기록이 없습니다.")

    # 최근 저장된 리포트 목록
    report_dir = settings.report_dir_path
    reports = sorted(report_dir.glob("*.json"), reverse=True)[:5]
    if reports:
        print("\n=== 최근 저장된 리포트 (최대 5개) ===")
        for r in reports:
            print(f"  {r.name}")
    else:
        print("\n저장된 리포트가 없습니다.")


def cmd_test_telegram(args: argparse.Namespace) -> None:
    """텔레그램 봇 연결 테스트"""
    setup_logger(settings.log_dir_path)

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print("❌ TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        sys.exit(1)

    from alphapulse.senders.telegram_sender import TelegramSender
    sender = TelegramSender()
    success = sender.test_connection()
    if success:
        print("✅ 텔레그램 봇 연결 성공!")
    else:
        print("❌ 텔레그램 봇 연결 실패. 로그를 확인하세요.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alphapulse",
        description="AlphaPulse - 텔레그램 자동 뉴스 요약 & 종목 분석 시스템",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run 커맨드
    run_parser = subparsers.add_parser("run", help="파이프라인 즉시 1회 실행")
    run_parser.add_argument(
        "--no-send", action="store_true", help="텔레그램 발송 제외 (테스트용)"
    )
    run_parser.add_argument(
        "--weekly", action="store_true", help="주간 요약 브리핑 모드로 실행"
    )
    run_parser.add_argument(
        "--session",
        choices=["morning", "evening"],
        default=None,
        help="세션 지정 (기본: 시각 자동 결정)",
    )
    run_parser.set_defaults(func=cmd_run)

    # schedule 커맨드
    schedule_parser = subparsers.add_parser("schedule", help="스케줄러 시작")
    schedule_parser.set_defaults(func=cmd_schedule)

    # status 커맨드
    status_parser = subparsers.add_parser("status", help="마지막 실행 상태 조회")
    status_parser.set_defaults(func=cmd_status)

    # test-telegram 커맨드
    test_parser = subparsers.add_parser("test-telegram", help="텔레그램 봇 연결 테스트")
    test_parser.set_defaults(func=cmd_test_telegram)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
