"""공통 프로토콜 v2 - 한 규칙, 세 관점 (v13.7, 사용자 지시 2026-11-27).

    engineer     다른 계장 엔지니어 · 공종 책임자: 무엇을, 왜 (설계 언어)
    computer     회사 AI · 개발자: 입력, 순서, 수치 기준, 판정 (PASS / INFO / HOLD), 데이터 이름
    maintenance  이 도구를 관리하는 사람: 관련 설정·파일, 바꾸는 법, 승인자, 바꾼 뒤 돌릴 시험

세 관점은 말투만 다르고 내용은 같아야 한다. 그래서
  - 숫자·기준은 규칙의 params 한 곳에만 두고, 세 문장은 {이름}으로 불러 쓴다 (숫자가 어긋날 수 없음)
  - 프로그램도 param()으로 같은 값을 읽어 동작한다 (컴퓨터 관점 = 실제 동작)
  - check()가 세 관점이 다 있는지, 모든 params를 세 관점이 다 언급하는지, 문장에 params 밖 숫자 기준이 없는지 본다
  - 뜻이 같은지는 사람이 승인할 때 확인 (자동 보장 불가 - 그래서 needs_review 표시)
"""
from __future__ import annotations

import re

VIEWS = {"engineer": "엔지니어 관점", "computer": "컴퓨터 관점 (회사 AI · 개발자)", "maintenance": "유지보수 관점"}

