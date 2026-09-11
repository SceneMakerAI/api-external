# api-external

**외부 공개 API 게이트웨이** (FastAPI). nginx reverse proxy 역할 — 외부에서 들어온 요청을
뒷단 에이전트(agent-stt / agent-compose)로 그대로 넘기고, 응답을 그대로 돌려준다.
가공은 없다. 요청·응답 본문을 로그에 남기는 것이 전부다.

[English README](README.md)

## 뒷단은 둘이다

| 외부 URL | 뒷단 | 뒷단 URL | 하는 일 |
|---|---|---|---|
| `POST /api/v1/stt_svc` | agent-stt | `POST /api/v1/pre_svc` | 최초 호출. 영상 등록 → download → ffmpeg(음성·프레임 추출). agent-stt 의 `STT_TRIGGER=true` 면 자막 공정까지 이어 돈다 |
| `POST /api/v1/compose` | agent-compose | `POST /api/v1/compose` | 질의 기반 하이라이트 편성 접수. 결과는 `callback_url` 로 통보된다 |

외부 이름과 뒷단 경로가 다른 건 `stt_svc → pre_svc` 하나뿐이고, 그 매핑은 `config.py` 가 갖는다.
뒷단 경로가 바뀌면 `config.py` 의 `*_PATH` 한 줄만 고친다.

## API

응답은 뒷단 것을 그대로 돌려주므로 본문 형식은 각 에이전트 README 를 따른다.
여기서는 요약만 적는다.

### `POST /api/v1/stt_svc` → agent-stt `pre_svc`

| 필드 | 타입 | 설명 |
|---|---|---|
| `v_id` | int | `-100` 이면 신규 발급. 양수면 이미 등록된 것이어야 한다 |
| `file_path` | str | S3 **객체 키만** — `s3://버킷/` 을 붙이면 안 된다 |
| `title` | str | 5~45자 |
| `category` | str | 6~45자. 예: `스포츠-야구` |
| `year` | int | 방송 연도 |
| `stream_mode` | `Y`/`N` | `N`=영상 전체, `Y`=스트림 조각 하나 |
| `stream_id` | str | `stream_mode=Y` 면 필수 |
| `stream_last` | `Y`/`N` | 마지막 조각에만 `Y` |
| `forced_yn` | `Y`/`N` | `Y` 면 이미 등록된 조각을 다시 처리한다 |
| `callback_url` | str | 선택, 200자 이하 |

응답: `{"v_id": 1012, "stream_id": "VOD", "code": 0, "result": "OK"}` — `code` 0 접수 / -1 거절.
대기열이 꽉 차면 HTTP 429 (`Retry-After` 헤더) 도 그대로 전달된다.

### `POST /api/v1/compose` → agent-compose

| 필드 | 타입 | 설명 |
|---|---|---|
| `v_id` | int | 이미 등록된 영상 |
| `query` | str | 편성 질의. 예: `홈런 장면만` |
| `stream_id` | str | 기본 `VOD` |
| `budget_sec` | int | 선택. 목표 분량(초). 없으면 절단하지 않는다 |
| `callback_url` | str | 선택. 완료 시 결과 통보 |

응답: `{"v_id": 1012, "stream_id": "VOD", "search_id": "…", "code": 0, "result": "OK"}`.
편성은 1~3분 걸리므로 접수만 하고 바로 응답한다. 완료 결과는 `callback_url` 로 통보된다.

## 소스 구조

```
main.py / config.py
lib/
  http/      외부에 노출되는 라우터 — 경로만 정하고 본문·응답은 client 로 넘긴다
             stt_svc.py / compose.py
  client/    뒷단 호출. proxy.py 하나 — 라운드로빈 + 그대로 전달 + 요청/응답 로그
  log.py     파일 + 콘솔 로거 (agent-stt 와 동일 포맷)
```

라우터 하나에 뒷단 경로 하나. 새 뒷단 = `lib/http/<이름>.py` 라우터 + `config.py` 의
`*_UPSTREAM` / `*_PATH` + `main.py` 에 `include_router` 한 줄.

## 설계 요점

- **가공 없음** — method / path / query / header / body 를 그대로 넘기고 상태코드·본문을 그대로 돌려준다.
  hop-by-hop 헤더(`content-length`, `transfer-encoding`, `connection`)와 이 서버가 다시 붙이는 `date` / `server` 만 뺀다.
- **upstream 은 배열** — nginx `upstream` 블록처럼 `.env` 에 JSON 배열로 적는다. 여러 대면 라운드로빈.
- **로그** — 요청 본문 `[req]`, 응답 본문 `[res]` 를 그대로 찍는다. 미들웨어가 method+URL, 상태코드, 소요시간을 앞뒤로 남긴다.
- **공유 리소스**(httpx.AsyncClient / 라운드로빈 이터레이터)는 `lifespan` 에서 1회 생성해 `app.state` 로.
- **타임아웃** — `pre_svc` 는 ffmpeg 추출이 끝날 때까지 응답을 잡고 있으므로 `PROXY_TIMEOUT_S` 를 넉넉히(20분) 둔다.

## 설정 (.env)

`.env.example` 를 복사해 `.env` 로 만들고 값을 채운다.

| 키 | 설명 |
|---|---|
| `HOST` / `PORT` | 이 서버 바인드 주소/포트 |
| `STT_UPSTREAM` | agent-stt 서버 배열. 예: `["http://10.0.0.1:19010", "http://10.0.0.2:19010"]` |
| `COMPOSE_UPSTREAM` | agent-compose 서버 배열. 예: `["http://127.0.0.1:8084"]` |

뒷단 **경로**(`/api/v1/pre_svc`, `/api/v1/compose`)는 `.env` 가 아니라 `config.py` 가 갖는다.

로그 파일: `/usr/service/logs/scenemaker/api_external/api_external.log`

## 실행

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 19000   # --reload 로 개발
```

## 테스트

`test.sh` 에 복사해 쓸 수 있는 예시가 있다 (STT VOD / STT 스트림 / 편성 / 상태 조회 둘).

```bash
# 최초 호출 — agent-stt pre_svc 로 간다
curl -X POST http://127.0.0.1:19000/api/v1/stt_svc \
  -H 'Content-Type: application/json' \
  -d '{"v_id":-100,"file_path":"vod_sbin/202607/game.mp4","title":"KBO 삼성-두산",
       "category":"스포츠-야구","year":2026,"stream_mode":"N","stream_last":"Y",
       "forced_yn":"Y","callback_url":"http://solbox.com"}'

# 편성 접수
curl -X POST http://127.0.0.1:19000/api/v1/compose \
  -H 'Content-Type: application/json' \
  -d '{"v_id":1012,"query":"홈런 장면만","stream_id":"VOD","budget_sec":300,"callback_url":"http://solbox.com"}'
```

## 요구사항

- Python >= 3.13, [uv](https://docs.astral.sh/uv/)
- 뒷단: agent-stt, agent-compose

## 라이선스

[MIT](LICENSE)
