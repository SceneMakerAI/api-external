"""stt_svc 라우터 — 외부 최초 호출. POST /api/v1/stt_svc 를 agent-stt 의 config.STT_PATH_PRE 로 넘긴다.

외부에 노출되는 이름은 stt_svc 지만, agent-stt 쪽 진입점은 pre_svc 다
(영상 등록 → download → ffmpeg 음성·프레임 추출. STT_TRIGGER=true 면 거기서 STT 까지 이어 돈다).
경로만 바꾸고 본문·응답은 그대로 client/proxy 로.
"""
from fastapi import APIRouter, Request

import config
from lib.client import proxy

router = APIRouter(prefix="/api/v1", tags=["stt_svc"])


@router.post("/stt_svc")
@router.post("/stt_svc/{rest:path}")      # /stt_svc 뒤에 오는 경로 전부 — /stt_svc/a/b → 뒷단 /api/v1/pre_svc/a/b
def stt_svc(request: Request, rest: str = ""):
    state = request.app.state
    path = config.STT_PATH_PRE + (f"/{rest}" if rest else "")
    return proxy.forward(state.http, state.stt_upstream, request, path=path)
