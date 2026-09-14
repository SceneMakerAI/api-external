"""status_svc 라우터 — DB(t_video_file) 에서 자막 공정 상태를 읽어 돌려준다 (프록시 아님, 이 서버가 직접 답한다).

  GET /api/v1/status?v_id=1012&stream_id=VOD   그 조각 하나 — v_id / stream_id 둘 다 필수 (빠지면 422)
  (v_id, stream_id) 가 t_video_file 의 PK 라 결과는 항상 한 건 이하다.

응답: v_id / stream_id + code / result. 없으면 code -1 / result "fail".
  {"v_id": 1012, "stream_id": "VOD", "code": 2011, "result": "음성·이미지 추출 완료"}
  code 는 t_video_file.status_code, result 는 그 코드의 t_code.name (JOIN — lib/rdb/t_video_file.py).
"""
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from lib.log import get_logger
from lib.rdb import t_video_file

router = APIRouter(prefix="/api/v1", tags=["status_svc"])
log = get_logger(__name__)


# ── 요청/응답 메시지 쌍 (GET /status)
class StatusRequest(BaseModel):
    """쿼리 파라미터. 둘 다 필수."""
    v_id: int
    stream_id: str = Field(..., max_length=20)


class StatusResponse(BaseModel):
    """t_video_file 한 행의 상태 — 요청 키 + code(status_code) / result(t_code.name)."""
    v_id: int
    stream_id: str
    code: int
    result: str | None = None


@router.get("/status", response_model=StatusResponse, response_model_exclude_unset=True)
@router.get("/status/{rest:path}", response_model=StatusResponse, response_model_exclude_unset=True)   # /status 뒤 경로는 받기만 (조회에 안 쓰므로 인자로도 안 받는다)
def status_svc(req: Annotated[StatusRequest, Query()]):
    log.info(f"status 조회: v_id={req.v_id} stream_id={req.stream_id!r}")
    files = t_video_file.select_video_files(req.v_id, req.stream_id)      # 동기 핸들러라 FastAPI 가 스레드풀에서 돌린다 — 블로킹(DB) 그대로 호출. 연결은 select_video_files 가 연다
    # code ← status_code / result ← t_code.name. PK 조회라 한 건 이하. 없으면 -1 / "fail" (agent-stt 응답 관례).
    if not files:
        return StatusResponse(v_id=req.v_id, stream_id=req.stream_id, code=-1, result="fail")
    return StatusResponse(v_id=req.v_id, stream_id=req.stream_id, code=files[0]["status_code"], result=files[0]["status_name"])
