"""뒷단 프록시 — 받은 요청을 upstream 으로 그대로 넘기고, 응답을 그대로 돌려준다.

가공은 없다. 하는 일은 셋뿐:
  ① upstream 배열에서 다음 서버 하나 고르기 (라운드로빈)
  ② method / path / query / header / body 그대로 전달
  ③ 요청 본문·응답 본문을 로그에 그대로 찍기

전부 동기다. 핸들러가 def 라 FastAPI 가 스레드풀에서 돌리므로 블로킹 호출이어도 서버는 안 막힌다.
"""
import itertools
import logging

import anyio.from_thread
import httpx
from fastapi import Request, Response

from lib.log import get_logger

log = get_logger(__name__)

# 전달하지 않는 헤더 — 연결 단위(hop-by-hop) 이거나 httpx 가 다시 계산하는 것들.
_SKIP_REQ_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}
#   date / server 는 이 서버(uvicorn)가 다시 붙이므로 upstream 것을 넘기면 두 번 찍힌다.
_SKIP_RES_HEADERS = {"content-length", "transfer-encoding", "connection", "content-encoding",
                     "date", "server"}

# httpx 가 요청마다 남기는 INFO 한 줄은 아래 [req]/[res] 와 겹치므로 끈다.
logging.getLogger("httpx").setLevel(logging.WARNING)


def round_robin(upstreams: list[str]):
    """upstream 배열을 무한 순환하는 이터레이터. main.py 에서 1회 만들어 app.state 에 둔다."""
    return itertools.cycle(upstreams)


def forward(http: httpx.Client, upstream_iter, request: Request,
            path: str | None = None) -> Response:
    """path 를 주면 그 경로로 보낸다 (외부 URL 과 뒷단 URL 이 다를 때). 안 주면 받은 경로 그대로."""
    base = next(upstream_iter)
    url = f"{base}{path or request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    # Starlette 의 본문 읽기는 async 뿐이다 — 동기 핸들러(워커 스레드)에서는 이벤트루프에 위임해 받는다.
    body = anyio.from_thread.run(request.body)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_REQ_HEADERS}

    log.info(f"[req] {request.method} {url}\n{body.decode('utf-8', errors='replace')}")

    res = http.request(request.method, url, headers=headers, content=body)

    log.info(f"[res] {res.status_code} {url}\n{res.text}")

    return Response(
        content=res.content,
        status_code=res.status_code,
        headers={k: v for k, v in res.headers.items() if k.lower() not in _SKIP_RES_HEADERS},
    )
