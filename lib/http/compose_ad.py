"""compose_ad 라우터. 광고 지점 편성 접수를 agent-compose 로 넘긴다.
본문은 그대로, 경로만 config.COMPOSE_AD_PATH (/api/v1/compose-ad) 로 바꾼다.
--------------------------------------------------------------------------
POST /api/v1/compose_ad
  요청
    {
      "v_id": 1036,                      영상 1건
      "ad_items": [                      한 줄 = 광고 하나
        {"ad_cate_id": 1, "ad_item_id": 2},
        {"ad_cate_id": 4, "ad_item_id": null}    ad_item_id null = 카테고리만
      ]
    }
    422        같은 (ad_cate_id, ad_item_id) 중복 · _ITEMS_MAX 줄 초과

  응답
    {"comp_ad_id": 7, "code": 0, "result": "OK"}            접수
    {"code": -1, "result": "fail", "reason": "..."}          거절

  409 (뒷단에 안 넘김)
    같은 v_id 가 편성 중 (status_code 5001 초과 5090 미만)
    편성 중 행이 _MAX_BUSY 건 이상
--------------------------------------------------------------------------
  완료 통보 없음 — GET /api/v1/status_compose_ad?comp_ad_id= 로 본다.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

import config
from lib.client import proxy
from lib.http import schema_resp
from lib.log import get_logger
from lib.rdb import t_compose_ad

router = APIRouter(prefix="/api/v1", tags=["compose_ad"])
log = get_logger(__name__)


# 편성 중으로 보는 status_code 범위 (초과, 미만) — 5010 PREPARE ~ 5030 MATCH. 5000 완료 / 5001 지점 없음 / 5900 실패는 뺀다.
_BUSY_WHERE = "AND (a.status_code > 5001 AND a.status_code < 5090)"
# 동시에 돌릴 수 있는 광고 편성 수 — 편성 중인 행이 이 수 이상이면 거절. 여기서 조정한다.
_MAX_BUSY = 2
# 한 요청에 넣을 수 있는 광고 줄 수 상한 (무한정 받지 않기 위해서)
_ITEMS_MAX = 20


class ReqAdItem(BaseModel):
    """광고 한 줄 = t_compose_ad_item 한 행. ad_item_id 없으면 카테고리만."""
    ad_cate_id: int = Field(..., gt=0)
    ad_item_id: int | None = Field(None, gt=0)


class ReqComposeAd(BaseModel):
    """POST 본문. 영상 1건."""
    v_id: int = Field(..., gt=0)
    ad_items: list[ReqAdItem] = Field(..., min_length=1, max_length=_ITEMS_MAX)

    @model_validator(mode="after")
    def _check(self):
        pairs = []
        for item in self.ad_items:
            pairs.append((item.ad_cate_id, item.ad_item_id))
        if len(pairs) != len(set(pairs)):
            raise ValueError(f"ad_items 중복: {pairs}")
        return self


class RespComposeAd(schema_resp.Resp_Base):
    comp_ad_id: int | None = None


@router.post("/compose_ad", response_model=RespComposeAd)
@router.post("/compose_ad/{rest:path}", response_model=RespComposeAd)
def compose_ad(req: ReqComposeAd, request: Request):
    ad_items = []
    for item in req.ad_items:
        ad_items.append(item.model_dump())
    log.info(f"compose_ad 접수: v_id={req.v_id} ad_items={ad_items}")
    state = request.app.state

    # 같은 영상이 편성 중이면 거절 — 한 영상에 분석 하나
    same = t_compose_ad.select_compose_ads(v_id=req.v_id, where_query=_BUSY_WHERE)
    if same:
        b = same[0]
        log.warning(
            f"compose_ad 거절: v_id={req.v_id} 편성 중 — comp_ad_id={b['comp_ad_id']} "
            f"status_code={b['status_code']}({b['status_name']})"
        )
        return JSONResponse(
            status_code=409,
            content={
                "v_id": req.v_id, "code": -1, "result": "fail",
                "reason": f"이 영상은 편성 중 (comp_ad_id={b['comp_ad_id']})",
                "comp_ad_id": b["comp_ad_id"],
                "status_code": b["status_code"], "status_name": b["status_name"],
            },
        )

    # 편성 중인 행이 _MAX_BUSY 건 이상이면 뒷단에 안 넘기고 거절
    busy = t_compose_ad.select_compose_ads(where_query=_BUSY_WHERE)
    if len(busy) >= _MAX_BUSY:
        b = busy[0]
        log.warning(
            f"compose_ad 거절: 편성 중 {len(busy)}건 (최대 {_MAX_BUSY}) — v_id={b['v_id']} "
            f"comp_ad_id={b['comp_ad_id']} status_code={b['status_code']}({b['status_name']})"
        )
        return JSONResponse(
            status_code=409,
            content={
                "v_id": req.v_id, "code": -1, "result": "fail",
                "reason": f"편성 중 {len(busy)}건 (최대 {_MAX_BUSY})",
                "status_code": b["status_code"], "status_name": b["status_name"],
            },
        )

    return proxy.forward(state.http, state.compose_upstream, request, path=config.COMPOSE_AD_PATH)
