# api-external

An **external-facing API gateway** (FastAPI). Incoming requests fall into three kinds:

- **Register / update** (`video_group` / `video`) — written straight to the DB (MariaDB); this server answers.
- **Analyze / compose** (`video_file` / `compose`) — forwarded untouched to the backend agents
  (agent-stt / agent-compose), response returned untouched. Rejected with 409 before forwarding
  if a job is already in progress.
- **Status** (`status` / `status_compose`) — read from the DB; this server answers.

[한국어 README](README.ko.md)

## Call order

**register group → register video → analyze (video_file) → poll status**

One group = one drama series or one baseball game. Videos hang under it as episodes (`order_no`).
Category (`cate_id`) and completion callback (`callback_url`) belong to the group, not the video.
The actual file (piece) is attached to a video (`v_id`) by the `video_file` call — one VOD file for a
drama episode, one call per inning piece (top 1st, bottom 1st, …) for baseball.
Once analysis is done, `compose` accepts a highlight composition — per group (`v_g_id`), optionally
narrowed to chosen videos and pieces.

## Endpoints

| External URL | Handled by | What it does |
|---|---|---|
| `POST /api/v1/video_group` | DB | Register a group. Issues `v_g_id` |
| `PUT /api/v1/video_group` | DB | Update a group. Only the fields sent |
| `POST /api/v1/video` | DB | Register a video. Issues `v_id` |
| `PUT /api/v1/video` | DB | Update a video. Only the fields sent |
| `POST /api/v1/video_file` | agent-stt `POST /api/v1/pre_svc` | Attach a file and start analysis (download → ffmpeg extraction → STT). 409 if a job is in progress |
| `POST /api/v1/compose` | agent-compose `POST /api/v1/compose` | Accept a query-driven highlight composition. Result goes to `callback_url`. 409 when the number of running compositions reaches the cap (`_MAX_BUSY` in `compose.py`) |
| `POST /api/v1/compose_ad` | agent-compose `POST /api/v1/compose-ad` | Accept an ad-break composition for one video `{v_id, ad_items[{ad_cate_id, ad_item_id}]}`. 409 if that `v_id` is already running or the running count reaches the cap (`_MAX_BUSY` in `compose_ad.py`). No callback — poll `status_compose_ad` |
| `GET /api/v1/status` | DB | Subtitle pipeline status (t_video_file) |
| `GET /api/v1/status_compose` | DB | Composition status (t_compose) |
| `GET /api/v1/status_compose_ad` | DB | Ad composition status (t_compose_ad). `?comp_ad_id=` |

`video_file → pre_svc` and `compose_ad → compose-ad` are the only places the external name differs from
the backend path, and both mappings live in `config.py`. If a backend path changes, edit the one `*_PATH` line in `config.py`.

## Response format

Every response carries a `code` / `result` pair. Success is `0` / `"OK"`; failure is `-1` / `"fail"`
plus the request key (`v_g_id`, `v_id`, …) and a `reason`.

```json
{"code": 0, "result": "OK", "v_g_id": 12}
{"reason": "참조하는 행이 없다 (cate_id / v_g_id)", "v_g_id": 12, "code": -1, "result": "fail"}
```

HTTP: **404** not found / **409** rejected or conflict / **422** bad value. A malformed body
(missing required field, wrong type, too long) gets FastAPI's default 422 (`detail` array).

## API

### `POST /api/v1/video_group` — register a group

| Field | Type | Description |
|---|---|---|
| `cate_id` | int | required. A `t_category` value — drama 3000 / baseball 5100. Unknown value → 422 |
| `name` | str | required. 1–100 chars |
| `callback_url` | str | optional. ≤200 chars. Called when the whole group finishes |
| `comment` | str | optional. ≤200 chars |

Response: `{"code": 0, "result": "OK", "v_g_id": 12}`

### `PUT /api/v1/video_group` — update a group

Only `v_g_id` is required; the same fields as above are all optional. **Only the fields sent are
updated** — omitted fields are left alone, an explicit `null` clears the column.
A body with only `v_g_id` → 422; unknown `v_g_id` → 404.

