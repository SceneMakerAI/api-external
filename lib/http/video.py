from typing import Literal

import pymysql
from fastapi import APIRouter
from pydantic import BaseModel, Field

from lib.http import http_util, schema_resp
from lib.log import get_logger
from lib.rdb import t_video

router = APIRouter(prefix="/api/v1", tags=["video"])
log = get_logger(__name__)


# ── 요청/응답 메시지 쌍 (POST /video) — 길이는 DB 컬럼 폭에 맞춘다 (name 50 / comment 200)
class Req_Video(BaseModel):
    """POST 본문."""
    v_g_id: int = Field(..., gt=0)                              # t_video_group.v_g_id — 없는 값이면 422
    name: str = Field(..., min_length=1, max_length=50)
    order_no: int | None = Field(None, gt=0)                    # 그룹 안 회차. 없으면 그 그룹의 MAX+1
    play_year: int | None = None
    stream_yn: Literal["Y", "N"] = "N"
    comment: str | None = Field(None, max_length=200)


class Req_VideoUpdate(Req_Video):
    v_id: int = Field(..., gt=0)
    v_g_id: int | None = Field(None, gt=0)
    name: str | None = Field(None, min_length=1, max_length=50)


class Resp_Video(schema_resp.Resp_Base):
    """등록 응답 — 발급된 v_id + code / result."""
    v_id: int


# ── 핸들러 — 동기 def (FastAPI 가 스레드풀에서 돌린다). 연결은 t_video.insert 가 안에서 연다
@router.post("/video", response_model=Resp_Video)
def video_create(req: Req_Video):
    log.info(f"video 등록: v_g_id={req.v_g_id} order_no={req.order_no} name={req.name!r} stream_yn={req.stream_yn}")
    try:
        v_id = t_video.insert(req.v_g_id, req.name, req.order_no, req.play_year, req.stream_yn, req.comment)
    except pymysql.err.IntegrityError as e:
        return http_util.integrity_response(e, "video 등록", v_g_id=req.v_g_id)
    return Resp_Video(v_id=v_id, code=0, result="OK")


# ── 핸들러 — 동기 def (FastAPI 가 스레드풀에서 돌린다). 연결은 t_video.update 가 안에서 연다
@router.put("/video", response_model=Resp_Video)
def video_update(req: Req_VideoUpdate):
    fields = req.model_dump(exclude={"v_id"}, exclude_unset=True)
    log.info(f"video 수정: v_id={req.v_id} {fields}")
    if not fields:
        return http_util.fail_response(422, reason="고칠 필드가 없다", v_id=req.v_id)
    try:
        n = t_video.update(req.v_id, fields)
    except pymysql.err.IntegrityError as e:
        return http_util.integrity_response(e, "video 수정", v_id=req.v_id)
    if n == 0:
        return http_util.fail_response(404, v_id=req.v_id)
    return Resp_Video(v_id=req.v_id, code=0, result="OK")
