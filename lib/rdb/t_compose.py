"""t_compose 조회 — 커서를 받아 동작 (connect 는 호출측이 연다). agent-compose 의 src/rdb/composes.py 와 같은 컬럼.

영상 1건(v_id)에 편성이 여러 개 달린다 — PK 는 (v_id, comp_id). comp_id 는 v_id 안에서 1부터.
search_id 는 접수 시 발급되는 {요청일}-{v_id}-{comp_id} — 외부가 접수 응답으로 받는 식별자다.

status_code 는 4000번대 (agent-compose ComposeStatus 참고):
  4000 OK / 4001 EMPTY / 4020 PLAN / 4030 CUT / 4040 VERIFY / 4050 RENDER / 4900 ERROR / 4950 ERROR_RENDER
"""
from lib.log import get_logger

log = get_logger(__name__)

# status_code 의 문구는 t_code(code, object, result, name, description)가 갖는다 — LEFT JOIN 으로 같이 읽는다.
#   ui-sbs-viwer 와 같은 별칭: status_name / status_desc. 미등록 코드면 NULL.
_COLS = ("c.v_id, c.comp_id, c.search_id, c.stream_id, c.query, c.budget_sec, c.callback_url, "
         "c.status_code, t.name AS status_name, t.description AS status_desc, "
         "c.duration_sec, c.clip_cnt, c.bumper_yn, c.reg_datetime")


def select_composes(cur, v_id: int = -1, stream_id: str | None = None,
                    search_id: str | None = None) -> list[dict]:
    """기본값이 아닌 인자만 AND 조건으로 묶어 편성 조회. 발급순.

    예) select_composes(cur, v_id=1012, search_id="20260911-1012-1")
    값은 f-string 으로 박지 않고 %s 로 넘긴다 — 문자열 따옴표·인젝션은 드라이버가 처리.
    조건이 하나도 없으면 전체를 훑게 되므로 빈 목록을 돌려준다.
    """
    where, vals = "", []
    if v_id != -1:
        where += " AND c.v_id=%s"
        vals.append(v_id)
    if stream_id is not None:
        where += " AND c.stream_id=%s"
        vals.append(stream_id)
    if search_id is not None:
        where += " AND c.search_id=%s"
        vals.append(search_id)
    if not vals:
        return []

    cur.execute(
        f"SELECT {_COLS} FROM t_compose c "
        f"LEFT JOIN t_code t ON t.code = c.status_code "
        f"WHERE 1=1{where} ORDER BY c.v_id, c.comp_id",
        vals,
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