### `POST /api/v1/video` — register a video

| Field | Type | Description |
|---|---|---|
| `v_g_id` | int | required. Parent group. Unknown value → 422 |
| `name` | str | required. 1–50 chars |
| `order_no` | int | optional. Episode number within the group. Omitted → MAX+1 (first video is 1). Duplicate within the group → 409 |
| `play_year` | int | optional. Broadcast year |
| `stream_yn` | `Y`/`N` | default `N` (one VOD file). `Y` when the video arrives in pieces, like baseball innings |
| `comment` | str | optional. ≤200 chars |

Response: `{"code": 0, "result": "OK", "v_id": 1012}`

### `PUT /api/v1/video` — update a video

Only `v_id` is required; the rest are optional. Same rules as the group update (only fields sent,
`null` clears, empty body 422, not found 404).

### `POST /api/v1/video_file` → agent-stt `pre_svc` — attach a file and start analysis

| Field | Type | Description |
|---|---|---|
| `v_id` | int | required. An already-registered video |
| `file_path` | str | required. 5–200 chars. S3 **object key only** — no `s3://bucket/` prefix |
| `stream_id` | str | required when `stream_yn=Y` (≤20 chars, e.g. `1top`). Ignored and fixed to `VOD` when `N` |
| `last_yn` | `Y`/`N` | `Y` on the final piece only. Default `Y`. Forced to `Y` when `stream_yn=N` |
| `forced_yn` | `Y`/`N` | `Y` deletes an already-registered piece (and those after it) and re-processes. Default `Y` |

The response is the backend's, untouched: `{"v_id": 1012, "stream_id": "VOD", "code": 0, "result": "OK"}` —
it arrives after audio/frame extraction finishes (minutes). `code` `0` accepted / `-1` rejected.
HTTP 429 with a `Retry-After` header (queue full) is passed through as well.
If any `t_video_file` row is in progress (`status_code` 2000–2090 / 3000–3090) the request is not
forwarded and gets 409, with that row's `status_code` / `status_name` in the body.

### `POST /api/v1/compose` → agent-compose — accept a composition

| Field | Type | Description |
|---|---|---|
| `v_g_id` | int | required. The group to compose from |
| `videos` | list | optional. Target videos. Omitted → the whole group. No duplicate `v_id` |
| `videos[].v_id` | int | required. A video in that group |
| `videos[].stream_ids` | list[str] | optional. Specific pieces (each ≤20 chars, no duplicates). Omitted → every file of that video |
| `query` | str | required. 1–1000 chars. Composition query, e.g. `홈런 장면만` |
| `budget_sec` | int | optional. Target length in seconds; no trimming when omitted |
| `callback_url` | str | optional. ≤200 chars. Result is posted here on completion |

```json
{"v_g_id": 12, "videos": [{"v_id": 1012, "stream_ids": ["1top", "1bot"]}], "query": "홈런 장면만", "budget_sec": 300, "callback_url": "http://sbs.co.kr/"}
```

The response is the backend's, untouched: `{"comp_id": 7, "code": 0, "result": "OK"}` — `code` `0` accepted / `-1` rejected.
Composition takes 1–3 minutes, so POST only accepts and returns immediately. The result is
posted to `callback_url` on completion. If the number of `t_compose` rows in progress reaches the cap (`_MAX_BUSY` in `compose.py`)
(`status_code` between 4001 and 4090, exclusive) the request is not forwarded and gets 409, with a
`reason` and that row's `status_code` / `status_name` in the body.

### `POST /api/v1/compose_ad` → agent-compose `compose-ad` — accept an ad-break composition

| Field | Type | Description |
|---|---|---|
| `v_id` | int | required. The single video to compose for |
| `ad_items` | list | required. One entry per ad, at most 20. No duplicate (`ad_cate_id`, `ad_item_id`) pair |
| `ad_items[].ad_cate_id` | int | required. Ad category |
| `ad_items[].ad_item_id` | int | optional. Ad product. `null` → category only |

