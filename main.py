"""api-external 진입점 — 외부 공개 API 게이트웨이 (nginx reverse proxy 역할).

FastAPI app 생성 + 라우터 등록만. 로직은 lib/ 계층에 둠 (agent-stt 와 같은 레이아웃):
    lib/http      외부에 노출되는 라우터 (검증·인증·로깅) — 뒷단 호출은 client 로 넘긴다
    lib/client    뒷단 에이전트 호출 (agent-stt / agent-compose)
    lib/rdb       MariaDB 조회 (상태)

뒷단:
  ① agent-stt      config.STT_UPSTREAM
       외부 POST /api/v1/stt_svc  →  agent-stt POST /api/v1/pre_svc (최초 호출: 등록 → download → ffmpeg)
  ② agent-compose  config.COMPOSE_UPSTREAM
       외부 POST /api/v1/compose  →  agent-compose POST /api/v1/compose (편성 접수, 결과는 callback_url 로)
  upstream 은 nginx 처럼 서버 배열 (.env 의 *_UPSTREAM JSON 배열) — 라운드로빈으로 돌린다.
  ③ status_svc     GET /api/v1/status — 프록시 아님. DB(t_video_file) 에서 자막 공정 상태를 직접 조회 (lib/http/status_svc.py)
  ④ status_compose GET /api/v1/status_compose — 프록시 아님. DB(t_compose) 에서 편성 상태를 직접 조회 (lib/http/status_compose.py)

가공 없음 — 받은 요청을 그대로 넘기고 응답을 그대로 돌려준다. 요청/응답 본문은 로그에 찍는다.

전부 동기(def) — 핸들러는 FastAPI 가 스레드풀에서 돌린다. lifespan 없이 공유 리소스
(httpx.Client / 라운드로빈 이터레이터)는 여기서 1회 만들어 app.state 에 둔다.
(로깅 미들웨어 하나만 async — Starlette 가 미들웨어는 async 만 받는다.)

실행:  uv run uvicorn main:app --host 0.0.0.0 --port 19000 --reload
"""
import httpx
import uvicorn
from fastapi import FastAPI

import config
from lib.client import proxy
from lib.http import compose, http_util, status_compose, status_svc, stt_svc
from lib.log import get_logger

log = get_logger(__name__)

app = FastAPI(title="api_external", version="1.0")

# 공유 리소스 — 프로세스당 1회
app.state.http = httpx.Client(timeout=httpx.Timeout(config.PROXY_TIMEOUT_S))
app.state.stt_upstream = proxy.round_robin(config.STT_UPSTREAM)
app.state.compose_upstream = proxy.round_robin(config.COMPOSE_UPSTREAM)

app.include_router(stt_svc.router)
app.include_router(compose.router)
app.include_router(status_svc.router)
app.include_router(status_compose.router)
http_util.register(app)

log.info(f"api_external up: {config.HOST}:{config.PORT} "
         f"→ stt={config.STT_UPSTREAM} compose={config.COMPOSE_UPSTREAM}")


@app.get("/")
def root():
    return {"message": "hello world", "service": "api_external"}


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
