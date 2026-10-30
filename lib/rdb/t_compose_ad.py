"""t_compose_ad 조회
영상(v_id) 1건에 광고 지점 요청 여러 건, PK 는 comp_ad_id. 넣은 광고·지점은 t_compose_ad_item / t_compose_ad_point.
status_code 5000번대 (t_code): 5000 완료 / 5001 지점 없음 / 5010~ 진행 중 / 59xx 실패
"""

from lib.log import get_logger
from lib.rdb.rdb import connect

log = get_logger(__name__)

# status_code 문구는 t_code 를 LEFT JOIN 으로 같이 읽는다 (status_name / status_desc). 미등록 코드면 NULL
_COLS = (
    "a.comp_ad_id, a.v_g_id, a.v_id, "
    "a.status_code, t.name AS status_name, t.description AS status_desc, "
    "a.point_cnt, a.comment, a.reg_datetime, a.upd_datetime"
)


def select_compose_ads(v_id: int = -1, comp_ad_id: int = -1, where_query: str = "") -> list[dict]:
    """기본값이 아닌 인자만 AND 로 묶어 조회. 발급순(comp_ad_id). 연결은 안에서 열고 닫는다.

    where_query 는 'AND ...' SQL 조각을 그대로 붙인다 — 소스에 박은 문자열만 (외부 입력 금지).
    조건이 하나도 없으면 빈 목록.
    """
    where, vals = "", []
    if v_id != -1:
        where += " AND a.v_id=%s"
        vals.append(v_id)
    if comp_ad_id != -1:
        where += " AND a.comp_ad_id=%s"
        vals.append(comp_ad_id)
    if not vals and not where_query:
        return []

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM t_compose_ad a "
            f"LEFT JOIN t_code t ON t.code = a.status_code "
            f"WHERE 1=1{where} {where_query} ORDER BY a.comp_ad_id",
            vals,
        )
        return list(cur.fetchall())
