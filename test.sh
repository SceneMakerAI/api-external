#!/bin/bash
# 호출 예시 — 필요한 블록만 복사해서 붙여넣는다. 응답은 뒷단 것을 그대로 돌려준다 (code 0=접수 / -1=거절).
#   게이트웨이 포트는 .env 의 PORT (기본 19000).

# ── ① STT 최초 호출 (VOD, stream_mode='N') — agent-stt pre_svc 로 간다. v_id -100 은 신규 발급
curl -X POST http://127.0.0.1:19000/api/v1/stt_svc \
  -H 'Content-Type: application/json' \
  -d '{
    "v_id": -100,
    "file_path": "vod_sbin/202607/20260726_kbs_SAMSUNG_DOOSAN/20260726_kbs_SAMSUNG_DOOSAN.mp4",
    "title": "KBS_20260902_KBO_삼성_두산",
    "category": "스포츠-야구",
    "year": 2026,
    "stream_mode": "N",
    "stream_last": "Y",
    "forced_yn": "Y",
    "callback_url": "http://solbox.com"
  }'


# ── ② STT 스트림 (stream_mode='Y') — 조각마다 stream_id, 마지막 조각만 stream_last='Y'
# curl -X POST http://127.0.0.1:19000/api/v1/stt_svc \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_id": 1012,
#     "file_path": "vod_sbin/202607/game/1top.mp4",
#     "title": "KBS_20260902_KBO_삼성_두산",
#     "category": "스포츠-야구",
#     "year": 2026,
#     "stream_mode": "Y",
#     "stream_id": "1top",
#     "stream_last": "N",
#     "forced_yn": "Y",
#     "callback_url": "http://solbox.com"
#   }'


# ── ③ 편성 접수 — agent-compose 로 간다. 완료 결과는 callback_url 로 통보
# curl -X POST http://127.0.0.1:19000/api/v1/compose \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_id": 1012,
#     "query": "홈런 장면만",
#     "stream_id": "VOD",
#     "budget_sec": 300,
#     "callback_url": "http://solbox.com"
#   }'


# ── ④ 자막 공정 상태 조회 (t_video_file) — v_id, stream_id 둘 다 필수. VOD 는 stream_id=VOD
#    응답: {"v_id":1012,"stream_id":"VOD","code":2011,"result":"음성·이미지 추출 완료"} / 없으면 code -1
# curl 'http://127.0.0.1:19000/api/v1/status?v_id=1012&stream_id=VOD'


# ── ⑤ 편성 상태 조회 (t_compose) — 두 형태 중 하나만 (섞거나 하나만 주면 422)
#    ⑤-1 search_id 만 — 편성 접수 응답의 search_id
# curl 'http://127.0.0.1:19000/api/v1/status_compose?search_id=20260911-1012-1'
#    ⑤-2 v_id + stream_id 둘 다
# curl 'http://127.0.0.1:19000/api/v1/status_compose?v_id=1012&stream_id=VOD'
