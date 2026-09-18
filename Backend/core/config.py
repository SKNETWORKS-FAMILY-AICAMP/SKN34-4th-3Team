import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


BACKEND_ROOT = Path(__file__).resolve().parent.parent
_load_env_file(BACKEND_ROOT.parent / ".env")
_load_env_file(BACKEND_ROOT / ".env")

APP_NAME = "청년창업 지원 플랫폼 API"
APP_VERSION = "0.2.0"
APP_DESCRIPTION = """
청년·1인 창업자 맞춤형 행정·재정 지원 플랫폼의 REST API입니다.

- **DB**: Postgres(`DATABASE_URL`)를 직접 SELECT/INSERT/UPDATE 합니다. 연결이 안 되면 SQLite로 폴백합니다. `policies`/`rag_documents`를 TRUNCATE하지 않습니다.
- **LLM**: `LLM_API_URL`(기본 `http://127.0.0.1:8001`)이 살아 있으면 RAG/OCR/요약을 호출하고, 실패 시 목업으로 내려갑니다.
- Rule 판정(세액감면·정책 자격)은 Backend에 두고, LLM은 근거 설명만 붙입니다.

**데모 계정:** `demo@demo.com` / `demo123`  
**관리자:** `admin@demo.com` / `admin123`
"""
OPENAPI_TAGS = [
    {"name": "상태", "description": "서버·DB·LLM 연결 여부"},
    {"name": "인증", "description": "회원가입, 로그인, 로그아웃"},
    {"name": "사용자", "description": "개인정보·사업자 온보딩 프로필"},
    {"name": "상담", "description": "카테고리별 챗봇(RAG 우선, 실패 시 목업)"},
    {"name": "캘린더", "description": "세금·지원금 통합 일정"},
    {"name": "세무", "description": "세금 정보, 리마인더, 세액감면 Rule + LLM 근거"},
    {"name": "지출", "description": "영수증 OCR(LLM)과 경비 안내"},
    {"name": "지원정책", "description": "정책 검색, 추천, 자격 확인, 공고 요약, 관심 저장"},
    {"name": "관리자", "description": "관리자 로그인 및 데이터 관리"},
    {"name": "알림", "description": "앱 알림함, 메일 대기열, 브라우저 푸시"},
]
TOKEN_PREFIX = "tok_"
TOKEN_SECRET = os.getenv("TOKEN_SECRET")
if not TOKEN_SECRET:
    raise RuntimeError('TOKEN_SECRET 미설정. 환경변수 확인')
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))
# 조세특례제한법 제6조 창업중소기업 세액감면의 최고 감면율(%).
# DB에서 집계할 근거가 없어 법령 기반 고정값으로 둔다. GET /stats가 사용한다.
MAX_REDUCTION_RATE = 100

DEMO_EMAIL = "demo@demo.com"
DEMO_PASSWORD = "demo123"
ADMIN_EMAIL = "admin@demo.com"
ADMIN_PASSWORD = "admin123"

DATA_DIR = BACKEND_ROOT / "data"
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(DATA_DIR / "app.db")))
LLM_API_URL = os.getenv("LLM_API_URL", "http://127.0.0.1:8001").rstrip("/")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "25"))

# 엔드포인트별 호출 제한(초). Docs/Design/LLM_API_SPEC_V1.md 9절.
# /rag/chat만 카테고리별로 갈린다. LLM의 _route_for_category가 tax·expense를 tax 멀티홉으로
# 강제하므로 실측값 120초를 쓴다. policy는 대화 이력이 있으면 문맥 복원 모델 호출이
# 한 번 더 붙으므로 기존 계약값 30초에서 그만큼 올린다.
# LLM_TIMEOUT_SECONDS는 명시 제한이 없는 호출의 기본값으로만 남는다.
LLM_TIMEOUT_READY = float(os.getenv("LLM_TIMEOUT_READY", "3"))
LLM_TIMEOUT_CHAT_POLICY = float(os.getenv("LLM_TIMEOUT_CHAT_POLICY", "45"))
LLM_TIMEOUT_CHAT_TAX = float(os.getenv("LLM_TIMEOUT_CHAT_TAX", "120"))
LLM_TIMEOUT_LEGAL_BASIS = float(os.getenv("LLM_TIMEOUT_LEGAL_BASIS", "30"))
LLM_TIMEOUT_DEDUCTIBILITY = float(os.getenv("LLM_TIMEOUT_DEDUCTIBILITY", "30"))
LLM_TIMEOUT_SUMMARIZE = float(os.getenv("LLM_TIMEOUT_SUMMARIZE", "45"))
LLM_TIMEOUT_OCR = float(os.getenv("LLM_TIMEOUT_OCR", "60"))
LLM_TIMEOUT_REINDEX = float(os.getenv("LLM_TIMEOUT_REINDEX", "180"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin1234@127.0.0.1:5432/startup_platform")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@skn34.local")
