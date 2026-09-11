# api-external

An **external-facing API gateway** (FastAPI). Plays the role of an nginx reverse proxy — forwards
incoming requests to the backend agents (agent-stt / agent-compose) untouched and returns their
responses untouched. No transformation. All it adds is a log of every request and response body.

[한국어 README](README.ko.md)

## Two backends

| External URL | Backend | Backend URL | What it does |
|---|---|---|---|
| `POST /api/v1/stt_svc` | agent-stt | `POST /api/v1/pre_svc` | First call. Registers the video → download → ffmpeg (audio/frame extraction). With `STT_TRIGGER=true` on agent-stt, the subtitle pipeline follows on its own |
| `POST /api/v1/compose` | agent-compose | `POST /api/v1/compose` | Accepts a query-driven highlight composition. The result is posted to `callback_url` |

`stt_svc → pre_svc` is the only place the external name differs from the backend path, and that
mapping lives in `config.py`. If a backend path changes, edit the one `*_PATH` line in `config.py`.

## API

Responses are passed through as-is, so the body formats are defined by each agent's README.
Only a summary is given here.

### `POST /api/v1/stt_svc` → agent-stt `pre_svc`

| Field | Type | Description |
|---|---|---|
| `v_id` | int | `-100` to issue a new one; a positive value must already exist |
| `file_path` | str | S3 **object key only** — no `s3://bucket/` prefix |
| `title` | str | 5–45 chars |
| `category` | str | 6–45 chars, e.g. `스포츠-야구` |
| `year` | int | broadcast year |
| `stream_mode` | `Y`/`N` | `N` = whole video, `Y` = one piece of a stream |
| `stream_id` | str | required when `stream_mode=Y` |
| `stream_last` | `Y`/`N` | `Y` on the final piece |
| `forced_yn` | `Y`/`N` | `Y` re-processes a piece already registered |
| `callback_url` | str | optional, ≤200 chars |

Response: `{"v_id": 1012, "stream_id": "VOD", "code": 0, "result": "OK"}` — `code` `0` accepted /
`-1` rejected. HTTP 429 with a `Retry-After` header (queue full) is passed through as well.

### `POST /api/v1/compose` → agent-compose

| Field | Type | Description |
|---|---|---|
| `v_id` | int | an already-registered video |
| `query` | str | composition query, e.g. `홈런 장면만` |
| `stream_id` | str | default `VOD` |
| `budget_sec` | int | optional. Target length in seconds; no trimming when omitted |
| `callback_url` | str | optional. Result is posted here on completion |

Response: `{"v_id": 1012, "stream_id": "VOD", "search_id": "…", "code": 0, "result": "OK"}`.
Composition takes 1–3 minutes, so POST only accepts and returns immediately. The result is
posted to `callback_url` on completion.

## Source layout

```
main.py / config.py
lib/
  http/      externally exposed routers — pick the path only; body and response go to client
             stt_svc.py / compose.py
  client/    backend calls. A single proxy.py — round-robin + pass-through + request/response log
  log.py     file + console logger (same format as agent-stt)
```

One router, one backend path. A new backend = a `lib/http/<name>.py` router + `*_UPSTREAM` /
`*_PATH` in `config.py` + one `include_router` line in `main.py`.

## Design notes

- **No transformation** — method / path / query / headers / body are forwarded as-is; status code
  and body come back as-is. Only hop-by-hop headers (`content-length`, `transfer-encoding`,
  `connection`) and the `date` / `server` headers this server re-adds are dropped.
- **Upstream is an array** — written as a JSON array in `.env`, like an nginx `upstream` block.
  Multiple servers are round-robined.
- **Logging** — the request body is logged as `[req]`, the response body as `[res]`, verbatim.
  Middleware brackets each call with method+URL, status code, and elapsed time.
- **Shared resources** (httpx.AsyncClient / round-robin iterator) are built once in `lifespan`
  and shared through `app.state`.
- **Timeout** — `pre_svc` holds the response until ffmpeg extraction finishes, so
  `PROXY_TIMEOUT_S` is generous (20 minutes).

## Configuration (.env)

Copy `.env.example` to `.env` and fill it in.

| Key | Description |
|---|---|
| `HOST` / `PORT` | bind address/port for this server |
| `STT_UPSTREAM` | agent-stt server array, e.g. `["http://10.0.0.1:19010", "http://10.0.0.2:19010"]` |
| `COMPOSE_UPSTREAM` | agent-compose server array, e.g. `["http://127.0.0.1:8084"]` |

Backend **paths** (`/api/v1/pre_svc`, `/api/v1/compose`) live in `config.py`, not `.env`.

Log file: `/usr/service/logs/scenemaker/api_external/api_external.log`

## Running

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 19000   # add --reload for development
```

## Testing

See `test.sh` for ready-to-paste examples (STT VOD / STT stream / compose / both status lookups).

```bash
# First call — goes to agent-stt pre_svc
curl -X POST http://127.0.0.1:19000/api/v1/stt_svc \
  -H 'Content-Type: application/json' \
  -d '{"v_id":-100,"file_path":"vod_sbin/202607/game.mp4","title":"KBO 삼성-두산",
       "category":"스포츠-야구","year":2026,"stream_mode":"N","stream_last":"Y",
       "forced_yn":"Y","callback_url":"http://solbox.com"}'

# Accept a composition
curl -X POST http://127.0.0.1:19000/api/v1/compose \
  -H 'Content-Type: application/json' \
  -d '{"v_id":1012,"query":"홈런 장면만","stream_id":"VOD","budget_sec":300,"callback_url":"http://solbox.com"}'
```

## Requirements

- Python >= 3.13, [uv](https://docs.astral.sh/uv/)
- Backends: agent-stt, agent-compose

## License

[MIT](LICENSE)
