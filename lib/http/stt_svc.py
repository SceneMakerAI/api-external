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
@router.post("/stt_svc/{rest:path}")      # /stt_svc 뒤에 뭐가 붙어도 받는다 — rest 는 인자로 안 받아 무시되고, 뒷단엔 path= 로 준 STT_PATH_PRE 만 간다
def stt_svc(request: Request):
    state = request.app.state
    return proxy.forward(state.http, state.stt_upstream, request, path=config.STT_PATH_PRE)
