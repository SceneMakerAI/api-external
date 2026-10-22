"""t_video CRUD — 연결은 여기서 직접 연다 (호출측은 함수만 부른다). agent-stt 의 lib/client/rdb/t_video.py 와 같은 컬럼.

영상 1건 = 분석 단위 (드라마 회차 또는 경기). 그룹(t_video_group) 아래에 order_no 로 달리고,
(v_g_id, order_no) 는 UNIQUE 다. 파일(조각)은 t_video_file 이 따로 갖는다.
PK v_id 는 AUTO_INCREMENT — insert 가 발급해 돌려준다. reg/upd_datetime 은 이 테이블에 없다.

summary / summary_stt / search_query / search_result / play_time 은 agent-stt 가 채우는 산출물이다 —
여기서는 읽기만 하고 update 로 못 고친다 (_UPDATABLE 참고).

삭제는 DB CASCADE 다: 영상을 지우면 t_video_file → 분석 결과 전부가 같이 지워진다. 막을지는 호출측(http)이 정한다.
"""
from lib.log import get_logger
from lib.rdb.rdb import connect

log = get_logger(__name__)

_COLS = ("v.v_id, v.v_g_id, v.order_no, v.name, v.play_year, v.stream_yn, v.play_time, "
         "v.summary, v.summary_stt, v.search_query, v.search_result, v.comment")

# update 로 고칠 수 있는 컬럼 — 산출물 컬럼(summary 등)은 에이전트 몫이라 뺀다.
_UPDATABLE = ("v_g_id", "order_no", "name", "play_year", "stream_yn", "comment")


def insert(v_g_id: int, name: str, order_no: int | None = None, play_year: int | None = None,
           stream_yn: str = "N", comment: str | None = None) -> int:
    """영상 1건 등록. 반환: 발급된 v_id.

    order_no 를 안 주면 그 그룹의 MAX+1 — 회차를 호출측이 안 세도 된다 (첫 영상은 1).
    준 값이 그 그룹에 이미 있으면 UNIQUE 위반(IntegrityError 1062), v_g_id 가 없으면 FK 위반(1452)이
    올라온다 — 미리 조회하지 않는다. MAX 와 INSERT 를 한 문장으로 묶어 동시 등록에도 번호가 안 겹친다.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO t_video (v_g_id, order_no, name, play_year, stream_yn, comment) "
            "SELECT %s, COALESCE(%s, COALESCE(MAX(order_no), 0) + 1), %s, %s, %s, %s "
            "FROM t_video WHERE v_g_id=%s",
            (v_g_id, order_no, name, play_year, stream_yn, comment, v_g_id),
        )
        v_id = cur.lastrowid
    log.info(f"t_video insert: v_id={v_id} v_g_id={v_g_id} order_no={order_no or 'MAX+1'} name={name!r}")
    return v_id


def select_videos(v_id: int = -1, v_g_id: int = -1, where_query: str = "") -> list[dict]:
    """기본값이 아닌 인자만 AND 조건으로 묶어 영상 조회. 그룹·회차순. 연결은 안에서 열고 닫는다.

    예) select_videos(v_id=1012)
        select_videos(v_g_id=1)               # 그 그룹의 회차 전부
        select_videos()                       # 전체 — 영상은 회차 단위라 몇 건 안 되므로 전체 조회를 막지 않는다
    값은 f-string 으로 박지 않고 %s 로 넘긴다 — 문자열 따옴표·인젝션은 드라이버가 처리.
    where_query 는 'AND ...' 로 시작하는 SQL 조각을 그대로 붙인다 — 소스에 박은 문자열만 넘길 것 (외부 입력 금지).
    """
    where, vals = "", []
    if v_id != -1:
        where += " AND v.v_id=%s"
        vals.append(v_id)
    if v_g_id != -1:
        where += " AND v.v_g_id=%s"
        vals.append(v_g_id)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM t_video v "
            f"WHERE 1=1{where} {where_query} ORDER BY v.v_g_id, v.order_no",
            vals,
        )
        return list(cur.fetchall())      # DictCursor (rdb.connect) 라 행이 dict 로 온다


def update(v_id: int, fields: dict) -> int:
    """fields 에 담긴 컬럼만 고친다. 반환: 매칭 행 수 (0 이면 그 v_id 가 없다 — rdb.connect 의 FOUND_ROWS).

    fields 는 {컬럼: 값}. 값이 None 이면 NULL 로 지운다 — '안 건드림' 과 '지움' 을 구분하려고 kwargs 가 아니라
    dict 를 받는다 (호출측은 요청에 들어온 필드만 담아 넘긴다). _UPDATABLE 밖의 컬럼은 ValueError.
    빈 dict 면 아무것도 안 하고 0. (v_g_id, order_no) 가 겹치면 IntegrityError 1062 가 올라온다.
    """
    bad = set(fields) - set(_UPDATABLE)
    if bad:
        raise ValueError(f"t_video update: 고칠 수 없는 컬럼 {sorted(bad)}")
    if not fields:
        return 0

    sets = ", ".join(f"{col}=%s" for col in fields)       # 컬럼명은 _UPDATABLE 로 걸러진 것만 — 외부 입력이 아니다
    vals = [*fields.values(), v_id]
    with connect() as conn, conn.cursor() as cur:
        n = cur.execute(f"UPDATE t_video SET {sets} WHERE v_id=%s", vals)
    log.info(f"t_video update: v_id={v_id} {sorted(fields)} → {n}건")
    return n


def delete(v_id: int) -> int:
    """영상 1건 삭제. 반환: 삭제 행 수 (0 이면 없던 것). 파일·결과는 DB CASCADE 로 같이 지워진다."""
    with connect() as conn, conn.cursor() as cur:
        n = cur.execute("DELETE FROM t_video WHERE v_id=%s", (v_id,))
    log.info(f"t_video delete: v_id={v_id} → {n}건 (파일·결과는 CASCADE)")
    return n
