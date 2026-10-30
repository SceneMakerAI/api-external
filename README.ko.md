# api-external

**외부 공개 API 게이트웨이** (FastAPI). 외부 요청을 받아 셋으로 나눠 처리한다.

- **등록·수정** (`video_group` / `video`) — DB(MariaDB)에 직접 넣고 이 서버가 답한다.
- **분석·편성** (`video_file` / `compose`) — 뒷단 에이전트(agent-stt / agent-compose)로 그대로 넘기고
  응답을 그대로 돌려준다. 넘기기 전에 공정 중인 건이 있으면 409 로 거절한다.
- **상태 조회** (`status` / `status_compose`) — DB 를 읽어 이 서버가 답한다.

[English README](README.md)

## 호출 순서

**그룹 등록 → 영상 등록 → 영상 분석(video_file) → 상태 조회**

그룹 1건 = 드라마 시리즈 또는 야구 경기. 영상은 그 아래 회차(`order_no`)로 달린다.
카테고리(`cate_id`)와 완료 콜백(`callback_url`)은 영상이 아니라 그룹의 속성이다.
실제 파일(조각)은 `video_file` 호출 때 영상(`v_id`)에 붙는다 — 드라마는 VOD 한 파일, 야구는 이닝(1회초·1회말 …) 조각마다 한 번씩.
분석이 끝나면 `compose` 로 하이라이트 편성을 접수한다 — 그룹 단위(`v_g_id`)이고, 영상·조각을 골라 줄 수 있다.

## 엔드포인트

| 외부 URL | 처리 | 하는 일 |
|---|---|---|
| `POST /api/v1/video_group` | DB | 그룹 등록. `v_g_id` 발급 |
| `PUT /api/v1/video_group` | DB | 그룹 수정. 보낸 필드만 |
| `POST /api/v1/video` | DB | 영상 등록. `v_id` 발급 |
| `PUT /api/v1/video` | DB | 영상 수정. 보낸 필드만 |
| `POST /api/v1/video_file` | agent-stt `POST /api/v1/pre_svc` | 파일 등록 + 분석 시작 (download → ffmpeg 추출 → STT). 공정 중인 건이 있으면 409 |
| `POST /api/v1/compose` | agent-compose `POST /api/v1/compose` | 질의 기반 하이라이트 편성 접수. 결과는 `callback_url` 로. 편성 중 건수가 상한(`compose.py` 의 `_MAX_BUSY`) 이상이면 409 |
| `POST /api/v1/compose_ad` | agent-compose `POST /api/v1/compose-ad` | 광고 지점 편성 접수. 영상 1건 `{v_id, ad_items[{ad_cate_id, ad_item_id}]}`. 같은 `v_id` 가 편성 중이거나 편성 중 건수가 상한(`compose_ad.py` 의 `_MAX_BUSY`) 이상이면 409. 완료 통보 없음 — `status_compose_ad` 로 본다 |
| `GET /api/v1/status` | DB | 자막 공정 상태 (t_video_file) |
| `GET /api/v1/status_compose` | DB | 편성 상태 (t_compose) |
| `GET /api/v1/status_compose_ad` | DB | 광고 편성 상태 (t_compose_ad). `?comp_ad_id=` |

외부 이름과 뒷단 경로가 다른 건 `video_file → pre_svc` 와 `compose_ad → compose-ad` 둘이고, 그 매핑은 `config.py` 가 갖는다.
뒷단 경로가 바뀌면 `config.py` 의 `*_PATH` 한 줄만 고친다.

## 응답 형식

모든 응답은 `code` / `result` 쌍을 가진다. 성공은 `0` / `"OK"`, 실패는 `-1` / `"fail"` 에 요청 키(`v_g_id`, `v_id` 등)와 사유(`reason`)가 붙는다.

