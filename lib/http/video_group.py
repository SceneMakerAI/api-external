
import pymysql
from fastapi import APIRouter
from pydantic import BaseModel, Field

from lib.http import http_util, schema_resp
from lib.log import get_logger
from lib.rdb import t_video_group

router = APIRouter(prefix="/api/v1", tags=["video_group"])
log = get_logger(__name__)


# ── 요청/응답 메시지 쌍 (POST /video_group) — 길이는 DB 컬럼 폭에 맞춘다 (name 100 / callback_url 200 / comment 200)
class Req_VideoGroup(BaseModel):
    """POST 본문."""
    cate_id: int = Field(..., gt=0)                             # t_category.cate_id — 드라마 3000 / 야구 5100. 없는 값이면 422
    name: str = Field(..., min_length=1, max_length=100)
    callback_url: str | None = Field(None, max_length=200)      # 전체 완료 콜백 (조각이 아니라 그룹 단위)
    comment: str | None = Field(None, max_length=200)


class Req_VideoGroupUpdate(Req_VideoGroup):
    v_g_id: int = Field(..., gt=0)
    cate_id: int | None = Field(None, gt=0)
    name: str | None = Field(None, min_length=1, max_length=100)


class Resp_VideoGroup(schema_resp.Resp_Base):
    """등록 응답 — 발급된 v_g_id + code / result."""
    v_g_id: int


# ── 핸들러 — 동기 def (FastAPI 가 스레드풀에서 돌린다). 연결은 t_video_group.insert 가 안에서 연다
@router.post("/video_group", response_model=Resp_VideoGroup)
def video_group_create(req: Req_VideoGroup):
    log.info(f"video_group 등록: cate_id={req.cate_id} name={req.name!r} callback_url={req.callback_url!r}")
    try:
        v_g_id = t_video_group.insert(req.cate_id, req.name, req.callback_url, req.comment)
    except pymysql.err.IntegrityError as e:
        return http_util.integrity_response(e, "video_group 등록")
    return Resp_VideoGroup(v_g_id=v_g_id, code=0, result="OK")



# ── 핸들러 — 동기 def (FastAPI 가 스레드풀에서 돌린다). 연결은 t_video_group.insert 가 안에서 연다
@router.put("/video_group", response_model=Resp_VideoGroup)
def video_group_update(req: Req_VideoGroupUpdate):
    fields = req.model_dump(exclude={"v_g_id"}, exclude_unset=True)
    log.info(f"video_group 수정: v_g_id={req.v_g_id} {fields}")
    if not fields:
        return http_util.fail_response(422, reason="고칠 필드가 없다", v_g_id=req.v_g_id)
    try:
        n = t_video_group.update(req.v_g_id, fields)
    except pymysql.err.IntegrityError as e:
        return http_util.integrity_response(e, "video_group 수정", v_g_id=req.v_g_id)
    if n == 0:
        return http_util.fail_response(404, v_g_id=req.v_g_id)
    return Resp_VideoGroup(v_g_id=req.v_g_id, code=0, result="OK")
