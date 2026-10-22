"""video_file 라우터 — 외부 최초 호출. POST /api/v1/video_file 를 agent-stt 의 config.STT_PATH_PRE 로 넘긴다.

외부에 노출되는 이름은 video_file 지만, agent-stt 쪽 진입점은 pre_svc 다
(영상 등록 → download → ffmpeg 음성·프레임 추출. STT_TRIGGER=true 면 거기서 STT 까지 이어 돈다).
경로만 바꾸고 본문·응답은 그대로 client/proxy 로.

넘기기 전에 하나만 본다 — t_video_file 에 공정 중 status_code 를 가진 행이 하나라도 있으면
뒷단에 안 넘기고 409 로 거절한다 (범위는 t_video_file.BUSY_WHERE — video_group / video 의 삭제 거절과 같은 값).
"""
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config
from lib.client import proxy
from lib.http import schema_resp
from lib.log import get_logger
from lib.rdb import t_video_file

router = APIRouter(prefix="/api/v1", tags=["video_file"])
log = get_logger(__name__)


class Req_VideoFile(BaseModel):
    v_id: int = Field(..., gt=0)
    file_path: str = Field(..., min_length=5, max_length=200)
    stream_id: str | None = Field(None, max_length=20)
    last_yn: Literal["Y", "N", "y", "n"] = "Y"
    forced_yn: Literal["Y", "N", "y", "n"] = "Y"


class Resp_VideoFile(schema_resp.Resp_Base):
    v_id: int
    stream_id: str | None = None


@router.post("/video_file", response_model=Resp_VideoFile)
@router.post("/video_file/{rest:path}", response_model=Resp_VideoFile)      # /video_file 뒤에 뭐가 붙어도 받는다 — rest 는 인자로 안 받아 무시되고, 뒷단엔 path= 로 준 STT_PATH_PRE 만 간다
def video_file(req: Req_VideoFile, request: Request):
    log.info(f"video_file 접수: v_id={req.v_id} stream_id={req.stream_id!r} file_path={req.file_path} last_yn={req.last_yn} forced_yn={req.forced_yn}")
    state = request.app.state

    # 공정 중인 행이 있으면 뒷단에 안 넘기고 거절
    busy = t_video_file.select_video_files(where_query=t_video_file.BUSY_WHERE)      # 연결은 select_video_files 가 연다
    if busy:
        b = busy[0]
        log.warning(f"video_file 거절: 공정 중 {len(busy)}건 — v_id={b['v_id']} stream_id={b['stream_id']!r} "
                    f"status_code={b['status_code']}({b['status_name']})")
        return JSONResponse(status_code=409, content={
            "v_id": b["v_id"], "stream_id": b["stream_id"], "code": -1, "result": "fail",
            "status_code": b["status_code"], "status_name": b["status_name"],
        })

    return proxy.forward(state.http, state.stt_upstream, request, path=config.STT_PATH_PRE)
