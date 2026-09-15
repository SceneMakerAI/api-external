"""stt_svc 라우터 — 외부 최초 호출. POST /api/v1/stt_svc 를 agent-stt 의 config.STT_PATH_PRE 로 넘긴다.

외부에 노출되는 이름은 stt_svc 지만, agent-stt 쪽 진입점은 pre_svc 다
(영상 등록 → download → ffmpeg 음성·프레임 추출. STT_TRIGGER=true 면 거기서 STT 까지 이어 돈다).
경로만 바꾸고 본문·응답은 그대로 client/proxy 로.

넘기기 전에 하나만 본다 — t_video_file 에 공정 중 status_code 를 가진 행이 하나라도 있으면
뒷단에 안 넘기고 409 로 거절한다 (범위는 아래 _BUSY_WHERE 에 하드코딩).
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from lib.client import proxy
from lib.log import get_logger
from lib.rdb import t_video_file

router = APIRouter(prefix="/api/v1", tags=["stt_svc"])
log = get_logger(__name__)

# 공정 중으로 보는 status_code 범위 (초과, 미만) — 정확한 값은 추후 확정. 지금은 하드코딩.
#   select_video_files 의 where_query 로 그대로 붙는 SQL 조각 (f = t_video_file 별칭).
_BUSY_WHERE = ("AND ((f.status_code > 2011 AND f.status_code < 2090) "
               "OR (f.status_code > 3000 AND f.status_code < 3090))")


@router.post("/stt_svc")
@router.post("/stt_svc/{rest:path}")      # /stt_svc 뒤에 뭐가 붙어도 받는다 — rest 는 인자로 안 받아 무시되고, 뒷단엔 path= 로 준 STT_PATH_PRE 만 간다
def stt_svc(request: Request):
    state = request.app.state

    # 공정 중인 행이 있으면 뒷단에 안 넘기고 거절
    busy = t_video_file.select_video_files(where_query=_BUSY_WHERE)      # 연결은 select_video_files 가 연다
    if busy:
        b = busy[0]
        log.warning(f"stt_svc 거절: 공정 중 {len(busy)}건 — v_id={b['v_id']} stream_id={b['stream_id']!r} "
                    f"status_code={b['status_code']}({b['status_name']})")
        return JSONResponse(status_code=409, content={
            "v_id": b["v_id"], "stream_id": b["stream_id"], "code": -1, "result": "fail",
            "status_code": b["status_code"], "status_name": b["status_name"],
        })

    return proxy.forward(state.http, state.stt_upstream, request, path=config.STT_PATH_PRE)