```json
{"code": 0, "result": "OK", "v_g_id": 12}
{"reason": "참조하는 행이 없다 (cate_id / v_g_id)", "v_g_id": 12, "code": -1, "result": "fail"}
```

HTTP 는 **404** 없음 / **409** 거절·충돌 / **422** 잘못된 값. 본문 형식 자체가 틀리면(필수 누락·타입·길이) FastAPI 기본 422(`detail` 배열)가 나간다.

## API

### `POST /api/v1/video_group` — 그룹 등록

| 필드 | 타입 | 설명 |
|---|---|---|
| `cate_id` | int | 필수. `t_category` 값 — 드라마 3000 / 야구 5100. 없는 값이면 422 |
| `name` | str | 필수. 1~100자 |
| `callback_url` | str | 선택. 200자 이하. 그룹 전체 공정 완료 콜백 |
| `comment` | str | 선택. 200자 이하 |

응답: `{"code": 0, "result": "OK", "v_g_id": 12}`

### `PUT /api/v1/video_group` — 그룹 수정

`v_g_id` 만 필수, 나머지는 위와 같은 필드가 전부 선택. **보낸 필드만 고친다** — 안 보낸 필드는 그대로, `null` 을 명시하면 NULL 로 지운다.
빈 본문(`v_g_id` 만)은 422, 없는 `v_g_id` 는 404.

### `POST /api/v1/video` — 영상 등록

| 필드 | 타입 | 설명 |
|---|---|---|
| `v_g_id` | int | 필수. 소속 그룹. 없는 값이면 422 |
| `name` | str | 필수. 1~50자 |
| `order_no` | int | 선택. 그룹 안 회차. 없으면 그 그룹의 MAX+1 (첫 영상은 1). 같은 그룹에 중복이면 409 |
| `play_year` | int | 선택. 방송 연도 |
| `stream_yn` | `Y`/`N` | 기본 `N`(VOD 한 파일). 야구처럼 조각으로 들어오면 `Y` |
| `comment` | str | 선택. 200자 이하 |

응답: `{"code": 0, "result": "OK", "v_id": 1012}`

### `PUT /api/v1/video` — 영상 수정

`v_id` 만 필수, 나머지 선택. 규칙은 그룹 수정과 같다 (보낸 필드만, `null` 은 지움, 빈 본문 422, 없으면 404).

### `POST /api/v1/video_file` → agent-stt `pre_svc` — 파일 등록 + 분석 시작

| 필드 | 타입 | 설명 |
|---|---|---|
| `v_id` | int | 필수. 미리 등록된 영상 |
| `file_path` | str | 필수. 5~200자. S3 **객체 키만** — `s3://버킷/` 을 붙이면 안 된다 |
| `stream_id` | str | `stream_yn=Y` 면 필수 (20자 이하, 예: `1top`). `N` 이면 무시하고 `VOD` 로 고정 |
| `last_yn` | `Y`/`N` | 마지막 조각에만 `Y`. 기본 `Y`. `stream_yn=N` 이면 `Y` 로 고정 |
| `forced_yn` | `Y`/`N` | `Y` 면 이미 등록된 조각(과 그 뒤)을 지우고 다시 처리. 기본 `Y` |

응답은 뒷단 것 그대로: `{"v_id": 1012, "stream_id": "VOD", "code": 0, "result": "OK"}` — 음성·프레임 추출이 끝난 뒤에 온다(수 분).
`code` 0 접수 / -1 거절. 대기열이 꽉 차면 HTTP 429 (`Retry-After` 헤더) 도 그대로 전달된다.
`t_video_file` 에 공정 중(`status_code` 2000~2090 / 3000~3090) 행이 하나라도 있으면 뒷단에 넘기지 않고 409 — 본문에 그 행의 `status_code` / `status_name` 이 붙는다.

### `POST /api/v1/compose` → agent-compose — 편성 접수

