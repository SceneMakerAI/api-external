"""status_compose 라우터 — DB(t_compose) 에서 편성 상태를 읽어 돌려준다 (프록시 아님, 이 서버가 직접 답한다).

  GET /api/v1/status_compose?search_id=20260911-1012-1     ① search_id 만 — 그 편성 하나 (접수 응답의 search_id)
  GET /api/v1/status_compose?v_id=1012&stream_id=VOD       ② v_id + stream_id 둘 다 — 그 조각의 편성
  → 두 형태 중 하나만 허용 (v_id 나 stream_id 하나만 오거나, 섞이거나, 아무것도 없으면 422).

응답: 요청에서 준 필드 + code / result. 여러 행이면 첫 행(발급순), 없으면 code -1 / result "fail".
  {"v_id": 1012, "search_id": "20260911-1012-1", "code": 4000, "result": "편성 완료"}
  code 는 t_compose.status_code, result 는 그 코드의 t_code.name (JOIN — lib/rdb/t_compose.py).
"""
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator

from lib.log import get_logger
from lib.rdb import t_compose
from lib.rdb.rdb import connect

router = APIRouter(prefix="/v1", tags=["status_compose"])
log = get_logger(__name__)


# ── 요청/응답 메시지 쌍 (GET /status_compose)
class StatusComposeRequest(BaseModel):
    """쿼리 파라미터. 두 형태 중 하나만 허용한다 (아니면 422):
      ① search_id 만
      ② v_id + stream_id 둘 다 (하나만 오면 안 된다)
    """
    v_id: int = -1
    stream_id: str | None = Field(None, max_length=20)
    search_id: str | None = Field(None, max_length=45)

    @model_validator(mode="after")
    def _check_keys(self):
        by_search = self.search_id is not None
        by_video = self.v_id != -1 and self.stream_id is not None
        half_video = (self.v_id != -1) != (self.stream_id is not None)     # 둘 중 하나만 온 경우
        if half_video:
            raise ValueError("v_id 와 stream_id 는 항상 같이 와야 한다")
        if by_search == by_video:                                          # 둘 다 없거나, 둘 다 온 경우
            raise ValueError("search_id 만 주거나, v_id + stream_id 를 주거나 둘 중 하나여야 한다")
        return self


class StatusComposeResponse(BaseModel):
    """t_compose 한 행의 상태 — status_code 와 그 문구(t_code.name / description). 필드명은 컬럼·별칭 그대로."""
    v_id: int = -1
    search_id: str | None = None
    stream_id: str | None = None
    code: int
    result: str | None = None
    


@router.get("/status_compose", response_model=StatusComposeResponse,  response_model_exclude_unset=True)     # 요청에서 준 필드 + code/result 만 내보낸다
def status_compose(req: Annotated[StatusComposeRequest, Query()]):
    log.info(f"status_compose 조회: v_id={req.v_id} stream_id={req.stream_id!r} search_id={req.search_id!r}")
    composes = _select(req)      # 동기 핸들러라 FastAPI 가 스레드풀에서 돌린다 — 블로킹(DB) 그대로 호출

    given = req.model_dump(exclude_defaults=True)
    if not composes:
        return StatusComposeResponse(**given, code=-1, result="fail")
    return StatusComposeResponse(**given, code=composes[0]["status_code"], result=composes[0]["status_name"])


def _select(req: StatusComposeRequest) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        return t_compose.select_composes(cur, req.v_id, req.stream_id, req.search_id)
