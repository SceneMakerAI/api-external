"""t_video_group CRUD — 연결은 여기서 직접 연다 (호출측은 함수만 부른다).

그룹 1건 = 드라마 시리즈 또는 야구 경기 1건. 영상(t_video)은 이 아래에 회차(order_no)로 달린다.
카테고리(cate_id)와 콜백(callback_url)은 영상이 아니라 그룹의 속성이다.
PK v_g_id 는 AUTO_INCREMENT — insert 가 발급해 돌려준다.

삭제는 DB CASCADE 다: 그룹을 지우면 t_video → t_video_file → 분석 결과 전부,
그리고 t_char_drama(인물 은행) / t_compose(편성) 까지 같이 지워진다. 막을지는 호출측(http)이 정한다.
"""
from lib.log import get_logger
from lib.rdb.rdb import connect

log = get_logger(__name__)

# cate_name 은 t_category 를 거쳐 '대분류-소분류' (예: '스포츠-야구'). 소분류가 없으면 대분류 그대로 ('드라마').
#   agent-stt 의 lib/client/rdb/t_video.py 와 같은 꼴 — 그쪽의 CATEGORIES 판정과 문자열이 맞아야 한다.
# video_cnt 는 소속 영상 수 — 목록에서 비어 있는 그룹을 가려내기 위한 것.
_COLS = ("g.v_g_id, g.cate_id, CONCAT_WS('-', p.cate_name, c.cate_name) AS cate_name, "
         "g.name, g.callback_url, g.comment, g.reg_datetime, g.upd_datetime, "
         "(SELECT COUNT(*) FROM t_video v WHERE v.v_g_id = g.v_g_id) AS video_cnt")

# update 로 고칠 수 있는 컬럼 — 나머지(v_g_id, reg/upd_datetime)는 DB 가 관리한다.
_UPDATABLE = ("cate_id", "name", "callback_url", "comment")


def insert(cate_id: int, name: str, callback_url: str | None = None, comment: str | None = None) -> int:
    """그룹 1건 등록. 반환: 발급된 v_g_id.

    cate_id 가 t_category 에 없으면 FK 위반(IntegrityError 1452)이 올라온다 — 미리 조회하지 않는다.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO t_video_group (cate_id, name, callback_url, comment) VALUES (%s, %s, %s, %s)",
            (cate_id, name, callback_url, comment),
        )
        v_g_id = cur.lastrowid
    log.info(f"t_video_group insert: v_g_id={v_g_id} cate_id={cate_id} name={name!r}")
    return v_g_id


def select_video_groups(v_g_id: int = -1, cate_id: int = -1, where_query: str = "") -> list[dict]:
    """기본값이 아닌 인자만 AND 조건으로 묶어 그룹 조회. 등록순. 연결은 안에서 열고 닫는다.

    예) select_video_groups(v_g_id=1)
        select_video_groups(cate_id=3000)
        select_video_groups()                 # 전체 — 그룹은 몇 건 안 되므로 전체 조회를 막지 않는다
    값은 f-string 으로 박지 않고 %s 로 넘긴다 — 문자열 따옴표·인젝션은 드라이버가 처리.
    where_query 는 'AND ...' 로 시작하는 SQL 조각을 그대로 붙인다 — 소스에 박은 문자열만 넘길 것 (외부 입력 금지).
    """
    where, vals = "", []
    if v_g_id != -1:
        where += " AND g.v_g_id=%s"
        vals.append(v_g_id)
    if cate_id != -1:
        where += " AND g.cate_id=%s"
        vals.append(cate_id)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM t_video_group g "
            f"JOIN t_category c ON c.cate_id = g.cate_id "
            f"LEFT JOIN t_category p ON p.cate_id = c.p_cate_id "
            f"WHERE 1=1{where} {where_query} ORDER BY g.v_g_id",
            vals,
        )
        return list(cur.fetchall())      # DictCursor (rdb.connect) 라 행이 dict 로 온다


def update(v_g_id: int, fields: dict) -> int:
    """fields 에 담긴 컬럼만 고친다. 반환: 매칭 행 수 (0 이면 그 v_g_id 가 없다 — rdb.connect 의 FOUND_ROWS).

    fields 는 {컬럼: 값}. 값이 None 이면 NULL 로 지운다 — '안 건드림' 과 '지움' 을 구분하려고 kwargs 가 아니라
    dict 를 받는다 (호출측은 요청에 들어온 필드만 담아 넘긴다). _UPDATABLE 밖의 컬럼은 ValueError.
    빈 dict 면 아무것도 안 하고 0.
    """
    bad = set(fields) - set(_UPDATABLE)
    if bad:
        raise ValueError(f"t_video_group update: 고칠 수 없는 컬럼 {sorted(bad)}")
    if not fields:
        return 0

    sets = ", ".join(f"{col}=%s" for col in fields)       # 컬럼명은 _UPDATABLE 로 걸러진 것만 — 외부 입력이 아니다
    vals = [*fields.values(), v_g_id]
    with connect() as conn, conn.cursor() as cur:
        n = cur.execute(f"UPDATE t_video_group SET {sets} WHERE v_g_id=%s", vals)
    log.info(f"t_video_group update: v_g_id={v_g_id} {sorted(fields)} → {n}건")
    return n


def delete(v_g_id: int) -> int:
    """그룹 1건 삭제. 반환: 삭제 행 수 (0 이면 없던 것). 소속 영상·결과는 DB CASCADE 로 같이 지워진다."""
    with connect() as conn, conn.cursor() as cur:
        n = cur.execute("DELETE FROM t_video_group WHERE v_g_id=%s", (v_g_id,))
    log.info(f"t_video_group delete: v_g_id={v_g_id} → {n}건 (소속 영상·결과는 CASCADE)")
    return n