| 필드 | 타입 | 설명 |
|---|---|---|
| `v_g_id` | int | 필수. 편성 대상 그룹 |
| `videos` | list | 선택. 대상 영상 목록. 없으면 그룹 전체. `v_id` 중복 불가 |
| `videos[].v_id` | int | 필수. 그룹 안의 영상 |
| `videos[].stream_ids` | list[str] | 선택. 조각 지정 (각 20자 이하, 중복 불가). 없으면 그 영상의 파일 전부 |
| `query` | str | 필수. 1~1000자. 편성 질의. 예: `홈런 장면만` |
| `budget_sec` | int | 선택. 목표 분량(초). 없으면 절단하지 않는다 |
| `callback_url` | str | 선택. 200자 이하. 완료 시 결과 통보 |

```json
{"v_g_id": 12, "videos": [{"v_id": 1012, "stream_ids": ["1top", "1bot"]}], "query": "홈런 장면만", "budget_sec": 300, "callback_url": "http://sbs.co.kr/"}
```

응답은 뒷단 것 그대로: `{"comp_id": 7, "code": 0, "result": "OK"}` — `code` 0 접수 / -1 거절.
편성은 1~3분 걸리므로 접수만 하고 바로 응답한다. 완료 결과는 `callback_url` 로 통보된다.
`t_compose` 에 편성 중(`status_code` 4001 초과 4090 미만) 행이 상한(`compose.py` 의 `_MAX_BUSY`) 이상이면 뒷단에 넘기지 않고 409 — 본문에 `reason` 과 그 행의 `status_code` / `status_name` 이 붙는다.

### `POST /api/v1/compose_ad` → agent-compose `compose-ad` — 광고 지점 편성 접수

| 필드 | 타입 | 설명 |
|---|---|---|
| `v_id` | int | 필수. 편성 대상 영상 1건 |
| `ad_items` | list | 필수. 광고 목록, 최대 20줄. 한 줄이 광고 하나. 같은 (`ad_cate_id`, `ad_item_id`) 중복 불가 |
| `ad_items[].ad_cate_id` | int | 필수. 광고 카테고리 |
| `ad_items[].ad_item_id` | int | 선택. 광고 상품. `null` 이면 카테고리만 |

```json
{"v_id": 1036, "ad_items": [{"ad_cate_id": 1, "ad_item_id": 2}, {"ad_cate_id": 4, "ad_item_id": null}]}
```

응답은 뒷단 것 그대로: `{"comp_ad_id": 7, "code": 0, "result": "OK"}` — `code` 0 접수 / -1 거절.
완료 통보는 없다 — `GET /api/v1/status_compose_ad` 로 본다.
같은 `v_id` 가 편성 중(`status_code` 5001 초과 5090 미만)이거나, `t_compose_ad` 에 편성 중 행이 상한(`compose_ad.py` 의 `_MAX_BUSY`) 이상이면 뒷단에 넘기지 않고 409 — 본문에 `reason` 과 그 행의 `status_code` / `status_name` 이 붙는다.

### `GET /api/v1/status?v_id=1012&stream_id=VOD` — 자막 공정 상태

`v_id` / `stream_id` 둘 다 필수 (VOD 는 `stream_id=VOD`). `code` 는 `t_video_file.status_code`, `result` 는 그 코드의 `t_code.name`. 없으면 `-1` / `"fail"`.

```json
{"v_id": 1012, "stream_id": "VOD", "code": 2011, "result": "음성·이미지 추출 완료"}
```

### `GET /api/v1/status_compose?comp_id=7` — 편성 상태

`comp_id` 필수 (접수 응답의 `comp_id`). `code` / `result` 는 조회 성공 여부(0 / -1)이고, 편성 상태는 `status_code` 와 그 문구 `status_name`(`t_code.name`) 으로 온다. 없으면 `-1` / `"fail"` 만.

```json
{"comp_id": 7, "code": 0, "result": "OK", "status_code": 4000, "status_name": "편성 완료"}
```

