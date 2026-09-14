"""compose 라우터 — POST /api/v1/compose 를 agent-compose(COMPOSE_UPSTREAM) 로 그대로 넘긴다.

agent-compose 규격 (src/api/compose.py):
  POST /api/v1/compose   편성 접수 — {v_id, query, stream_id, budget_sec, callback_url}
                         → {v_id, stream_id, search_id, code, result}  (code 0=접수 / -1=거절)
편성은 1~3분 걸려서 접수만 하고 바로 응답, 완료는 callback_url 로 통보된다.

여기서는 아무것도 해석하지 않는다. 경로만 config.COMPOSE_PATH 로, 본문·응답은 그대로.

넘기기 전에 하나만 본다 — t_compose 에 편성 중 status_code 를 가진 행이 _MAX_BUSY 건 이상이면
뒷단에 안 넘기고 409 로 거절한다 (범위·개수는 아래에 하드코딩). stt_svc.py 와 같은 구조인데
편성은 동시에 여러 건 돌 수 있어서 '하나라도' 가 아니라 '개수' 로 본다.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from lib.client import proxy
from lib.log import get_logger
from lib.rdb import t_compose

router = APIRouter(prefix="/api/v1", tags=["compose"])
log = get_logger(__name__)

# 편성 중으로 보는 status_code 범위 (초과, 미만) — 4020 PLAN ~ 4050 RENDER. 정확한 값은 추후 확정. 지금은 하드코딩.
#   4000 OK / 4001 EMPTY(정상 종결) / 4900·4950 실패는 뺀다. select_composes 의 where_query 로 그대로 붙는 SQL 조각 (c = t_compose 별칭).
_BUSY_WHERE = "AND (c.status_code > 4001 AND c.status_code < 4090)"
# 동시에 돌릴 수 있는 편성 수 — 편성 중인 행이 이 수 이상이면 거절. 정확한 값은 추후 확정. 지금은 하드코딩.
_MAX_BUSY = 3


@router.post("/search_svc")
@router.post("/search_svc/{rest:path}")      # /search_svc 뒤에 뭐가 붙어도 받는다 — rest 는 인자로 안 받아 무시되고, 뒷단엔 path= 로 준 COMPOSE_PATH 만 간다
def compose(request: Request):
    state = request.app.state

    # 편성 중인 행이 _MAX_BUSY 건 이상이면 뒷단에 안 넘기고 거절
    busy = t_compose.select_composes(where_query=_BUSY_WHERE)
    if len(busy) >= _MAX_BUSY:
        b = busy[0]
        log.warning(f"compose 거절: 편성 중 {len(busy)}건 (최대 {_MAX_BUSY}) — v_id={b['v_id']} search_id={b['search_id']!r} "
                    f"status_code={b['status_code']}({b['status_name']})")
        return JSONResponse(status_code=409, content={
            "v_id": b["v_id"], "stream_id": b["stream_id"], "search_id": b["search_id"],
            "code": -1, "result": "fail",
            "status_code": b["status_code"], "status_name": b["status_name"],
        })

    return proxy.forward(state.http, state.compose_upstream, request, path=config.COMPOSE_PATH)
