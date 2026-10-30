"""compose 라우터 — 편성 접수를 agent-compose 로 넘긴다 (본문 그대로, 경로만 config.COMPOSE_PATH).

POST /api/v1/compose
  요청  {v_g_id, videos[{v_id, stream_ids}], query, budget_sec, callback_url}
        videos 없으면 그룹 전체, stream_ids 없으면 그 영상의 파일 전부
  응답  {comp_id, code, result}   code 0 접수 / -1 거절. 완료는 callback_url 로 통보
  409   편성 중 행이 _MAX_BUSY 건 이상이면 뒷단에 안 넘기고 거절
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

import config
from lib.client import proxy
from lib.http import schema_resp
from lib.log import get_logger
from lib.rdb import t_compose

router = APIRouter(prefix="/api/v1", tags=["compose"])
log = get_logger(__name__)

# 편성 중으로 보는 status_code 범위 (초과, 미만) — 4020 PLAN ~ 4050 RENDER. 정확한 값은 추후 확정. 지금은 하드코딩.
#   4000 OK / 4001 EMPTY(정상 종결) / 4900·4950 실패는 뺀다. select_composes 의 where_query 로 그대로 붙는 SQL 조각 (c = t_compose 별칭).
_BUSY_WHERE = "AND (c.status_code > 4001 AND c.status_code < 4090)"
# 동시에 돌릴 수 있는 편성 수 — 편성 중인 행이 이 수 이상이면 거절. 정확한 값은 추후 확정. 지금은 하드코딩.
_MAX_BUSY = 3

class ReqComposeVideo(BaseModel):
    v_id: int = Field(..., gt=0)
    stream_ids: list[str] | None = Field(None, min_length=1)
    
    @model_validator(mode="after")
    def _check(self):
        if self.stream_ids is not None:
            for stream_id in self.stream_ids:
                if not stream_id:
                    raise ValueError(f"v_id={self.v_id}: stream_id가 없음")
                if len(stream_id) > 20:
                    raise ValueError(f"v_id={self.v_id}: stream_id가 20자를 넘음")
                
            if len(self.stream_ids) != len(set(self.stream_ids)):
                raise ValueError(f"v_id={self.v_id}: stream_ids 중복")
        return self

class ReqCompose(BaseModel):
    """POST 본문. videos 를 빼면 그룹 전체."""
    v_g_id: int = Field(..., gt=0)
    videos: list[ReqComposeVideo] | None = Field(None, min_length=1)
    query: str = Field(..., min_length=1, max_length=1000)
    budget_sec: int | None = Field(None, gt=0)
    callback_url: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def _check(self):
        if self.videos is not None:
            v_ids = []
            for video in self.videos:
                v_ids.append(video.v_id)
            if len(v_ids) != len(set(v_ids)):
                raise ValueError(f"v_id 중복: {v_ids}")
        return self

class RespCompose(schema_resp.Resp_Base):
    comp_id: int | None = None

@router.post("/compose", response_model=RespCompose)
@router.post("/compose/{rest:path}", response_model=RespCompose)
def compose(req: ReqCompose, request: Request):
    log.info(f"compose 접수: v_g_id={req.v_g_id} videos={req.videos} budget_sec={req.budget_sec} {req.query!r}")
    state = request.app.state

    # 편성 중인 행이 _MAX_BUSY 건 이상이면 뒷단에 안 넘기고 거절
    busy = t_compose.select_composes(where_query=_BUSY_WHERE)
    if len(busy) >= _MAX_BUSY:
        b = busy[0]
        log.warning(f"compose 거절: 편성 중 {len(busy)}건 (최대 {_MAX_BUSY}) — v_g_id={b['v_g_id']} "
                    f"comp_id={b['comp_id']} status_code={b['status_code']}({b['status_name']})")
        return JSONResponse(status_code=409, content={
            "v_g_id": req.v_g_id, "code": -1, "result": "fail",
            "reason": f"편성 중 {len(busy)}건 (최대 {_MAX_BUSY})",
            "status_code": b["status_code"], "status_name": b["status_name"],
        })

    return proxy.forward(state.http, state.compose_upstream, request, path=config.COMPOSE_PATH)