### `GET /api/v1/status_compose_ad?comp_ad_id=7` — 광고 편성 상태

`comp_ad_id` 필수 (접수 응답의 `comp_ad_id`). 형식은 `status_compose` 와 같다 — `code` / `result` 는 조회 성공 여부, 편성 상태는 `status_code` / `status_name`. 5000 완료 / 5001 지점 없음 / 5010~5030 진행 중 / 5900 실패.

```json
{"comp_ad_id": 7, "code": 0, "result": "OK", "status_code": 5000, "status_name": "광고 지점 찾기 완료"}
```

## 소스 구조

```
main.py / config.py
lib/
  http/      외부에 노출되는 라우터 — 파일명 = 외부 경로 = 핸들러 이름
             video_group.py / video.py            DB CRUD (등록·수정)
             video_file.py / compose.py / compose_ad.py              뒷단 프록시 (공정 중이면 409 거절)
             status_svc.py / status_compose.py / status_compose_ad.py  DB 상태 조회
             http_util.py                         로깅 미들웨어 + 실패 응답 (fail_response / integrity_response)
             schema_resp.py                       응답 베이스 (code / result)
  rdb/       MariaDB — rdb.py(connect) + 테이블별 t_video_group / t_video / t_video_file / t_compose / t_compose_ad
  client/    뒷단 호출. proxy.py 하나 — 라운드로빈 + 그대로 전달 + 요청/응답 로그
  log.py     파일 + 콘솔 로거 (agent-stt 와 동일 포맷)
```

라우터 하나에 역할 하나. 새 뒷단 = `lib/http/<이름>.py` 라우터 + `config.py` 의 `*_UPSTREAM` / `*_PATH` + `main.py` 에 `include_router` 한 줄.
새 테이블 = `lib/rdb/t_<이름>.py` (연결은 각 함수 안에서 `with connect()`).

## 설계 요점

- **프록시는 가공 없음** — `video_file` / `compose` / `compose_ad` 는 method / path / query / header / body 를 그대로 넘기고 상태코드·본문을 그대로 돌려준다.
  hop-by-hop 헤더(`content-length`, `transfer-encoding`, `connection`)와 이 서버가 다시 붙이는 `date` / `server` 만 뺀다.
  요청 본문은 pydantic 모델로 형식만 검증하고(틀리면 뒷단에 안 가고 422), 통과하면 받은 본문 그대로 보낸다.
- **등록은 미리 SELECT 로 검사하지 않는다** — FK 없음 / UNIQUE 중복은 DB 가 거르고, 그 IntegrityError 를 `http_util._INTEGRITY` 가 422 / 409 로 옮긴다. DB 메시지는 로그에만.
- **수정은 보낸 필드만** — `model_dump(exclude_unset=True)`. '안 건드림' 과 '지움(`null`)' 을 구분한다.
- **공정 중 거절** — 넘기기 전에 `t_video_file` / `t_compose` / `t_compose_ad` 를 한 번 보고, 공정 중이면 409. 범위는 `t_video_file.BUSY_WHERE` / `compose._BUSY_WHERE` / `compose_ad._BUSY_WHERE` 한 곳. 동시 상한은 `compose._MAX_BUSY` / `compose_ad._MAX_BUSY` 로 조정한다.
- **upstream 은 배열** — nginx `upstream` 블록처럼 `.env` 에 JSON 배열로 적는다. 여러 대면 라운드로빈.
- **로그** — 프록시는 요청 본문 `[req]`, 응답 본문 `[res]` 를 그대로 찍는다. 미들웨어가 method+URL, 상태코드, 소요시간을 앞뒤로 남긴다.
- **전부 동기(def)** — 핸들러는 FastAPI 가 스레드풀에서 돌린다. 공유 리소스(httpx.Client / 라운드로빈 이터레이터)는 `main.py` 에서 1회 만들어 `app.state` 에. 로깅 미들웨어만 async (Starlette 제약).
- **DB 연결은 요청마다** — `with connect()` 로 짧게 열고 닫는다. 정상 종료 commit / 예외 rollback.
- **타임아웃** — `pre_svc` 는 ffmpeg 추출이 끝날 때까지 응답을 잡고 있으므로 `PROXY_TIMEOUT_S` 를 넉넉히(20분) 둔다.