RULES = [
    {"id": "P01", "title": "같은 입력이면 같은 물량", "params": {},
     "engineer": "같은 도면·PLOT·3D와 같은 체크리스트 값이면 누가 언제 돌려도 같은 물량이 나와야 한다. 결과 숫자를 손으로 고치지 않는다. 바꾸려면 입력이나 사람 결정을 바꾸고 다시 계산한다.",
     "computer": "출력 = f(입력 파일 SHA-256, 설정값, 사람 결정 기록). 같은 상태 ID(엑셀 '_지문' 시트)면 같은 물량. 결과 파일 직접 편집 금지, 변경은 입력·설정·결정 기록으로만. 검사: 같은 입력으로 다시 계산한 STRUCTURED_MODEL_DATA records 해시가 같아야 함 (06 REPRODUCIBILITY).",
     "maintenance": "확인: 엑셀 '_지문' 시트의 상태 ID, 06 REPRODUCIBILITY 자동 점검. 계산 코드를 바꾸면 tests/check_cable_jb.py를 돌리고 기준 프로젝트('-2') 물량을 전후 비교, 이유는 인수인계 버전 이력에."},
    {"id": "P02", "title": "값이 부딪힐 때 우선순위", "params": {},
     "engineer": "같은 항목에 값이 여럿이면 사람이 정한 것 > 승인된 3D 자료 > PLOT 자동 인식 > 체크리스트 기본값 순서로 쓴다. 3D가 사람 결정을 덮지 않는다.",
     "computer": "값 결정 순서: 사람 결정(plot_decisions.json · decisions.json · overrides.json) > 승인된 3D 반영(decision_log.json, approved) > PLOT 자동 인식 > 설정 기본값. 상위 값이 있으면 하위 값은 쓰지 않음. 3D 반영은 P03 관문을 거친 것만 '승인된 3D'.",
     "maintenance": "관련: gate.py(결정 보호), decision_log.json. 순서를 바꾸면 관문 시험(사람이 옮긴 JB가 3D 반영 뒤에도 그 자리) 다시 확인, 승인 계장 공종 책임자."},
    {"id": "P03", "title": "3D 반영은 제안 → 미리보기 → 승인", "params": {},
     "engineer": "3D 자료 때문에 물량이 바뀌는 것은 바로 바꾸지 않는다. 바뀌는 숫자·JB·PLOT 그림을 먼저 보여 주고 사람이 승인한 것만 반영한다. 취소하면 아무것도 안 바뀐다.",
     "computer": "3D 반영 = 제안(proposals/<시각>.json) → 미리보기(물량 전후, JB 변화, PLOT 마크업 회색=지금 빨강=제안, 부딪히는 사람 결정) → 항목별 승인 → 승인 항목만 설정 반영 + decision_log 기록 + 리비전 스냅샷. 미승인 = 변경 0.",
     "maintenance": "관련: STEP 10 '3D 반영 제안 보기', gate.py, proposals/. 제안 항목을 늘리면 GATE_3D 목록과 미리보기 숫자를 같이 고침."},
    {"id": "P04", "title": "랙 차선 · 충돌 시 계장이 비킨다", "params": {},
     "engineer": "계장 트레이는 랙의 계장 차선을 먼저 쓰고, 다른 공종과 부딪히면 계장이 옆으로, 그래도 안 되면 위로 비킨다. 다른 공종을 옮기라고 하지 않는다.",
     "computer": "트레이 배치: 랙 폭 방향 계장 차선(설정 W01·W02)부터 채움. 다른 공종 객체와 겹치면 폭 방향 이동 → 안 되면 위로 한 단(W05)씩 최대 W06단 → 그래도 겹치면 HOLD(V08). 다른 공종 객체는 읽기만.",
     "maintenance": "관련 설정 STEP 10 W01~W06, twin.avoid, 3D 점검 V08. 바꾸면 다른 공종 JSON(예시 protocols/other3d_example.json)으로 회피 결과 확인."},
    {"id": "P05", "title": "랙 위 트레이 높이 · 자리", "params": {"slot_gap_m": 0.1},
     "engineer": "랙 위 트레이는 그 랙의 케이블 단 높이에 놓고, 한 랙 위 트레이끼리는 겹치지 않게 {slot_gap_m} m 띄워 나란히 자리를 나눈다.",
     "computer": "ladder_on_rack 트레이 EL = 같은 방향 랙의 케이블 단 EL(3D RK.cable 또는 구조물 높이). 한 랙의 트레이는 길이 방향으로 겹치는 구간마다 폭 방향 슬롯을 따로 배정, 슬롯 간격 {slot_gap_m} m. 위반 시 V02·V06 HOLD.",
     "maintenance": "관련: twin.to_model(차선 배정, 간격 {slot_gap_m} m을 여기서 읽음), 3D 점검 V02·V06. 랙 데이터 형식이 바뀌면(새 3D 모델) twin.parse_base 확인."},
    {"id": "P06", "title": "경사 경로 없음", "params": {},
     "engineer": "케이블은 비스듬히 가지 않는다. 수평으로 가다가 수직으로 오르내린다.",
     "computer": "경로 마디마다 수평 변화와 높이 변화가 동시에 있으면 낮은 쪽 높이로 수평 → 수직 라이저로 나눔. 남으면 V04.",
     "maintenance": "관련: twin.to_model(라이저 분리), 3D 점검 V04."},
    {"id": "P07", "title": "JB 위치", "params": {},
     "engineer": "JB는 장비나 랙 안에 두지 않는다. 랙 기둥 바깥이나 장비 가장자리에 둔다.",
     "computer": "JB 자리 후보 = 랙 기둥 바깥(설정 J13 거리) · 장비 가장자리(J14) · 3D 랙 기둥 옆. 랙 칸·장비 상자(3D 포함, J1A) 안은 제외. 위반 시 V07 HOLD.",
     "maintenance": "관련 설정 STEP 7 J10~J1A, jb.slots, 3D 점검 V07, check_cable_jb.py의 '자리 … 랙 안' 검사."},
    {"id": "P08", "title": "3D 점검 HOLD는 사람이 판단", "params": {},
     "engineer": "3D 점검에서 걸린 항목은 프로그램이 고치지 않고 HOLD로 두며 사람이 맞다 / 오탐 / 고침을 정한다.",
     "computer": "3D 사전 점검 V01~V09 결과: HOLD 항목은 자동 수정 금지, 3D_REVIEW_PRECHECK에 객체 ID로 기록, 회사 AI 리뷰 답(CONFIRMED / FALSE_ALARM / NEEDS_PERSON)도 제안일 뿐.",
     "maintenance": "관련: review3d.py(규칙 V01~V09), 3D_REVIEW_PROMPT.md. 규칙 추가 시 V 번호 이어서, 프롬프트·스키마 같이 고침."},
    {"id": "P09", "title": "출력 관리", "params": {},
     "engineer": "결과물은 '최신 하나', '발행본(고정)', '이력(안 지움)'으로 나눠 두고, 모든 엑셀에 어느 입력·설정으로 만든 것인지 지문을 남긴다.",
     "computer": "output/LATEST(종류마다 하나, 덮어씀) · ISSUED/R*_날짜(읽기 전용) · HISTORY(시각 붙은 원본, 지우지 않음). 모든 엑셀 끝 '_지문' 시트: 지문 ID, 상태 ID, Rev, 입력 SHA-256, 설정·결정 해시.",
     "maintenance": "관련: outputs.py, history.json, _latest.json. 출력 종류를 추가하면 KIND_NAME에 등록."},
    {"id": "P10", "title": "AI는 제안만", "params": {},
     "engineer": "AI는 제안과 해석만 한다. 값을 바꾸는 것과 공통 규칙으로 올리는 것은 사람이 승인한다.",
     "computer": "AI 출력(심볼 판정, 주문 해석, 3D 리뷰, 교훈 후보) = status pending/OPEN 제안. 반영은 사람 승인 이벤트(이름·시각)가 있을 때만. 공통 규칙 추가는 decide_lesson(accept) 또는 코멘트 승인으로만.",
     "maintenance": "관련: ai_suggestions.json, lessons.json, prompt_rules.json. 승인 기록이 없는 반영이 생기면 버그 - 관련 화면 확인."},
    {"id": "P11", "title": "3D와 PLOT이 다를 때", "params": {"pos_tol_m": 5, "detour_pct": 2, "same_rack_pct": 30},
     "engineer": "물량과 배치의 기준은 우리 Base(PLOT + 산출근거 + 사람 결정)이고 3D는 높이와 구조물 확인용이다. 높이는 3D 값을 쓴다. PLOT 랙과 3D 랙이 {same_rack_pct}% 이상 겹치면 같은 랙으로 보고 형상은 3D를 쓴다. 위치 차이가 {pos_tol_m} m 이하면 그림만 맞추고 물량은 Base대로 둔다. 장비 위치가 {pos_tol_m} m 넘게 다르면 어느 도면이 최신인지 먼저 확인한다. 3D에만 있는 구조물(오버브리지·서브 랙)은 물량 영향과 함께 보여 주고 사람이 쓸지 정하며, 그 구조물 때문에 케이블이 {detour_pct}% 넘게 늘면 다시 확인한다. PLOT에만 있는 랙은 Base대로 두고 배관팀에 알린다.",
     "computer": "입력: PLOT 랙(pt), 3D 랙·참조 구조물(모델 좌표 → 좌표 맞춤 후 pt). (1) 높이: 랙 케이블 단 EL = 3D RK.cable, 참조 구조물 = 높이 h. (2) 랙 출처 '둘 다': PLOT 랙이 3D 랙과 면적 {same_rack_pct}% 이상 겹치면 같은 랙 → 3D 사각형, 아니면 PLOT 랙 유지. (3) 장비 잔차 d: d ≤ {pos_tol_m} m → INFO(그림만 맞춤), d > {pos_tol_m} m → HOLD. (4) 3D에만 있는 구조물: 넣었을 때와 뺐을 때 케이블 m 차이 Δ%를 계산, 사용 여부는 사람 설정(rack_refs, rack_refs_off); 사용 중이고 Δ > {detour_pct}% → HOLD. (5) PLOT에만 있는 랙 → INFO '배관팀 보고'. 결과 evidence/plot_vs_3d.csv.",
     "maintenance": "관련 설정: STEP 6 '랙 출처'(3D 모델이 있으면 '둘 다' 권장), '3D 모델 오버브리지 · 서브 랙', '빼는 3D 참조 랙'. 기준값 {pos_tol_m} m · {detour_pct}% · 같은 랙 {same_rack_pct}%는 이 규칙의 params에만 있고 프로그램도 여기서 읽는다. 바꾸면 tests/check_protocol.py와 기준 프로젝트 불일치 목록·물량을 전후 비교, 승인 계장 공종 책임자, 버전 +0.1."},
]


