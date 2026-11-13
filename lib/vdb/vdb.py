"""Milvus 삭제 — 영상(v_id)의 벡터를 컬렉션마다 지운다. 쓰기(적재)는 agent-vision 몫이고 여기는 삭제만.

연결은 함수마다 새로 열고 닫는다 (rdb.connect 와 같은 패턴).
컬렉션은 _COLLECTIONS — 카테고리 구분 없이 전부 지운다 (없는 v_id 는 0건).
"""
from pymilvus import MilvusClient

import config
from lib.log import get_logger

log = get_logger(__name__)

_COLLECTIONS = ("sm_sport_baseball", "sm_drama")


def delete(v_id: int) -> dict[str, int]:
    """그 영상의 벡터를 전부 지운다. 반환: {컬렉션: 삭제 건수}. 실패는 예외로 올라간다."""
    mc = MilvusClient(config.MILVUS_URI)
    try:
        mc.use_database(config.MILVUS_DB)
        result = {}
        for col in _COLLECTIONS:
            if not mc.has_collection(col):
                log.warning(f"vdb delete: 없는 컬렉션 {config.MILVUS_DB}.{col}")
                continue
            r = mc.delete(col, filter=f"v_id == {int(v_id)}")
            mc.flush(col)
            result[col] = r.get("delete_count", 0) if isinstance(r, dict) else 0
    finally:
        mc.close()
    log.info(f"vdb delete: v_id={v_id} {config.MILVUS_DB} → {result}")
    return result
