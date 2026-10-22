"""status_compose 라우터 — t_compose 에서 편성 상태를 읽어 직접 답한다 (프록시 아님).

GET /api/v1/status_compose?comp_id=7     접수 응답의 comp_id
  응답 {comp_id, code, result, status_code, status_name}  code 는 조회 성공 여부(0 / -1). 없으면 -1 / fail 만
"""
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from lib.http import schema_resp
from lib.log import get_logger
from lib.rdb import t_compose

router = APIRouter(prefix="/api/v1", tags=["status_compose"])
log = get_logger(__name__)


# ── 요청/응답 메시지 쌍 (GET /status_compose)
class StatusComposeRequest(BaseModel):
    """쿼리 파라미터. comp_id 필수."""
    comp_id: int = Field(..., gt=0)


class StatusComposeResponse(schema_resp.Resp_Base):
    """code / result 는 조회 성공 여부(0 OK / -1 fail). 편성 상태는 status_code / status_name."""
    comp_id: int
    status_code: int | None = None
    status_name: str | None = None


@router.get("/status_compose", response_model=StatusComposeResponse, response_model_exclude_none=True)
@router.get("/status_compose/{rest:path}", response_model=StatusComposeResponse, response_model_exclude_none=True)   # 뒤 경로는 받기만 (조회에 안 쓴다)
def status_compose(req: Annotated[StatusComposeRequest, Query()]):
    log.info(f"status_compose 조회: comp_id={req.comp_id}")
    composes = t_compose.select_composes(comp_id=req.comp_id)      # 연결은 select_composes 가 연다

    if not composes:
        return StatusComposeResponse(comp_id=req.comp_id, code=-1, result="fail")
    row = composes[0]
    return StatusComposeResponse(
        comp_id=req.comp_id, code=0, result="OK",
        status_code=row["status_code"], status_name=row["status_name"],
    )
