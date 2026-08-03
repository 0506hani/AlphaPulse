# AlphaVerse - AlphaPulse 🚀

> **투자 의사결정 지원 플랫폼 AlphaVerse의 첫 번째 모듈**
>
> 텔레그램 기반 자동 뉴스 요약 및 종목 분석 리포트 시스템

---

## 📋 주요 기능

- **뉴스 자동 수집**: 국내외 주요 금융/경제 RSS 피드에서 최대 200개 뉴스 수집
- **AI 그룹화 & 요약**: TF-IDF 클러스터링 + Gemini AI로 5~10개 핵심 주제 요약
- **종목 영향 분석**: 수혜/피해 업종 + 국내·미국 관련 종목 3~5개 자동 분석
- **텔레그램 자동 발송**: 인라인 버튼(원본 링크) 포함 깔끔한 리포트 발송
- **자동 스케줄링**: 월~토 오전 7시, 오후 6시 1일 2회 자동 실행
- **데이터 파이프라인**: JSON + SQLite 이중 저장 (AlphaFuture·AlphaTrader 연동용)

---

## 🏗️ 아키텍처

```
[RSS 수집] → [중복 제거] → [TF-IDF 클러스터링] → [Gemini 요약]
                                                          ↓
                                                   [종목 분석]
                                                          ↓
                                              [텔레그램 발송] ← [리포트 생성]
                                                          ↓
                                              [JSON + SQLite 저장]
                                         (AlphaFuture·AlphaTrader 연동)
```

---

## ⚡ 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
copy .env.example .env
```

`.env` 파일을 열어 아래 값을 입력하세요:

```dotenv
# 필수
GEMINI_API_KEY=your_gemini_api_key    # Google AI Studio에서 발급
TELEGRAM_BOT_TOKEN=your_bot_token    # @BotFather에서 발급
TELEGRAM_CHAT_ID=your_chat_id        # 채널/그룹 ID (-100으로 시작)
```

> **Gemini API 키 발급**: [Google AI Studio](https://aistudio.google.com/app/apikey)
>
> **텔레그램 봇 생성**: [@BotFather](https://t.me/BotFather)에서 `/newbot` 명령 사용

### 3. 텔레그램 연결 테스트

```bash
python main.py test-telegram
```

### 4. 즉시 실행 (테스트)

```bash
# 텔레그램 발송 없이 테스트
python main.py run --no-send

# 실제 발송 포함 전체 실행
python main.py run
```

### 5. 스케줄러 시작 (상시 실행)

```bash
python main.py schedule
```

---

## 📁 폴더 구조

```
AlphaVerse/
├── main.py                         # CLI 진입점
├── requirements.txt
├── .env.example                    # 환경변수 템플릿
│
├── alphapulse/
│   ├── config.py                   # 설정 관리
│   ├── pipeline.py                 # 전체 파이프라인 오케스트레이터
│   │
│   ├── collectors/                 # 뉴스 수집 레이어
│   │   ├── base_collector.py       # 추상 인터페이스
│   │   ├── rss_collector.py        # RSS 피드 수집기
│   │   └── collector_factory.py
│   │
│   ├── analyzers/                  # AI 분석 레이어
│   │   ├── base_llm.py             # LLM 추상 인터페이스
│   │   ├── gemini_llm.py           # Google Gemini 구현
│   │   ├── llm_factory.py          # LLM 팩토리
│   │   ├── news_grouper.py         # 뉴스 그룹화 & 요약
│   │   └── stock_analyzer.py      # 종목 영향 분석
│   │
│   ├── reporters/                  # 리포트 생성 레이어
│   │   ├── report_builder.py
│   │   └── formatter.py            # 텔레그램 MarkdownV2 포맷터
│   │
│   ├── senders/                    # 발송 레이어
│   │   ├── base_sender.py          # 추상 인터페이스
│   │   └── telegram_sender.py
│   │
│   ├── scheduler/
│   │   └── job_scheduler.py        # APScheduler 스케줄러
│   │
│   ├── storage/
│   │   ├── models.py               # Pydantic 데이터 모델
│   │   └── repository.py           # JSON + SQLite 저장소
│   │
│   └── utils/
│       ├── logger.py
│       └── deduplicator.py
│
├── data/
│   ├── reports/                    # 저장된 리포트 JSON
│   └── cache/                      # 헬스체크 파일
│
└── tests/
    ├── test_collectors.py
    ├── test_analyzers.py
    └── test_senders.py
```

---

## 🛠️ CLI 명령어

| 명령어 | 설명 |
|---|---|
| `python main.py run` | 파이프라인 즉시 1회 실행 (텔레그램 발송 포함) |
| `python main.py run --no-send` | 파이프라인 실행 (텔레그램 발송 제외, 테스트용) |
| `python main.py run --session morning` | 오전 세션으로 강제 실행 |
| `python main.py schedule` | 스케줄러 시작 (Ctrl+C로 종료) |
| `python main.py status` | 마지막 실행 상태 및 저장된 리포트 목록 조회 |
| `python main.py test-telegram` | 텔레그램 봇 연결 테스트 |

---

## 🧪 테스트 실행

```bash
# 전체 테스트
pytest tests/ -v

# 개별 모듈 테스트
pytest tests/test_collectors.py -v
pytest tests/test_analyzers.py -v
pytest tests/test_senders.py -v
```

---

## 📊 텔레그램 리포트 예시

```
🌅 AlphaPulse 오전 리포트
📅 2026-07-24 (목) 07:00 KST
📊 총 145개 기사 수집 → 7개 핵심 주제 분석
━━━━━━━━━━━━━━━━━━━━

📈 1. 연준 금리 동결 발표
━━━━━━━━━━━━━━━━━━━━
📌 핵심 요약
연준이 7월 FOMC에서 기준금리를 5.25~5.5%로 동결 결정했습니다.
성장세 유지와 인플레이션 목표 달성을 위한 결정으로...

🟢 수혜 업종: 기술주, 성장주
   금리 동결로 성장주 밸류에이션 부담 완화
🔴 피해 업종: 은행, 보험
   이자 수익 개선 기대감 약화

🇰🇷 관련 종목
  • 삼성전자 (005930)
    외국인 수급 개선 기대
  • 카카오 (035720)
    성장주 밸류에이션 부담 완화

🇺🇸 관련 종목
  • NVIDIA (NVDA)
    AI 투자 지속 수혜
  • Apple (AAPL)
    성장주 선호 환경

[📰 원문1 보기] [📰 원문2 보기]
```

---

## 🔗 향후 모듈 연동 (AlphaFuture & AlphaTrader)

AlphaPulse가 저장하는 데이터를 활용하는 방법:

```python
from alphapulse.storage.repository import AlphaPulseRepository

repo = AlphaPulseRepository()

# 최근 7일 리포트 목록 (AlphaFuture 장기 트렌드 분석용)
recent = repo.get_recent_reports(days=7)

# 최근 30일 반복 언급 종목 (AlphaTrader 기술적 분석 대상 선정용)
hot_stocks = repo.get_stock_recommendations(days=30, min_mentions=3)

# 업종 트렌드 분석 (AlphaFuture 산업 분석용)
trends = repo.get_sector_trends(days=14)
```

---

## ⚠️ 주의사항

- 본 리포트는 AI가 생성한 정보이며, **투자 조언이 아닙니다**.
- Gemini API 무료 티어 한도를 고려하여 1일 2회 스케줄이 설계되었습니다.
- 로컬 PC 운영 시 스케줄러 실행 시간에 PC가 켜져 있어야 합니다.

---

*AlphaVerse - AlphaPulse v0.1.0*
