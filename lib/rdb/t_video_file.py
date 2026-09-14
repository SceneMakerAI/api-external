"""t_video_file 조회 — 연결은 여기서 직접 연다 (호출측은 함수만 부른다). agent-stt 의 lib/client/rdb/t_video_file.py 와 같은 컬럼.

영상 1건(v_id)에 파일 여러 개가 달린다 — PK 는 (v_id, stream_id).
  VOD   : stream_id='VOD' 한 행
  Stream: 조각마다 한 행

status_code 는 2000번대 (agent-stt lib/def_code.py 참고):
  2000 OK / 2001 접수 / 2010 추출 중 / 2011 추출 완료 / 2030 대사 추출 중 / ... / 29xx 실패
"""
from lib.log import get_logger
from lib.rdb.rdb import connect

log = get_logger(__name__)

# status_code 의 문구는 t_code(code, object, result, name, description)가 갖는다 — LEFT JOIN 으로 같이 읽는다.
#   ui-sbs-viwer 와 같은 별칭: status_name / status_desc. 미등록 코드면 NULL.
_COLS = ("f.v_id, f.stream_id, f.stream_seq, f.stream_idx_last, f.file_path, "
         "f.stream_last, f.forced_yn, f.callback_url, "
         "f.status_code, t.name AS status_name, t.description AS status_desc, "
         "f.play_time, f.reg_datetime, f.comment")


def select_video_files(v_id: int = -1, stream_id: str | None = None, where_query: str = "") -> list[dict]:
    """기본값이 아닌 인자만 AND 조건으로 묶어 파일(조각) 조회. 등록순. 연결은 안에서 열고 닫는다.

    예) select_video_files(v_id=1012, stream_id="VOD")
        select_video_files(where_query="AND f.status_code > 2000 AND f.status_code < 2090")
    값은 f-string 으로 박지 않고 %s 로 넘긴다 — 문자열 따옴표·인젝션은 드라이버가 처리.
    where_query 는 'AND ...' 로 시작하는 SQL 조각을 그대로 붙인다 — 소스에 박은 문자열만 넘길 것 (외부 입력 금지).
    조건이 하나도 없으면 전체를 훑게 되므로 빈 목록을 돌려준다.
    """
    where, vals = "", []

    if v_id != -1:
        where += " AND f.v_id=%s"
        vals.append(v_id)
    if stream_id is not None:
        where += " AND f.stream_id=%s"
        vals.append(stream_id)

    if not vals and not where_query:
        return []
    
    
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM t_video_file f "
            f"LEFT JOIN t_code t ON t.code = f.status_code "
            f"WHERE 1=1{where} {where_query} ORDER BY f.v_id, f.stream_seq",
            vals,
        )
        return list(cur.fetchall())      # DictCursor (rdb.connect) 라 행이 dict 로 온다
