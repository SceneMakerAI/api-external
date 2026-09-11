import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOG_DIR = Path("/usr/service/logs/scenemaker/api_external")
LOG_FILE = LOG_DIR / "api_external.log"

# ── 서버 (FastAPI) — 외부 노출 게이트웨이
HOST = os.getenv("HOST")
PORT = int(os.getenv("PORT"))

# ── MariaDB — 처리 상태 조회 (t_video_file). agent-stt 와 같은 DB
RDB_HOST = os.getenv("RDB_HOST")
RDB_PORT = int(os.getenv("RDB_PORT"))
RDB_USER = os.getenv("RDB_USER")
RDB_PW = os.getenv("RDB_PW")
RDB_NAME = os.getenv("RDB_NAME")


# ── 뒷단 upstream — nginx upstream 블록처럼 서버 배열. .env 에 JSON 배열 그대로 쓴다.
#      STT_UPSTREAM=["http://127.0.0.1:19010", "http://10.0.0.2:19010"]

# ① agent-stt — 자막 공정
STT_UPSTREAM: list[str] = json.loads(os.getenv("STT_UPSTREAM"))
STT_PATH_PRE = "/api/v1/pre_svc"      # 외부 /api/v1/stt_svc → agent-stt 진입점 (등록 → download → ffmpeg). 뒷단 경로 바뀌면 여기만.

# ② agent-compose — 질의 기반 하이라이트 편성
COMPOSE_UPSTREAM: list[str] = json.loads(os.getenv("COMPOSE_UPSTREAM"))
COMPOSE_PATH = "/api/v1/compose"      # 외부 POST /api/v1/compose (편성 접수) → agent-compose. 뒷단 경로 바뀌면 여기만.


# ── 프록시 타임아웃(초) — 뒷단은 접수 즉시 응답하므로 길게 잡을 이유가 없다.
#   단, pre_svc 는 ffmpeg 추출이 끝날 때까지 응답을 잡고 있으므로 넉넉히.
PROXY_TIMEOUT_S = 60 * 20
