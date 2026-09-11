"""MariaDB 공용 — connect() 하나만. agent-stt 의 lib/client/rdb/rdb.py 와 같은 패턴.

  - 연결은 요청마다 새로 연다 (with connect()). 조회 한 번이면 끝나므로 짧게 열고 닫는다.
  - with 블록 정상 종료 → commit, 예외 → rollback, 항상 close.

테이블별 조회는 t_*.py(커서 받음).
"""
from contextlib import contextmanager

import pymysql

import config
from lib.log import get_logger

log = get_logger(__name__)


@contextmanager
def connect():
    """pymysql 연결 context manager. 정상 종료 시 commit, 예외 시 rollback, 항상 close."""
    conn = pymysql.connect(
        host=config.RDB_HOST,
        port=config.RDB_PORT,
        user=config.RDB_USER,
        password=config.RDB_PW,
        database=config.RDB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        log.error("트랜잭션 rollback")
        raise
    finally:
        conn.close()
