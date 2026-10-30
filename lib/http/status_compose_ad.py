"""status_compose_ad 라우터 — 광고 편성 상태를 DB(t_compose_ad)에서 읽어 직접 답한다. 프록시 아님.

GET /api/v1/status_compose_ad?comp_ad_id=7

  파라미터
    comp_ad_id   접수(POST /api/v1/compose_ad) 응답의 comp_ad_id. 필수

  응답
    {"comp_ad_id": 7, "code": 0,  "result": "OK", "status_code": 5000, "status_name": "광고 지점 찾기 완료"}
    {"comp_ad_id": 7, "code": -1, "result": "fail"}                                           없는 id

  code / result   조회 성공 여부 (0 OK · -1 fail)
  status_code     편성 상태
  status_name     t_code.name. 미등록 코드면 null
"""
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from lib.http import schema_resp
from lib.log import get_logger
from lib.rdb import t_compose_ad

router = APIRouter(prefix="/api/v1", tags=["status_compose_ad"])
log = get_logger(__name__)


# ── 요청/응답 메시지 쌍 (GET /status_compose_ad)
class StatusComposeAdRequest(BaseModel):
    """쿼리 파라미터. comp_ad_id 필수."""
    comp_ad_id: int = Field(..., gt=0)


class StatusComposeAdResponse(schema_resp.Resp_Base):
    """code / result 는 조회 성공 여부(0 OK / -1 fail). 편성 상태는 status_code / status_name."""
    comp_ad_id: int
    status_code: int | None = None
    status_name: str | None = None


@router.get("/status_compose_ad", response_model=StatusComposeAdResponse, response_model_exclude_none=True)
@router.get("/status_compose_ad/{rest:path}", response_model=StatusComposeAdResponse, response_model_exclude_none=True)   # 뒤 경로는 받기만 (조회에 안 쓴다)
def status_compose_ad(req: Annotated[StatusComposeAdRequest, Query()]):

    log.info(f"status_compose_ad 조회: comp_ad_id={req.comp_ad_id}")
    rows = t_compose_ad.select_compose_ads(comp_ad_id=req.comp_ad_id)      # 연결은 select_compose_ads 가 연다

    if not rows:
        return StatusComposeAdResponse(comp_ad_id=req.comp_ad_id, code=-1, result="fail")
    row = rows[0]
    return StatusComposeAdResponse(
        comp_ad_id=req.comp_ad_id,
        code=0,
        result="OK",
        status_code=row["status_code"],
        status_name=row["status_name"],
    )