```json
{"v_id": 1036, "ad_items": [{"ad_cate_id": 1, "ad_item_id": 2}, {"ad_cate_id": 4, "ad_item_id": null}]}
```

The response is the backend's, untouched: `{"comp_ad_id": 7, "code": 0, "result": "OK"}` — `code` `0` accepted / `-1` rejected.
There is no callback — poll `GET /api/v1/status_compose_ad`.
If that `v_id` is already in progress (`status_code` between 5001 and 5090, exclusive), or the number
of `t_compose_ad` rows in progress reaches the cap (`_MAX_BUSY` in `compose_ad.py`), the request is not
forwarded and gets 409, with a `reason` and that row's `status_code` / `status_name` in the body.

### `GET /api/v1/status?v_id=1012&stream_id=VOD` — subtitle pipeline status

Both `v_id` and `stream_id` are required (`stream_id=VOD` for VOD). `code` is
`t_video_file.status_code`, `result` is that code's `t_code.name`. Not found → `-1` / `"fail"`.

```json
{"v_id": 1012, "stream_id": "VOD", "code": 2011, "result": "음성·이미지 추출 완료"}
```

### `GET /api/v1/status_compose?comp_id=7` — composition status

`comp_id` is required (the `comp_id` from the accept response). `code` / `result` say whether the
lookup succeeded (0 / -1); the composition state comes as `status_code` plus its label
`status_name` (`t_code.name`). Not found → just `-1` / `"fail"`.

```json
{"comp_id": 7, "code": 0, "result": "OK", "status_code": 4000, "status_name": "편성 완료"}
```

### `GET /api/v1/status_compose_ad?comp_ad_id=7` — ad composition status

`comp_ad_id` is required (the `comp_ad_id` from the accept response). Same shape as `status_compose`:
`code` / `result` say whether the lookup succeeded, the state comes as `status_code` / `status_name`.
5000 done / 5001 no break found / 5010–5030 in progress / 5900 failed.

```json
{"comp_ad_id": 7, "code": 0, "result": "OK", "status_code": 5000, "status_name": "광고 지점 찾기 완료"}
```

## Source layout

```
main.py / config.py
lib/
  http/      externally exposed routers — file name = external path = handler name
             video_group.py / video.py            DB CRUD (register / update)
             video_file.py / compose.py / compose_ad.py              backend proxies (409 while a job is in progress)
             status_svc.py / status_compose.py / status_compose_ad.py  DB status lookups
             http_util.py                         logging middleware + failure responses (fail_response / integrity_response)
             schema_resp.py                       response base (code / result)
  rdb/       MariaDB — rdb.py (connect) + one module per table: t_video_group / t_video / t_video_file / t_compose / t_compose_ad
  client/    backend calls. A single proxy.py — round-robin + pass-through + request/response log
  log.py     file + console logger (same format as agent-stt)
```

One router, one job. A new backend = a `lib/http/<name>.py` router + `*_UPSTREAM` / `*_PATH` in
`config.py` + one `include_router` line in `main.py`. A new table = `lib/rdb/t_<name>.py` (each
function opens its own `with connect()`).

## Design notes

- **Proxies do not transform** — `video_file` / `compose` / `compose_ad` forward method / path / query / headers /
  body as-is and return status code and body as-is. Only hop-by-hop headers (`content-length`,
  `transfer-encoding`, `connection`) and the `date` / `server` headers this server re-adds are dropped.
  The request body is shape-checked by a pydantic model first (a bad body gets 422 without reaching
  the backend); once it passes, the original bytes are forwarded.
- **Registration does not pre-check with SELECT** — missing FK / duplicate UNIQUE are caught by the
  DB, and `http_util._INTEGRITY` maps that IntegrityError to 422 / 409. The DB message goes to the
  log only.
- **Updates touch only the fields sent** — `model_dump(exclude_unset=True)`, so "leave alone" and
  "clear (`null`)" are distinct.