## 설정 (.env)

`.env.example` 를 복사해 `.env` 로 만들고 값을 채운다. `config.py` 가 읽는 키는 전부 있어야 한다 — 하나라도 빠지면 기동 시 죽는다.

| 키 | 설명 |
|---|---|
| `HOST` / `PORT` | 이 서버 바인드 주소/포트 |
| `RDB_HOST` / `RDB_PORT` / `RDB_USER` / `RDB_PW` / `RDB_NAME` | MariaDB. agent-stt 와 같은 DB |
| `STT_UPSTREAM` | agent-stt 서버 배열. 예: `["http://10.0.0.1:19010", "http://10.0.0.2:19010"]` |
| `COMPOSE_UPSTREAM` | agent-compose 서버 배열. 예: `["http://127.0.0.1:8084"]` |

뒷단 **경로**(`/api/v1/pre_svc`, `/api/v1/compose`, `/api/v1/compose-ad`)는 `.env` 가 아니라 `config.py` 가 갖는다.

로그 파일: `/usr/service/logs/scenemaker/api_external/api_external.log`

## 실행

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 19000   # --reload 로 개발
```

## 테스트

`test.sh` 에 복사해 쓸 수 있는 예시가 있다 (그룹 등록·수정 / 영상 등록·수정 / 영상 분석 스트림·VOD / 편성 접수 / 광고 편성 접수 / 상태 조회).

```bash
# ① 그룹 등록 — 응답의 v_g_id 를 영상 등록에 쓴다
curl -X POST http://127.0.0.1:19000/api/v1/video_group \
  -H 'Content-Type: application/json' \
  -d '{"cate_id":5100,"name":"2026 KBO KT vs NC","callback_url":"http://sbs.co.kr/","comment":"정규시즌"}'

# ③ 영상 등록 — 야구는 이닝 조각으로 들어오므로 stream_yn=Y. 응답의 v_id 를 분석에 쓴다
curl -X POST http://127.0.0.1:19000/api/v1/video \
  -H 'Content-Type: application/json' \
  -d '{"v_g_id":12,"name":"2026 KBO KT vs NC","play_year":2026,"stream_yn":"Y"}'

# ⑤ 영상 분석 (1회초 조각) — agent-stt pre_svc 로 간다. 마지막 조각만 last_yn=Y
curl -X POST http://127.0.0.1:19000/api/v1/video_file \
  -H 'Content-Type: application/json' \
  -d '{"v_id":1012,"file_path":"vod/kbo/20260831_KT_NC/1top.mp4","stream_id":"1top","last_yn":"N","forced_yn":"Y"}'

# ⑦ 편성 접수 — agent-compose 로 간다. 그룹 단위, videos 를 빼면 그룹 전체. 완료는 callback_url 로
curl -X POST http://127.0.0.1:19000/api/v1/compose \
  -H 'Content-Type: application/json' \
  -d '{"v_g_id":12,"videos":[{"v_id":1012,"stream_ids":["1top","1bot"]}],"query":"홈런 장면만","budget_sec":300,"callback_url":"http://sbs.co.kr/"}'
```

## 요구사항

- Python >= 3.13, [uv](https://docs.astral.sh/uv/)
- MariaDB — agent-stt 와 같은 DB (`t_video_group` / `t_video` / `t_video_file` / `t_compose` / `t_code` / `t_category`)
- 뒷단: agent-stt, agent-compose

## 라이선스

[MIT](LICENSE)
