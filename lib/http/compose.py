"""compose 라우터 — POST /api/v1/compose 를 agent-compose(COMPOSE_UPSTREAM) 로 그대로 넘긴다.

agent-compose 규격 (src/api/compose.py):
  POST /api/v1/compose   편성 접수 — {v_id, query, stream_id, budget_sec, callback_url}
                         → {v_id, stream_id, search_id, code, result}  (code 0=접수 / -1=거절)
편성은 1~3분 걸려서 접수만 하고 바로 응답, 완료는 callback_url 로 통보된다.

여기서는 아무것도 해석하지 않는다. 경로만 config.COMPOSE_PATH 로, 본문·응답은 그대로.
"""
from fastapi import APIRouter, Request

import config
from lib.client import proxy

router = APIRouter(prefix="/v1", tags=["compose"])


@router.post("/compose")
def compose(request: Request):
    state = request.app.state
    return proxy.forward(state.http, state.compose_upstream, request, path=config.COMPOSE_PATH)