def render(text: str, params: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(params.get(m.group(1), m.group(0))), text or "")


def rendered(rule: dict) -> dict:
    p = rule.get("params") or {}
    return {**rule, **{k: render(rule.get(k, ""), p) for k in VIEWS}, "text": render(rule.get("engineer") or rule.get("text", ""), p)}


NUM = re.compile(r"(?<![\w.{])\d+(?:\.\d+)?\s*(?:m|%|mm|°C)(?![\w])")


def check(rules: list) -> list:
    """[(rule id, problem)] - views missing, a param not used in all three, a bare number criterion outside params."""
    out = []
    for r in rules:
        for k in VIEWS:
            if not (r.get(k) or "").strip():
                out.append((r["id"], f"{VIEWS[k]} 없음"))
        for p in (r.get("params") or {}):
            miss = [VIEWS[k] for k in VIEWS if "{" + p + "}" not in (r.get(k) or "")]
            if miss:
                out.append((r["id"], f"기준값 {p}를 {', '.join(miss)}에서 안 씀 - 세 관점이 같은 값을 말해야 함"))
        for k in VIEWS:
            for m in NUM.findall(r.get(k) or ""):
                if not r.get("allow_numbers"):
                    out.append((r["id"], f"{VIEWS[k]}에 params 밖 숫자 기준 '{m.strip()}' - params로 옮기세요"))
        if r.get("needs_review"):
            out.append((r["id"], "세 관점 문장이 같은 뜻인지 사람 확인 필요"))
    return out


