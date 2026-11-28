"""공통 프로토콜 v3 - 엔지니어 관점이 마스터, 컴퓨터 · 유지보수 관점은 번역본 (v13.8, 사용자 결정 2026-11-27).

  마스터 (사람이 고치고 승인하는 유일한 원본) = 엔지니어 관점, 설계실 가이드 Rule 양식에 맞춘 칸:
      대상 (title + 적용 범위) · 조건 (preconditions) · 할 일 (steps, 순서) · 예외 (exceptions) · 판정 (PASS / INFO / HOLD)
      · 근거 (evidence) · 상태 · 승인 (status DRAFT / APPROVED, approved_by, approval_date) · 기준값 (params)
  번역본 = 컴퓨터 관점 (회사 AI · 개발자), 유지보수 관점 (도구 관리자)
      - 마스터를 옮긴 것. 마스터와 다르면 항상 마스터가 맞다 (번역 오류로 보고 번역본을 고친다). 직접 고치지 않는다.
      - from_master = 번역할 때의 마스터 지문. 마스터가 바뀌면 자동으로 '다시 번역 필요'.
      - 상태: 확인 필요 (AI·도구가 번역, 사람 확인 전) / 확정 (사람 확인) / 다시 번역 필요 / 질문 있음 (애매해서 마스터에 물음)
      - 번역하다 애매하면 짐작하지 않고 questions에 적는다 → 엔지니어가 마스터를 고쳐야 확정.
  숫자 기준은 params 한 곳 - 마스터와 번역본이 {이름}으로 불러 쓰고, 프로그램도 같은 값을 읽는다.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

VIEWS = {"engineer": "엔지니어 관점 (마스터)", "computer": "컴퓨터 관점 (번역본 · 회사 AI · 개발자)", "maintenance": "유지보수 관점 (번역본 · 도구 관리자)"}
MASTER_FIELDS = [("target", "대상"), ("preconditions", "조건"), ("steps", "할 일"), ("exceptions", "예외"), ("verdict", "판정"), ("evidence", "근거")]
STATES = ("확인 필요", "확정", "다시 번역 필요", "질문 있음")

NOTICE = ("이 프로토콜의 기준은 **엔지니어 관점(마스터)** 하나입니다. 컴퓨터 관점과 유지보수 관점은 마스터를 옮긴 **번역본**입니다. "
          "둘이 다르면 항상 마스터가 맞고, 번역본은 고치지 않고 마스터를 고친 뒤 다시 번역합니다. 숫자 기준은 규칙의 기준값(params) 한 곳에만 있습니다. "
          "자세한 관리 방법은 P00.")


def _m(target, pre, steps, exc, verdict, evidence):
    return {"target": target, "preconditions": pre, "steps": steps, "exceptions": exc, "verdict": verdict, "evidence": evidence}


# master (engineer view) + translations (computer, maintenance). Content = v2.0, form = the design office Rule layout.
SEED = [
    {"id": "P00", "title": "이 프로토콜 읽는 법 · 고치는 법", "params": {},
     "master": _m("이 공통 프로토콜 전체 (모든 규칙)", "규칙을 만들거나 고치거나 인계받을 때",
                  ["기준은 엔지니어 관점(마스터) 하나다. 컴퓨터 관점과 유지보수 관점은 마스터의 번역본이다.",
                   "규칙을 바꾸려면 마스터(대상 · 조건 · 할 일 · 예외 · 판정 · 근거)와 기준값만 고친다. 번역본은 직접 고치지 않는다.",
                   "마스터가 바뀌면 번역본은 '다시 번역 필요'가 되고, 다시 번역해서 사람이 확인해야 '확정'이 된다.",
                   "번역하다 애매하면 짐작하지 않고 질문으로 남긴다. 엔지니어가 마스터를 고쳐서 답한다.",
                   "숫자 기준은 기준값 한 곳에만 둔다. 마스터와 번역본과 프로그램이 같은 값을 쓴다.",
                   "마스터 승인은 계장 공종 책임자가 하고, 승인자 · 일자를 남긴다. 고칠 때마다 버전을 올리고 변경 이력을 남긴다."],
                  ["프로젝트 한정 규칙(태그 번호 · 프로젝트 이름이 들어간 것)은 공통에 넣지 않는다"],
                  "번역본이 마스터와 다르면 번역본을 따르지 않는다 (마스터 우선). 다시 번역 필요 · 질문 있음이 남아 있으면 점검 실패.",
                  ["사용자 결정 2026-11-27 (마스터 = 엔지니어 관점)"]),
     "computer": "권위 순서: master(엔지니어 관점) > translations.computer / translations.maintenance. 각 번역본은 from_master(마스터 지문)와 state를 가진다. "
                 "from_master ≠ 현재 마스터 지문이면 state = '다시 번역 필요'로 보고 그 번역본을 근거로 쓰지 않는다 (마스터 원문을 쓴다). "
                 "state = '질문 있음'이면 questions를 엔지니어에게 돌려준다. 번역본 수정은 마스터 지문 갱신과 함께만. 숫자는 params만 참조, 문장 안 숫자 기준 금지. "
                 "검사: tests/check_protocol.py (다시 번역 필요 · 질문 있음 = FAIL, 확인 필요 = 참고).",
     "maintenance": "고치는 순서: ① 마스터 칸과 기준값 수정 ② 버전 +0.1, 변경 이력 ③ 번역본 다시 만들기(회사 Copilot 또는 채팅 AI 초안) ④ 사람이 번역 확인(앱 STEP 10 '공통 프로토콜 보기' → 번역 확인) "
                    "⑤ tests/check_protocol.py 통과 ⑥ 계장 공종 책임자 승인. 파일: projects/_protocol/common_protocol.json (원본), 공통프로토콜.md (보기용, 자동 생성). 코드: pid_io/common_rules.py."},
    {"id": "P01", "title": "같은 입력이면 같은 물량", "params": {},
     "master": _m("모든 물량 결과 (인덱스 · 케이블 · JB · 트레이 · 서포트 · 3D 데이터)", "같은 도면 · PLOT · 3D와 같은 체크리스트 값",
                  ["누가 언제 돌려도 같은 물량이 나와야 한다.", "결과 숫자를 손으로 고치지 않는다.", "바꾸려면 입력이나 사람 결정을 바꾸고 다시 계산한다."],
                  [], "같은 입력인데 물량이 다르면 HOLD (원인 확인).", ["pid_io 설계 원칙"]),
     "computer": "출력 = f(입력 파일 SHA-256, 설정값, 사람 결정 기록). 같은 상태 ID(엑셀 '_지문' 시트)면 같은 물량. 결과 파일 직접 편집 금지, 변경은 입력·설정·결정 기록으로만. 검사: 같은 입력으로 다시 계산한 STRUCTURED_MODEL_DATA records 해시가 같아야 함 (06 REPRODUCIBILITY).",
     "maintenance": "확인: 엑셀 '_지문' 시트의 상태 ID, 06 REPRODUCIBILITY 자동 점검. 계산 코드를 바꾸면 tests/check_cable_jb.py를 돌리고 기준 프로젝트('-2') 물량을 전후 비교, 이유는 인수인계 버전 이력에."},
    {"id": "P02", "title": "값이 부딪힐 때 우선순위", "params": {},
     "master": _m("같은 항목에 값이 여럿일 때 (위치 · 크기 · 경로 · 설정)", "사람 결정, 승인된 3D, PLOT 자동 인식, 체크리스트 기본값이 서로 다를 때",
                  ["사람이 정한 것 > 승인된 3D 자료 > PLOT 자동 인식 > 체크리스트 기본값 순서로 쓴다.", "3D가 사람 결정을 덮지 않는다."],
                  ["3D 자료는 P03 절차로 승인된 것만 '승인된 3D'"], "순서를 어긴 반영은 FAIL.", ["pid_io 설계 원칙"]),
     "computer": "값 결정 순서: 사람 결정(plot_decisions.json · decisions.json · overrides.json) > 승인된 3D 반영(decision_log.json, approved) > PLOT 자동 인식 > 설정 기본값. 상위 값이 있으면 하위 값은 쓰지 않음. 3D 반영은 P03 관문을 거친 것만 '승인된 3D'.",
     "maintenance": "관련: gate.py(결정 보호), decision_log.json. 순서를 바꾸면 관문 시험(사람이 옮긴 JB가 3D 반영 뒤에도 그 자리) 다시 확인, 승인 계장 공종 책임자."},
    {"id": "P03", "title": "3D 반영은 제안 → 미리보기 → 승인", "params": {},
     "master": _m("3D 자료 때문에 물량 · 배치가 바뀌는 것", "3D 모델을 올렸거나 바뀌었을 때",
                  ["바로 바꾸지 않는다.", "바뀌는 숫자 · JB · PLOT 그림을 먼저 보여 준다.", "사람이 승인한 항목만 반영하고 기록한다."],
                  ["취소하면 아무것도 바뀌지 않는다"], "승인 없이 바뀐 값이 있으면 FAIL.", ["pid_io 설계 원칙"]),
     "computer": "3D 반영 = 제안(proposals/<시각>.json) → 미리보기(물량 전후, JB 변화, PLOT 마크업 회색=지금 빨강=제안, 부딪히는 사람 결정) → 항목별 승인 → 승인 항목만 설정 반영 + decision_log 기록 + 리비전 스냅샷. 미승인 = 변경 0.",
     "maintenance": "관련: STEP 10 '3D 반영 제안 보기', gate.py, proposals/. 제안 항목을 늘리면 GATE_3D 목록과 미리보기 숫자를 같이 고침."},
    {"id": "P04", "title": "랙 차선 · 충돌 시 계장이 비킨다", "params": {},
     "master": _m("랙 위 계장 트레이", "다른 공종(배관 · 전기) 객체와 겹칠 때",
                  ["랙의 계장 차선을 먼저 쓴다.", "부딪히면 계장이 옆으로 비킨다.", "옆으로 안 되면 위로 비킨다."],
                  ["다른 공종을 옮기라고 하지 않는다"], "비킨 뒤에도 겹치면 HOLD (사람 판단).", ["pid_io 설계 원칙"]),
     "computer": "트레이 배치: 랙 폭 방향 계장 차선(설정 W01·W02)부터 채움. 다른 공종 객체와 겹치면 폭 방향 이동 → 안 되면 위로 한 단(W05)씩 최대 W06단 → 그래도 겹치면 HOLD(V08). 다른 공종 객체는 읽기만.",
     "maintenance": "관련 설정 STEP 10 W01~W06, twin.avoid, 3D 점검 V08. 바꾸면 다른 공종 JSON(예시 protocols/other3d_example.json)으로 회피 결과 확인."},
    {"id": "P05", "title": "랙 위 트레이 높이 · 자리", "params": {"slot_gap_m": 0.1},
     "master": _m("랙 위 사다리 트레이", "트레이가 랙을 탈 때",
                  ["그 랙의 케이블 단 높이에 놓는다.", "한 랙 위 트레이끼리는 겹치지 않게 {slot_gap_m} m 띄워 나란히 자리를 나눈다."],
                  [], "랙 밖이거나 높이가 다르거나 서로 겹치면 HOLD.", ["pid_io 설계 원칙"]),
     "computer": "ladder_on_rack 트레이 EL = 같은 방향 랙의 케이블 단 EL(3D RK.cable 또는 구조물 높이). 한 랙의 트레이는 길이 방향으로 겹치는 구간마다 폭 방향 슬롯을 따로 배정, 슬롯 간격 {slot_gap_m} m. 위반 시 V02·V06 HOLD.",
     "maintenance": "관련: twin.to_model(차선 배정, 간격 {slot_gap_m} m을 여기서 읽음), 3D 점검 V02·V06. 랙 데이터 형식이 바뀌면(새 3D 모델) twin.parse_base 확인."},
    {"id": "P06", "title": "경사 경로 없음", "params": {},
     "master": _m("케이블 경로", "높이가 바뀌는 구간", ["비스듬히 가지 않는다.", "수평으로 가다가 수직으로 오르내린다."], [],
                  "경사 마디가 남으면 INFO (확인).", ["pid_io 설계 원칙"]),
     "computer": "경로 마디마다 수평 변화와 높이 변화가 동시에 있으면 낮은 쪽 높이로 수평 → 수직 라이저로 나눔. 남으면 V04.",
     "maintenance": "관련: twin.to_model(라이저 분리), 3D 점검 V04."},
    {"id": "P07", "title": "JB 위치", "params": {},
     "master": _m("필드 JB 자리", "JB를 자동으로 놓을 때", ["장비나 랙 안에 두지 않는다.", "랙 기둥 바깥이나 장비 가장자리에 둔다."],
                  ["사람이 옮긴 JB는 그 자리 유지 (P02)"], "장비 · 랙 안이면 HOLD.", ["pid_io 설계 원칙"]),
     "computer": "JB 자리 후보 = 랙 기둥 바깥(설정 J13 거리) · 장비 가장자리(J14) · 3D 랙 기둥 옆. 랙 칸·장비 상자(3D 포함, J1A) 안은 제외. 위반 시 V07 HOLD.",
     "maintenance": "관련 설정 STEP 7 J10~J1A, jb.slots, 3D 점검 V07, check_cable_jb.py의 '자리 … 랙 안' 검사."},
    {"id": "P08", "title": "3D 점검 HOLD는 사람이 판단", "params": {},
     "master": _m("3D 점검에서 걸린 항목", "3D 사전 점검 · 회사 AI 리뷰 결과가 나왔을 때",
                  ["프로그램이 고치지 않고 보류로 둔다.", "사람이 맞다 / 오탐 / 고침을 정한다."], ["AI 리뷰 답도 제안일 뿐"],
                  "사람 판단 전까지 HOLD.", ["pid_io 설계 원칙"]),
     "computer": "3D 사전 점검 V01~V09 결과: HOLD 항목은 자동 수정 금지, 3D_REVIEW_PRECHECK에 객체 ID로 기록, 회사 AI 리뷰 답(CONFIRMED / FALSE_ALARM / NEEDS_PERSON)도 제안일 뿐.",
     "maintenance": "관련: review3d.py(규칙 V01~V09), 3D_REVIEW_PROMPT.md. 규칙 추가 시 V 번호 이어서, 프롬프트·스키마 같이 고침."},
    {"id": "P09", "title": "출력 관리", "params": {},
     "master": _m("모든 결과 파일", "결과를 만들 때 · 발행할 때",
                  ["'최신 하나', '발행본(고정)', '이력(안 지움)'으로 나눠 둔다.", "모든 엑셀에 어느 입력 · 설정으로 만든 것인지 지문을 남긴다."], [],
                  "지문 없는 엑셀은 FAIL.", ["pid_io 설계 원칙"]),
     "computer": "output/LATEST(종류마다 하나, 덮어씀) · ISSUED/R*_날짜(읽기 전용) · HISTORY(시각 붙은 원본, 지우지 않음). 모든 엑셀 끝 '_지문' 시트: 지문 ID, 상태 ID, Rev, 입력 SHA-256, 설정·결정 해시.",
     "maintenance": "관련: outputs.py, history.json, _latest.json. 출력 종류를 추가하면 KIND_NAME에 등록."},
    {"id": "P10", "title": "AI는 제안만", "params": {},
     "master": _m("AI가 만든 모든 결과 (심볼 판정 · 주문 해석 · 3D 리뷰 · 번역 · 교훈)", "AI를 쓸 때",
                  ["AI는 제안과 해석만 한다.", "값을 바꾸는 것과 공통 규칙으로 올리는 것은 사람이 승인한다."], [],
                  "승인 기록 없는 반영은 FAIL.", ["pid_io 설계 원칙"]),
     "computer": "AI 출력(심볼 판정, 주문 해석, 3D 리뷰, 교훈 후보, 프로토콜 번역) = status pending/OPEN/'확인 필요' 제안. 반영은 사람 승인 이벤트(이름·시각)가 있을 때만. 공통 규칙 추가는 decide_lesson(accept) 또는 코멘트 승인으로만.",
     "maintenance": "관련: ai_suggestions.json, lessons.json, prompt_rules.json, common_protocol.json(번역 상태). 승인 기록이 없는 반영이 생기면 버그 - 관련 화면 확인."},
    {"id": "P11", "title": "3D와 PLOT이 다를 때", "seed_rev": 2, "params": {"pos_tol_m": 5, "detour_pct": 2, "same_rack_pct": 30},
     "master": _m("PLOT과 배관 3D 모델의 위치 · 높이 · 랙 · 구조물 차이", "3D 모델을 올렸을 때 (랙 출처가 3D를 쓸 때)",
                  ["물량과 배치의 기준은 우리 Base(PLOT + 산출근거 + 사람 결정)다. 3D는 결과물이다.",
                   "PLOT과 3D가 다르면 그림은 3D를 따른다. 물량은 Base 그대로 두고, 차이는 표(plot_vs_3d)로만 남긴다. 3D를 보고 루팅을 다시 하지 않는다.",
                   "어느 도면이 맞는지는 사람에게 묻지 않는다 (P12).",
                   "높이는 3D 값을 쓴다.",
                   "PLOT 랙과 3D 랙이 {same_rack_pct}% 이상 겹치면 같은 랙으로 보고 형상은 3D를 쓴다.",
                   "장비 위치는 PLOT의 태그 글자가 아니라 장비 도형의 중심으로 잰다. 도형은 3D 상자와 크기가 같은 것을 고른다. 못 찾으면 글자 위치로 재고 표에 '글자'라고 적는다.",
                   "3D에만 있는 구조물(오버브리지 · 서브 랙)은 그림에 3D대로 둔다. 케이블을 그 위로 보낼지는 Base 설정(사람 결정)이고, 물량 영향을 표에 적는다.",
                   "PLOT에만 있는 랙은 Base대로 두고 배관팀에 알린다."],
                  ["PLOT 자체가 옛 도면으로 확인되면 3D 학습이 아니라 Base 입력이 바뀐 것이다: 새 PLOT을 넣고 다시 돌린다."],
                  "차이는 모두 INFO (표에 남기고 멈추지 않음). 장비 위치 차이 > {pos_tol_m} m, 쓰는 3D 구조물로 케이블 증가 > {detour_pct}% 는 INFO '큰 차이'로 표시만 한다.",
                  ["사용자 결정 2026-11-27 (Base 먼저)", "사용자 결정 2026-11-27 (차이 나면 그림은 3D, 어느 쪽이 맞는지 묻지 않음)"]),
     "computer": "입력: PLOT 랙(pt), PLOT 장비 글자 위치와 주변 닫힌 도형(plot.eq_shapes), 3D 랙·참조 구조물·장비 상자(모델 좌표 → 좌표 맞춤 후 pt). (1) 높이: 랙 케이블 단 EL = 3D RK.cable, 참조 구조물 = 높이 h. (2) 랙 출처 '둘 다': PLOT 랙이 3D 랙과 면적 {same_rack_pct}% 이상 겹치면 같은 랙 → 3D 사각형, 아니면 PLOT 랙 유지. (3) 장비 위치: 글자 주변 닫힌 도형 중 3D 상자와 크기 오차 합 ≤ 0.5 인 도형의 중심(twin.outline), 없으면 글자 위치(basis='글자'). 잔차 d > {pos_tol_m} m → INFO '큰 차이', 아니면 INFO. (4) 3D에만 있는 구조물: 넣었을 때와 뺐을 때 케이블 m 차이 Δ%를 계산해 적음, 사용 여부는 사람 설정(rack_refs, rack_refs_off), Δ > {detour_pct}% → INFO '큰 차이'. (5) PLOT에만 있는 랙 → INFO '배관팀 보고'. HOLD는 내지 않는다. 3D 그림: 장비·랙·구조물은 3D 좌표, 트레이·케이블 물량은 Base. 결과 evidence/plot_vs_3d.csv.",
     "maintenance": "관련 설정: STEP 6 '랙 출처'(3D 모델이 있으면 '둘 다' 권장), '3D 모델 오버브리지 · 서브 랙', '빼는 3D 참조 랙'. 기준값 {pos_tol_m} m · {detour_pct}% · 같은 랙 {same_rack_pct}%는 이 규칙의 params에만 있고 프로그램도 여기서 읽는다. 장비 도형 찾기: plot.equipment_shapes (PLOT 캐시 v5), twin.outline. 주의: Base 루팅의 3D 랙 좌표 맞춤은 아직 글자 기준(server.model_racks, outlines=False) - 도형 기준으로 바꾸면 랙 가장자리 경로가 바뀌어 UG가 크게 늘어남(인수인계 열린 질문), 랙 가장자리 규칙을 정한 뒤 전환. 바꾸면 tests/check_protocol.py와 기준 프로젝트 물량 전후 비교, 승인 계장 공종 책임자, 버전 +0.1."},
    {"id": "P12", "title": "3D 코멘트를 규칙으로 바꾸기 (코파일럿 대화)", "seed_rev": 1, "params": {"max_q": 5},
     "master": _m("3D 결과를 보고 사람이 단 코멘트, 3D를 그리며 생긴 질문", "3D 루프(R0, R1 …)에서 회사 AI(VS Code 코파일럿)와 한국어로 대화할 때",
                  ["사실(PLOT과 3D 중 어느 쪽이 맞나)은 묻지 않는다. P11대로 처리하고 가정으로 적는다. 알 수 있는 사람은 타 공종이라 확인 목록으로 보낸다.",
                   "묻는 것은 두 가지뿐이다: ① PLOT에도 3D에도 없어 어디에 그릴지 정해지지 않은 것 ② 3D를 따랐더니 그림이 이상해지는 곳 (트레이가 장비를 뚫음, 케이블이 공중에 뜸).",
                   "물을 때는 한 번에 한 건, 그림(파일 이름)을 먼저 보여 주고, 추천안과 각 선택의 결과를 붙여 '응 / 다르게'로 답할 수 있게 한다. 추천안을 못 쓰면 묻지 않고 가정으로 처리한다. 한 라운드에 {max_q}건까지.",
                   "사람이 코멘트하거나 '다르게'라고 하면 '왜요?'를 한 번 묻는다. 고른 답보다 이유가 규칙이 된다.",
                   "마지막으로 '이번만이에요, 항상이에요?'를 묻는다. 이번만 → 이 프로젝트의 3D 프롬프트 규칙. 항상 → 공통 프로토콜 마스터 개정안 (엔지니어 승인 후 규칙).",
                   "대화 결과는 정해진 답 파일에 적고, pid_io가 읽어 코멘트로 올린다. 사람이 승인하면 다음 라운드부터 들어간다."],
                  ["답하다 PLOT이 옛 도면으로 밝혀지면 3D 학습이 아니라 Base 입력 변경이다 (P11 예외).",
                   "AI는 길이 · 위치 · 물량을 재거나 계산하지 않는다. 숫자는 pid_io가 준 값만 쓴다."],
                  "답 파일 항목에 이유(reason) 또는 범위(이번만 / 항상)가 없으면 HOLD: pid_io가 읽지 않고 되돌려 다시 묻게 한다.",
                  ["사용자 결정 2026-11-27 (사실은 묻지 않고 의도를 묻는다, 이유가 규칙이 된다)"]),
     "computer": "대화 상대: VS Code 코파일럿 (한국어). 라운드 폴더의 COPILOT_GUIDE.md를 읽고 시작한다. 금지: PLOT/3D 중 어느 쪽이 맞는지 묻기, 길이·위치·물량 계산. 질문 = ① 미정 배치 ② 3D를 따랐더니 그림이 이상한 곳만, 한 번에 한 건, 그림 파일 이름 + 추천안 + 선택별 결과(pid_io 숫자) + '응 / 다르게', 라운드당 {max_q}건 이하, 추천안이 없으면 묻지 않음. 코멘트나 '다르게' → '왜요?' 1회 → '이번만 / 항상'. 결과는 같은 폴더 COPILOT_ANSWERS.json (format pid_io-copilot-answers-1, items[]: id, about, picture, question, recommendation, answer, what, reason, scope 이번만|항상, kind 3D|BASE, by). reason 또는 scope가 비면 그 항목은 HOLD로 되돌아온다. 이번만 → 프로젝트 코멘트(scope 프로젝트), 항상 → 코멘트(scope 공통) → 승인 시 공통 프로토콜 DRAFT 규칙.",
     "maintenance": "파일: 라운드 폴더 COPILOT_GUIDE.md(만들 때마다 새로 씀), COPILOT_ANSWERS.json(빈 양식, 코파일럿이 채움). 앱 STEP 10 → 3D 루프 → '코파일럿 답 읽기'가 loop3d.import_answers를 불러 코멘트(C-nnn)로 올린다. 같은 답 항목은 두 번 올라가지 않는다(answer_key). 질문 상한 {max_q}건은 이 규칙의 params. 바꾸면 tests/check_protocol.py, 승인 계장 공종 책임자, 버전 +0.1."},
]


# ------------------------------------------------------------------ helpers
def render(text, params: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(params.get(m.group(1), m.group(0))), text or "")


def master_hash(rule: dict) -> str:
    return hashlib.sha256(json.dumps([rule.get("master"), rule.get("params") or {}], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def master_text(rule: dict, fill: bool = True) -> str:
    """the engineer view as one paragraph from the master fields."""
    m = rule.get("master") or {}
    p = rule.get("params") or {} if fill else {}
    f = (lambda t: render(t, p)) if fill else (lambda t: t)
    parts = []
    for k, lab in MASTER_FIELDS:
        v = m.get(k)
        if not v:
            continue
        if isinstance(v, list):
            v = " ".join(f"{i + 1}) {f(x)}" for i, x in enumerate(v)) if k == "steps" else " / ".join(f(x) for x in v)
        else:
            v = f(v)
        parts.append(f"[{lab}] {v}")
    return " ".join(parts)


def state(rule: dict, view: str) -> str:
    t = (rule.get("translations") or {}).get(view) or {}
    if not (t.get("text") or "").strip():
        return "다시 번역 필요"
    if t.get("from_master") != master_hash(rule):
        return "다시 번역 필요"
    if t.get("questions"):
        return "질문 있음"
    return t.get("state") or "확인 필요"


def views(rule: dict, fill: bool = True) -> dict:
    p = rule.get("params") or {}
    tr = rule.get("translations") or {}
    g = (lambda t: render(t, p)) if fill else (lambda t: t or "")
    return {"engineer": master_text(rule, fill), "computer": g((tr.get("computer") or {}).get("text")),
            "maintenance": g((tr.get("maintenance") or {}).get("text"))}


def make_rule(seed: dict, by: str = "pid_io (초기 번역)") -> dict:
    r = {k: seed[k] for k in ("id", "title", "params", "master")}
    if seed.get("seed_rev"):
        r["seed_rev"] = seed["seed_rev"]
    h = master_hash(r)
    r["translations"] = {v: {"text": seed[v], "from_master": h, "state": "확인 필요", "by": by, "at": time.strftime("%Y-%m-%d"), "questions": []}
                         for v in ("computer", "maintenance")}
    r.update(status="DRAFT", approved_by=None, approval_date=None, src=seed.get("src", "seed"))
    return r


RULES = [make_rule(x) for x in SEED]


def flat(rule: dict) -> dict:
    """the stored rule + old-style fields (engineer / computer / maintenance / text) for screens and the AI prompt."""
    v = views(rule, fill=False)
    return {**rule, "engineer": v["engineer"], "computer": v["computer"], "maintenance": v["maintenance"],
            "text": master_text(rule), "states": {k: state(rule, k) for k in ("computer", "maintenance")}, "master_hash": master_hash(rule)}


NUM = re.compile(r"(?<![\w.{])\d+(?:\.\d+)?\s*(?:m|%|mm|°C)(?![\w])")


def check(rules: list) -> list:
    """[(rule id, problem, level)] level FAIL / 참고."""
    out = []
    for r in rules:
        m = r.get("master") or {}
        for k, lab in (("target", "대상"), ("steps", "할 일"), ("verdict", "판정")):
            if not m.get(k):
                out.append((r["id"], f"마스터 '{lab}' 칸이 비어 있음", "FAIL"))
        vv = views(r, fill=False)
        for p in (r.get("params") or {}):
            for k in VIEWS:
                if "{" + p + "}" not in vv[k]:
                    out.append((r["id"], f"기준값 {p}를 {VIEWS[k]}에서 안 씀", "FAIL"))
        for k in VIEWS:
            for n in NUM.findall(vv[k]):
                out.append((r["id"], f"{VIEWS[k]}에 기준값(params) 밖 숫자 '{n.strip()}'", "FAIL"))
        for k in ("computer", "maintenance"):
            st = state(r, k)
            if st in ("다시 번역 필요", "질문 있음"):
                qs = ((r.get("translations") or {}).get(k) or {}).get("questions") or []
                out.append((r["id"], f"{VIEWS[k]}: {st}" + (f" - {'; '.join(qs)}" if qs else ""), "FAIL"))
            elif st == "확인 필요":
                out.append((r["id"], f"{VIEWS[k]}: 번역 확인 필요 (사람)", "참고"))
        if r.get("status") != "APPROVED":
            out.append((r["id"], "마스터 승인 전 (DRAFT)", "참고"))
    return out


def params_flat(common: dict) -> dict:
    out = {}
    for r in common.get("rules", []):
        for k, v in (r.get("params") or {}).items():
            out[f"{r['id']}.{k}"] = v
            out.setdefault(k, v)
    return out


def param(common: dict, rule_id: str, name: str, default=None):
    r = next((x for x in common.get("rules", []) if x["id"] == rule_id), None)
    return ((r or {}).get("params") or {}).get(name, default)


# ------------------------------------------------------------------ changes (people)
def set_master(c: dict, rid: str, master: dict | None = None, params: dict | None = None, by: str = "") -> dict:
    r = next(x for x in c["rules"] if x["id"] == rid)
    if master:
        r["master"] = {**r["master"], **master}
    if params is not None:
        r["params"] = params
    r.update(status="DRAFT", approved_by=None, approval_date=None)        # a changed master needs approval again
    _bump(c, f"{rid} 마스터 수정" + (f" ({by})" if by else "") + " - 번역본 다시 번역 필요")
    return c


def set_translation(c: dict, rid: str, view: str, text: str, by: str, questions: list | None = None) -> dict:
    r = next(x for x in c["rules"] if x["id"] == rid)
    r.setdefault("translations", {})[view] = {"text": text, "from_master": master_hash(r), "state": "확인 필요", "by": by,
                                               "at": time.strftime("%Y-%m-%d %H:%M"), "questions": questions or []}
    return c


def confirm_translation(c: dict, rid: str, view: str, by: str) -> dict:
    r = next(x for x in c["rules"] if x["id"] == rid)
    st = state(r, view)
    if st in ("다시 번역 필요", "질문 있음"):
        raise ValueError(f"{rid} {VIEWS[view]}: {st} - 다시 번역하거나 마스터를 고친 뒤 확인하세요")
    if not (by or "").strip():
        raise ValueError("확인한 사람 이름을 적어 주세요")
    r["translations"][view].update(state="확정", confirmed_by=by.strip(), confirmed_at=time.strftime("%Y-%m-%d %H:%M"))
    return c


def approve_master(c: dict, rid: str, by: str) -> dict:
    if not (by or "").strip():
        raise ValueError("승인자 이름을 적어 주세요")
    r = next(x for x in c["rules"] if x["id"] == rid)
    r.update(status="APPROVED", approved_by=by.strip(), approval_date=time.strftime("%Y-%m-%d"))
    _bump(c, f"{rid} 마스터 승인 ({by.strip()})")
    return c


def _bump(c: dict, what: str):
    major, minor = str(c.get("version", "3.0")).split(".")[:2]
    c["version"] = f"{major}.{int(minor) + 1}"
    c.setdefault("changelog", []).append({"version": c["version"], "at": time.strftime("%Y-%m-%d"), "what": what})


def sync_seed(c: dict) -> bool:
    """v13.9: seed rules changed by a user decision (seed_rev) reach a stored v3 file: a missing rule is added, a DRAFT seed
    rule with an older seed_rev gets the new master + fresh translations (to confirm). An APPROVED rule is not overwritten -
    the changelog says a newer seed exists. Returns True when something changed."""
    changed = False
    for sd in SEED:
        rev = sd.get("seed_rev")
        if not rev:
            continue
        r = next((x for x in c["rules"] if x["id"] == sd["id"]), None)
        if r is None:
            c["rules"].append(make_rule(sd, "pid_io (번역)"))
            _bump(c, f"{sd['id']} 추가 ({sd['title']}) - 사용자 결정, 마스터 승인 · 번역 확인 필요")
            changed = True
        elif (r.get("seed_rev") or 1) < rev:
            if r.get("status") == "APPROVED":
                note = f"{sd['id']} 새 seed {rev} 있음 - 승인된 규칙이라 덮어쓰지 않음, 엔지니어가 마스터 비교"
                if not any(x.get("what") == note for x in c.get("changelog", [])):
                    c.setdefault("changelog", []).append({"version": c.get("version"), "at": time.strftime("%Y-%m-%d"), "what": note})
                    changed = True
                continue
            r["title"] = sd["title"]
            set_master(c, sd["id"], sd["master"], sd["params"], "사용자 결정")
            for v in ("computer", "maintenance"):
                set_translation(c, sd["id"], v, sd[v], "pid_io (번역)")
            r["seed_rev"] = rev
            changed = True
    return changed


# ------------------------------------------------------------------ upgrade / document
def upgrade(c: dict) -> dict:
    """v1 / v2 -> v3 (master + translations). Seed rules -> v3 seed (same content), learned / comment rules: their
    engineer sentence becomes the master steps, the other views translations to confirm."""
    if str(c.get("version", "1")).split(".")[0] >= "3":
        return c
    extra = []
    for r in c.get("rules", []):
        if r.get("src") in ("lesson", "comment"):
            eng = r.get("engineer") or r.get("text", "")
            nr = {"id": r["id"], "title": r.get("title") or eng[:30], "params": r.get("params") or {},
                  "master": _m(r.get("title") or eng[:30], "", [eng], [], "어기면 HOLD (사람 판단)", [r.get("from") or r.get("src", "")]),
                  "computer": r.get("computer") or eng, "maintenance": r.get("maintenance") or "", "src": r.get("src")}
            extra.append(make_rule(nr, "v2에서 옮김"))
    c["rules"] = [make_rule(x) for x in SEED] + extra
    c["version"] = "3.0"
    c["views"] = VIEWS
    c["notice"] = NOTICE
    c.setdefault("changelog", []).append({"version": "3.0", "at": "2026-11-27",
                                          "what": "엔지니어 관점 = 마스터 (설계실 Rule 양식 칸: 대상·조건·할 일·예외·판정·근거·상태), 컴퓨터·유지보수 = 번역본 "
                                                  "(마스터 지문·상태), P00 읽는 법 추가. 규칙 내용은 v2.0과 같음 (사용자 결정)"})
    return c


def markdown(c: dict) -> str:
    rs = c["rules"]
    md = [f"# {c['name']} v{c['version']}", "", f"> **읽기 전에** {NOTICE}", "", f"범위: {c['scope']}", ""]
    md += ["## 목차 · 상태", "", "| 규칙 | 제목 | 마스터 | 컴퓨터 번역 | 유지보수 번역 |", "|---|---|---|---|---|"]
    for r in rs:
        md.append(f"| {r['id']} | {r.get('title', '')} | {'승인 ' + str(r.get('approved_by')) if r.get('status') == 'APPROVED' else 'DRAFT'} | "
                  f"{state(r, 'computer')} | {state(r, 'maintenance')} |")
    md += ["", "## 엔지니어 관점 (마스터)", ""]
    for r in rs:
        m, p = r.get("master") or {}, r.get("params") or {}
        md.append(f"### {r['id']} {r.get('title', '')}")
        for k, lab in MASTER_FIELDS:
            v = m.get(k)
            if not v:
                continue
            if isinstance(v, list):
                md.append(f"- **{lab}**")
                md += [f"  {i + 1}. {render(x, p)}" if k == "steps" else f"  - {render(x, p)}" for i, x in enumerate(v)]
            else:
                md.append(f"- **{lab}** {render(v, p)}")
        if p:
            md.append("- **기준값** " + ", ".join(f"{k} = {v}" for k, v in p.items()))
        md.append(f"- **상태** {r.get('status')}" + (f" · 승인 {r.get('approved_by')} {r.get('approval_date')}" if r.get("status") == "APPROVED" else ""))
        md.append("")
    for k in ("computer", "maintenance"):
        md += [f"## {VIEWS[k]}", "", "_마스터의 번역본입니다. 마스터와 다르면 마스터가 맞습니다._", ""]
        for r in rs:
            md.append(f"- **{r['id']} {r.get('title', '')}** _({state(r, k)})_: {render(((r.get('translations') or {}).get(k) or {}).get('text'), r.get('params') or {})}")
        md.append("")
    md += ["## 기준값 (params)", "", "| 규칙 | 이름 | 값 |", "|---|---|---|"]
    md += [f"| {r['id']} | {k} | {v} |" for r in rs for k, v in (r.get("params") or {}).items()] or ["| - | - | - |"]
    issues = check(rs)
    md += ["", "## 점검", ""] + ([f"- {lv} {i}: {p}" for i, p, lv in issues if lv == "FAIL"] or ["- FAIL 없음"])
    n_ref = sum(1 for i in issues if i[2] == "참고")
    if n_ref:
        md.append(f"- 참고 {n_ref}건 (번역 확인 · 마스터 승인 대기)")
    md += ["", "## 변경 이력", ""] + [f"- v{x['version']} ({x['at']}): {x['what']}" for x in c.get("changelog", [])]
    return "\n".join(md) + "\n"