- **Busy rejection** — `t_video_file` / `t_compose` / `t_compose_ad` are checked once before forwarding;
  409 if a job is in progress. The ranges live in one place each: `t_video_file.BUSY_WHERE` /
  `compose._BUSY_WHERE` / `compose_ad._BUSY_WHERE`. The concurrency caps are `compose._MAX_BUSY` /
  `compose_ad._MAX_BUSY`.
- **Upstream is an array** — written as a JSON array in `.env`, like an nginx `upstream` block.
  Multiple servers are round-robined.
- **Logging** — proxies log the request body as `[req]` and the response body as `[res]`, verbatim.
  Middleware brackets each call with method+URL, status code, and elapsed time.
- **Everything is sync (`def`)** — FastAPI runs handlers in its thread pool. Shared resources
  (httpx.Client / round-robin iterator) are built once in `main.py` and kept on `app.state`. Only
  the logging middleware is async (a Starlette constraint).
- **One DB connection per request** — `with connect()`, opened and closed briefly. Commit on normal
  exit, rollback on exception.
- **Timeout** — `pre_svc` holds the response until ffmpeg extraction finishes, so
  `PROXY_TIMEOUT_S` is generous (20 minutes).

## Configuration (.env)

Copy `.env.example` to `.env` and fill it in. Every key `config.py` reads must be present — a
missing one kills startup.

| Key | Description |
|---|---|
| `HOST` / `PORT` | bind address/port for this server |
| `RDB_HOST` / `RDB_PORT` / `RDB_USER` / `RDB_PW` / `RDB_NAME` | MariaDB. The same DB agent-stt uses |
| `STT_UPSTREAM` | agent-stt server array, e.g. `["http://10.0.0.1:19010", "http://10.0.0.2:19010"]` |
| `COMPOSE_UPSTREAM` | agent-compose server array, e.g. `["http://127.0.0.1:8084"]` |

Backend **paths** (`/api/v1/pre_svc`, `/api/v1/compose`, `/api/v1/compose-ad`) live in `config.py`, not `.env`.

Log file: `/usr/service/logs/scenemaker/api_external/api_external.log`

## Running

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 19000   # add --reload for development
```

## Testing

See `test.sh` for ready-to-paste examples (group register/update, video register/update,
analysis for a stream piece and for VOD, composition accept, both status lookups).

```bash
# ① Register a group — use the returned v_g_id to register videos
curl -X POST http://127.0.0.1:19000/api/v1/video_group \
  -H 'Content-Type: application/json' \
  -d '{"cate_id":5100,"name":"2026 KBO KT vs NC","callback_url":"http://sbs.co.kr/","comment":"정규시즌"}'

# ③ Register a video — baseball arrives in inning pieces, so stream_yn=Y. Use the returned v_id for analysis
curl -X POST http://127.0.0.1:19000/api/v1/video \
  -H 'Content-Type: application/json' \
  -d '{"v_g_id":12,"name":"2026 KBO KT vs NC","play_year":2026,"stream_yn":"Y"}'

# ⑤ Analyze (top of the 1st) — goes to agent-stt pre_svc. last_yn=Y on the final piece only
curl -X POST http://127.0.0.1:19000/api/v1/video_file \
  -H 'Content-Type: application/json' \
  -d '{"v_id":1012,"file_path":"vod/kbo/20260831_KT_NC/1top.mp4","stream_id":"1top","last_yn":"N","forced_yn":"Y"}'

# ⑦ Accept a composition — goes to agent-compose. Per group; omit videos for the whole group. Result goes to callback_url
curl -X POST http://127.0.0.1:19000/api/v1/compose \
  -H 'Content-Type: application/json' \
  -d '{"v_g_id":12,"videos":[{"v_id":1012,"stream_ids":["1top","1bot"]}],"query":"홈런 장면만","budget_sec":300,"callback_url":"http://sbs.co.kr/"}'
```

## Requirements

- Python >= 3.13, [uv](https://docs.astral.sh/uv/)
- MariaDB — the same DB agent-stt uses (`t_video_group` / `t_video` / `t_video_file` / `t_compose` / `t_code` / `t_category`)
- Backends: agent-stt, agent-compose

## License

[MIT](LICENSE)
