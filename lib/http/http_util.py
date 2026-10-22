"""HTTP 공용 — 요청/응답 로깅 미들웨어 + 실패 응답 헬퍼.

미들웨어: 요청 들어올 때 method+URL, 끝날 때 상태코드+URL+소요시간 로그.
main.py 에서 register(app) 로 등록.

실패 응답(fail_response / integrity_response)은 DB 를 직접 쓰는 CRUD 라우터(video_group / video)가 쓴다 —
본문은 늘 code -1 / result "fail" 에 요청 키(v_g_id 등)와 사유를 붙인 꼴.
"""
import time

import pymysql
from fastapi import Request
from fastapi.responses import JSONResponse

from lib.log import get_logger

log = get_logger(__name__)

# IntegrityError 번호 → (HTTP 상태, 사유). FK 없음·NOT NULL 은 요청 값 문제라 422, UNIQUE 중복은 상태 충돌이라 409.
_INTEGRITY = {
    1452: (422, "참조하는 행이 없다 (cate_id / v_g_id)"),
    1048: (422, "NULL 이 될 수 없는 컬럼"),
    1062: (409, "이미 있는 값 (중복)"),
}


def fail_response(status: int, **body) -> JSONResponse:
    """실패 응답 — body(요청 키·사유) + code -1 / result "fail". HTTP 는 404 없음 / 409 거절 / 422 잘못된 값."""
    return JSONResponse(status_code=status, content={**body, "code": -1, "result": "fail"})


def integrity_response(e: pymysql.err.IntegrityError, what: str, **body) -> JSONResponse:
    """INSERT/UPDATE 가 FK·UNIQUE 에 걸렸을 때의 응답. 미리 SELECT 로 검사하지 않고 DB 가 거른 것을 그대로 옮긴다.
    DB 메시지(스키마 이름이 들어 있다)는 로그에만 남기고 외부엔 사유 문구만 준다."""
    errno, msg = e.args[0], (e.args[1] if len(e.args) > 1 else "")
    status, reason = _INTEGRITY.get(errno, (409, "제약 위반"))
    log.warning(f"{what} 거절: {reason} — [{errno}] {msg}")
    return fail_response(status, reason=reason, **body)


def register(app):
    # 이 프로젝트에서 유일한 async — Starlette 미들웨어는 async 만 받는다 (동기로 바꿀 수 없음).
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        log.info(f"→ {request.method} {request.url}")
        t0 = time.time()
        response = await call_next(request)
        log.info(f"← {request.method} {request.url} {response.status_code} ({time.time() - t0:.1f}s)")
        return response