def params_flat(common: dict) -> dict:
    """all params of all rules, for the program ('P11.pos_tol_m' and plain 'pos_tol_m')."""
    out = {}
    for r in common.get("rules", []):
        for k, v in (r.get("params") or {}).items():
            out[f"{r['id']}.{k}"] = v
            out.setdefault(k, v)
    return out


def param(common: dict, rule_id: str, name: str, default=None):
    r = next((x for x in common.get("rules", []) if x["id"] == rule_id), None)
    return ((r or {}).get("params") or {}).get(name, default)


def upgrade(c: dict) -> dict:
    """v1 (one sentence per rule) -> v2: seed rules replaced by the three-view text, lessons keep their text as the
    engineer view and are flagged for the other two."""
    if str(c.get("version", "1")).split(".")[0] >= "2":
        return c
    lessons = []
    for r in c.get("rules", []):
        if r.get("src") == "lesson":
            lessons.append({**r, "title": r.get("title") or r["text"][:30], "params": {}, "engineer": r["text"],
                            "computer": r["text"], "maintenance": "배운 규칙 - " + (r.get("from") or ""), "needs_review": True})
    c["rules"] = [{**x, "src": "seed"} for x in RULES] + lessons
    c["version"] = "2.0"
    c["views"] = VIEWS
    c.setdefault("changelog", []).append({"version": "2.0", "at": "2026-11-27",
                                          "what": "세 관점(엔지니어 · 컴퓨터 · 유지보수)으로 다시 씀, 기준값 params 한 곳, P11 3D와 PLOT이 다를 때 추가 (사용자 지시)"})
    return c


def markdown(c: dict) -> str:
    rs = [rendered(r) for r in c["rules"]]
    md = [f"# {c['name']} v{c['version']}", "", f"범위: {c['scope']}", "",
          "규칙 하나를 세 관점으로 씁니다. **말투만 다르고 내용은 같습니다.** 숫자 기준은 규칙마다 한 곳(params)에만 있고 세 관점과 프로그램이 같은 값을 씁니다.", ""]
    md += ["## 목차", ""] + [f"- **{r['id']}** {r.get('title', '')}" + (" _(배운 것)_" if r.get("src") == "lesson" else "") for r in rs] + [""]
    for k, name in VIEWS.items():
        md += [f"## {name}", ""]
        for r in rs:
            md.append(f"- **{r['id']} {r.get('title', '')}**: {r.get(k, '')}")
        md.append("")
    md += ["## 기준값 (params)", "", "| 규칙 | 이름 | 값 |", "|---|---|---|"]
    md += [f"| {r['id']} | {k} | {v} |" for r in c["rules"] for k, v in (r.get("params") or {}).items()] or ["| - | - | - |"]
    issues = check(c["rules"])
    md += ["", "## 세 관점 일치 점검", ""] + ([f"- {i}: {p}" for i, p in issues] or ["- 문제 없음"])
    md += ["", "## 변경 이력", ""] + [f"- v{x['version']} ({x['at']}): {x['what']}" for x in c.get("changelog", [])]
    return "\n".join(md) + "\n"
