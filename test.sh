#!/bin/bash
# 호출 예시 — 필요한 블록만 복사해서 붙여넣는다. 순서: 그룹 등록 → 영상 등록 → 영상 분석(video_file) → 편성 접수(compose) → 상태 조회.
#   video_group / video / status* 는 이 서버가 DB 를 직접 보고 답한다. video_file / compose 는 뒷단(agent-stt / agent-compose) 응답을 그대로 돌려준다 (code 0=접수 / -1=거절).
#   게이트웨이 포트는 .env 의 PORT (기본 19000).

# ── ① 영상 그룹 등록 — 드라마 시리즈 또는 야구 경기 1건. 응답의 v_g_id 를 ③ 에 쓴다. cate_id: 드라마 3000 / 야구 5100
curl -X POST http://127.0.0.1:19000/api/v1/video_group \
  -H 'Content-Type: application/json' \
  -d '{
    "cate_id": 5100,
    "name": "2026 KBO KT vs NC",
    "callback_url": "http://sbs.co.kr/",
    "comment": "정규시즌"
  }'


# ── ② 영상 그룹 수정 — v_g_id 만 필수. 보낸 필드만 고치고 나머지는 그대로. null 을 보내면 그 값을 지운다
# curl -X PUT http://127.0.0.1:19000/api/v1/video_group \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_g_id": 12,
#     "name": "2026 KBO KT vs NC (수정)",
#     "comment": null
#   }'


# ── ③ 영상 등록 — 그룹 아래 회차 1건. order_no 를 빼면 그 그룹의 마지막 회차 + 1. 야구는 조각(이닝)으로 들어오므로 stream_yn='Y'. 응답의 v_id 를 ⑤⑥ 에 쓴다
# curl -X POST http://127.0.0.1:19000/api/v1/video \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_g_id": 12,
#     "name": "2026 KBO KT vs NC",
#     "play_year": 2026,
#     "stream_yn": "Y",
#     "comment": "8월 31일 경기"
#   }'


# ── ④ 영상 수정 — v_id 만 필수. 보낸 필드만 고친다
# curl -X PUT http://127.0.0.1:19000/api/v1/video \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_id": 1012,
#     "name": "2026 KBO KT vs NC (수정)"
#   }'


# ── ⑤ 영상 분석 (스트림 조각, 프로야구) — agent-stt pre_svc 로 간다. stream_yn='Y' 영상은 조각마다 한 번씩, stream_id 로 구분(1top, 1bot, 2top …). 마지막 조각만 last_yn='Y'
#    응답은 음성·프레임 추출이 끝난 뒤 온다: {"v_id":1012,"stream_id":"1top","code":0,"result":"OK"}
# curl -X POST http://127.0.0.1:19000/api/v1/video_file \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_id": 1012,
#     "file_path": "vod/kbo/20260831_KT_NC/1top.mp4",
#     "stream_id": "1top",
#     "last_yn": "N",
#     "forced_yn": "Y"
#   }'


# ── ⑥ 영상 분석 (VOD, 드라마) — stream_yn='N' 으로 등록한 영상. 파일 하나로 끝. stream_id 는 안 준다 (VOD 로 고정)
#    응답: {"v_id":1012,"stream_id":"VOD","code":0,"result":"OK"}
# curl -X POST http://127.0.0.1:19000/api/v1/video_file \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_id": 1012,
#     "file_path": "vod/drama/kimbujang_01.mp4",
#     "last_yn": "Y",
#     "forced_yn": "Y"
#   }'


# ── ⑦ 편성 접수 — agent-compose 로 간다. 그룹 단위(v_g_id). videos 를 빼면 그룹 전체, stream_ids 를 빼면 그 영상의 파일 전부. 완료는 callback_url 로 통보
#    응답: {"comp_id":7,"code":0,"result":"OK"} / 편성 중 건수가 상한(compose._MAX_BUSY) 이상이면 뒷단에 안 넘기고 409
# curl -X POST http://127.0.0.1:19000/api/v1/compose \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_g_id": 12,
#     "videos": [{"v_id": 1012, "stream_ids": ["1top", "1bot"]}],
#     "query": "홈런 장면만",
#     "budget_sec": 300,
#     "callback_url": "http://sbs.co.kr/"
#   }'


# ── ⑧ 자막 공정 상태 조회 (t_video_file) — v_id, stream_id 둘 다 필수. VOD 는 stream_id=VOD, 스트림은 조각의 stream_id
#    응답: {"v_id":1012,"stream_id":"VOD","code":2011,"result":"음성·이미지 추출 완료"} / 없으면 code -1
# curl 'http://127.0.0.1:19000/api/v1/status?v_id=1012&stream_id=VOD'


# ── ⑨ 편성 상태 조회 (t_compose) — comp_id 필수 (편성 접수 응답의 comp_id). code/result 는 조회 성공 여부, 편성 상태는 status_code/status_name
#    응답: {"comp_id":7,"code":0,"result":"OK","status_code":4000,"status_name":"편성 완료"} / 없으면 {"comp_id":7,"code":-1,"result":"fail"}
# curl 'http://127.0.0.1:19000/api/v1/status_compose?comp_id=7'


# ── ⑩ 광고 지점 편성 접수 — agent-compose /api/v1/compose-ad 로 간다. 영상 1건(v_id). ad_items 한 줄이 광고 하나:
#    ad_item_id 를 null 로 두면 카테고리만. 같은 (ad_cate_id, ad_item_id) 두 번은 422.
#    같은 v_id 가 편성 중(5001 초과 5090 미만)이거나 편성 중 건수가 상한(compose_ad._MAX_BUSY) 이상이면 409. 완료 통보 없음 — ⑪ 로 본다
#    응답: {"comp_ad_id":7,"code":0,"result":"OK"} / 거절 {"code":-1,"result":"fail","reason":"..."}
# curl -X POST http://127.0.0.1:19000/api/v1/compose_ad \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "v_id": 1036,
#     "ad_items": [
#       {"ad_cate_id": 1, "ad_item_id": 2},
#       {"ad_cate_id": 1, "ad_item_id": 1},
#       {"ad_cate_id": 4, "ad_item_id": null}
#     ]
#   }'


# ── ⑪ 광고 편성 상태 조회 (t_compose_ad) — comp_ad_id 필수. 5000 완료 / 5001 지점 없음 / 5010~5030 진행 / 5900 실패
#    응답: {"comp_ad_id":7,"code":0,"result":"OK","status_code":5000,"status_name":"광고 지점 찾기 완료"} / 없으면 {"comp_ad_id":7,"code":-1,"result":"fail"}
# curl 'http://127.0.0.1:19000/api/v1/status_compose_ad?comp_ad_id=7'
