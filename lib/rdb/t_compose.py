"""t_compose 조회
그룹(v_g_id) 1건에 편성 여러 건, PK 는 comp_id. 대상·클립은 t_compose_video / t_compose_clip.
status_code 4000번대 (t_code): 4000 완료 / 4001 장면 없음 / 4010~ 진행 중 / 49xx 실패
"""

from lib.log import get_logger
from lib.rdb.rdb import connect

log = get_logger(__name__)

# status_code 문구는 t_code 를 LEFT JOIN 으로 같이 읽는다 (status_name / status_desc). 미등록 코드면 NULL
_COLS = ("c.comp_id, c.v_g_id, c.query, c.budget_sec, c.callback_url, "
         "c.status_code, t.name AS status_name, t.description AS status_desc, "
         "c.duration_sec, c.clip_cnt, c.comment, c.reg_datetime, c.upd_datetime")

def select_composes(v_g_id: int = -1, comp_id: int = -1, where_query: str = "") -> list[dict]:
    """기본값이 아닌 인자만 AND 로 묶어 조회. 발급순(comp_id). 연결은 안에서 열고 닫는다.

    where_query 는 'AND ...' SQL 조각을 그대로 붙인다 — 소스에 박은 문자열만 (외부 입력 금지).
    조건이 하나도 없으면 빈 목록.
    """
    where, vals = "", []
    if v_g_id != -1:
        where += " AND c.v_g_id=%s"
        vals.append(v_g_id)
    if comp_id != -1:
        where += " AND c.comp_id=%s"
        vals.append(comp_id)
    if not vals and not where_query:
        return []

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM t_compose c "
            f"LEFT JOIN t_code t ON t.code = c.status_code "
            f"WHERE 1=1{where} {where_query} ORDER BY c.comp_id",
            vals,
        )
        return list(cur.fetchall())