"""3D 구현 루프 (v13.6) - 회사 AI가 우리 프롬프트 + 자료로 3D를 그리고, 사람이 코멘트하고, 프롬프트/자료를 고쳐 다시 낸다.

    Base (산출근거 + PLOT 마크업)  →  R0: 7종 + 3D_BUILD_PROMPT.md + BASE_SUMMARY.md + PLOT_MARKUP.png  →  회사 AI가 3D 작성
      → 사람이 AI 3D를 보고 코멘트  →  코멘트 = 프롬프트 규칙(PR-nnn, 승인) 또는 Base 수정(STEP 6~9)
      → R1: 다시 뽑기 (프롬프트 규칙 누적, 변경표)  →  …  →  제출 zip (최신 Rn)

Project files: prompt_rules.json (comments + rules), loop_rounds.json (rounds), input/ai3d/R<n>_*.html (AI가 그린 3D).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
import zipfile
from pathlib import Path

from .handoff import JB_TYPICAL, PROFILE, now_iso, sha

PROMPT_NAME = "3D_BUILD_PROMPT.md"


# ------------------------------------------------------------------ comments → prompt rules
def load_rules(pdir: Path) -> dict:
    f = Path(pdir) / "prompt_rules.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:                                      # noqa: BLE001
        d = {}
    d.setdefault("comments", [])
    return d


def save_rules(pdir: Path, d: dict):
    (Path(pdir) / "prompt_rules.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def rounds(pdir: Path) -> list:
    try:
        return json.loads((Path(pdir) / "loop_rounds.json").read_text(encoding="utf-8"))
    except Exception:                                      # noqa: BLE001
        return []


def save_rounds(pdir: Path, r: list):
    (Path(pdir) / "loop_rounds.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def comment_update(pdir: Path, b: dict) -> dict:
    """add a comment / turn it into a prompt rule (text, scope) / approve / hold / mark a base fix done / delete."""
    d = load_rules(pdir)
    rs = rounds(pdir)
    cur = len(rs) - 1
    if b.get("add"):
        a = b["add"]
        if not (a.get("text") or "").strip():
            raise ValueError("코멘트 내용이 비어 있습니다")
        n = 1 + max([int(c["id"][2:]) for c in d["comments"]] or [0])
        d["comments"].append({"id": f"C-{n:03d}", "at": now_iso(), "round": max(cur, 0), "text": a["text"].strip(),
                              "target": (a.get("target") or "").strip(), "kind": a.get("kind") or "PROMPT",
                              "rule_text": (a.get("rule_text") or a["text"]).strip(), "scope": a.get("scope") or "프로젝트",
                              "status": "OPEN", "rule_id": None, "by": (a.get("by") or "").strip()})
    else:
        c = next((x for x in d["comments"] if x["id"] == b.get("id")), None)
        if not c:
            raise ValueError("코멘트를 찾지 못했습니다")
        if b.get("delete"):
            if c["status"] == "APPLIED" and c.get("rule_id"):
                raise ValueError("이미 프롬프트에 들어간 규칙은 지우지 않고 '폐기'로 남깁니다")
            d["comments"].remove(c)
        for k in ("rule_text", "computer_text", "kind", "scope", "target"):
            if k in b:
                c[k] = b[k]
        if b.get("approve"):                                  # becomes a prompt rule from the next round on
            if c["kind"] != "PROMPT":
                raise ValueError("Base 수정 코멘트는 STEP 6~9에서 고친 뒤 '반영 완료'를 누르세요")
            n = 1 + max([int(x["rule_id"][3:]) for x in d["comments"] if x.get("rule_id")] or [0])
            c.update(status="APPLIED", rule_id=c.get("rule_id") or f"PR-{n:03d}", approved_at=now_iso(),
                     approved_by=(b.get("by") or "").strip(), round_applied=cur + 1)
            c["computer_text"] = (c.get("computer_text") or "").strip() or c["rule_text"]
            c["maintenance_text"] = (f"코멘트 {c['id']} (R{c['round']}{', 대상 ' + c['target'] if c.get('target') else ''}) → "
                                     f"{c['rule_id']}, R{c['round_applied']}부터, 승인 {c.get('approved_by') or '(이름 없음)'} {c['approved_at'][:16]}. "
                                     "바꾸려면 코멘트 '폐기' 후 새 코멘트")
            c["needs_review"] = c["computer_text"] == c["rule_text"]     # same sentence for both views: a person checks
        if b.get("done"):                                     # base fix done in STEP 6~9
            c.update(status="APPLIED", approved_at=now_iso(), approved_by=(b.get("by") or "").strip(), round_applied=cur + 1)
        if b.get("hold"):
            c["status"] = "HOLD"
        if b.get("retire"):
            c["status"] = "RETIRED"
            c["retired_round"] = cur + 1
    save_rules(pdir, d)
    return d


# ------------------------------------------------------------------ 3D 구현 프롬프트
def build_prompt(project: str, n: int, v: dict, base: dict, meta: dict, recs: list, tf: dict, rules: list, model_json: str,
                 common: dict | None = None) -> str:
    from collections import Counter
    cnt = Counter(r["entity_id"] for r in recs)
    fit = Counter(r["geometry"]["type"] for r in recs if r["entity_id"] == "E-FITTING")
    mount = Counter(r["geometry"]["mount"] for r in recs if r["entity_id"] == "E-JB")
    sp = Counter(r["attributes"].get("type") for r in recs if r["entity_id"] == "E-SUPPORT")
    jbt = " · ".join(f"≤{lim}P {w}×{h}×{d}" for lim, (w, h, d) in JB_TYPICAL[:-1]) + f" · 그 이상 {JB_TYPICAL[-1][1][0]}×{JB_TYPICAL[-1][1][1]}×{JB_TYPICAL[-1][1][2]}"
    g = lambda k, d="": v.get(k, d)
    active = [r for r in rules if r["status"] == "APPLIED" and r["kind"] == "PROMPT"]
    L = []
    a = L.append
    a(f"# 3D 구현 프롬프트 — 계장 (T1-CI) · {project} · R{n}")
    a("")
    a(f"버전: R{n} · scope {meta['scope_rev']} · rule {meta['rule_rev']} · model {meta['model_rev']} · 작성 {now_iso()} · 생성 pid_io")
    a("")
    a("## 0. 역할과 결과물")
    a("당신은 계장 3D 개념설계 모델러입니다. 아래 **기준 Seed(배관 3D)** 복제본에 **계장 레이어**를 추가한 HTML 한 개를 만듭니다.")
    a(f"- 결과 파일명: `{PROFILE}_Seed03_R{n}_AI.html` (원본 Seed는 수정·덮어쓰기 금지, 복제본에 추가만)")
    a(f"- 기준 Seed: `{base['file']}` SHA-256 `{base['sha256']}` · Three.js {base.get('three', '0.164.1')} (importmap · OrbitControls 그대로, 버전 변경·새 외부 라이브러리 금지)")
    a("- 배관·장비·랙 등 Seed 객체는 **읽기만** (삭제·이동·색 변경 금지). 계장 객체는 별도 그룹 `inst_*` 레이어에.")
    a(f"- 모든 계장 객체의 위치·치수는 **데이터 파일 `{model_json}`(STRUCTURED_MODEL_DATA, DELTA)의 records**를 그대로 씁니다. 좌표를 임의로 옮기거나 객체를 추가·생략하지 마세요. 문제를 발견하면 고치지 말고 끝의 '보고'에 object_id로 적습니다.")
    a("- 물량의 기준은 `01_scope.csv`·`05_validation.csv`입니다. 3D는 물량을 바꾸지 않습니다.")
    a("")
    a("## 1. 좌표")
    a("- Seed 좌표계: X 동쪽, Y 위(EL), Z 남쪽, 단위 m, 원점 = Seed 원점 (Rack A × E-W 랙 교점).")
    a(f"- records의 좌표는 이미 Seed 좌표계입니다 (PLOT 변환 {tf['formula']}, 장비 기준 잔차 중앙값 {tf['median_m']} m · 최대 {tf['max_m']} m - 다시 변환하지 마세요).")
    a("")
    a("## 2. 그릴 것 (레이어 · 데이터 · 형상)")
    a(f"레이어 이름(체크박스로 켜고 끄기): `inst_tray`(트레이·트렌치·피팅), `inst_cable`(케이블), `inst_jb`(JB·JB 서포트), `inst_support`(트레이 서포트·조인트). 객체 수 = records 수와 같아야 합니다.")
    a("")
    a(f"### 2-1. 사다리 트레이 (E-ROUTE_SEGMENT, kind = ladder_on_rack / ladder_on_supports) — {sum(1 for r in recs if r['entity_id'] == 'E-ROUTE_SEGMENT' and r['attributes'].get('kind') != 'ug_trench')}개")
    a(f"- geometry: a→b = 1단 바닥 중심선, width_m = 폭, height_m = 레일 높이({g('tray_height')} mm), tiers = 단 수, tier_pitch_m = 단 간격({g('sp_tier_gap')} mm).")
    a("- 형상: 양쪽 C형 레일(웨브 4 mm × 레일 높이, 위·아래 플랜지 30 mm, 안쪽으로) + 러그(가로대) 300 mm 간격(폭 × 20 × 40 mm). 단이 여럿이면 tier_pitch_m씩 위로 같은 형상.")
    a("- 색: 랙 위 하늘색, AG 서포트 위 파랑, 금속 질감. 통신 트레이(구분 '통신')는 같은 형상, 속성에 표시.")
    a("")
    a(f"### 2-2. UG 트렌치 (kind = ug_trench) — {sum(1 for r in recs if r['attributes'].get('kind') == 'ug_trench')}개")
    a("- a→b = 트렌치 바닥 중심선(EL 음수), width_m = 안쪽 폭. 형상: 콘크리트 U형(바닥 100 mm, 벽 두께 100 mm, 벽은 지면 EL 0까지) + 반투명 덮개(두께 50 mm, 지면). tiers > 1이면 단마다 브래킷 선반.")
    a("")
    a(f"### 2-3. 트레이 꺾임 피팅 (E-FITTING) — {cnt.get('E-FITTING', 0)}개: " + ", ".join(f"{k} {v_}" for k, v_ in fit.items()))
    a(f"- geometry.type: ELBOW_90_H(수평 90° 엘보), TEE_H(수평 티), CROSS_H(수평 크로스), REDUCER(폭 변경). point = 교점, dirs = 이어지는 방향들(XZ 단위벡터), width_m = 가장 넓은 폭, radius_m = 엘보 안쪽 반경({g('sp_fit_r')} mm), tiers = 단 수.")
    a("- 형상: 트레이와 같은 레일·러그를 곡선으로 (엘보는 반경 radius_m의 1/4 원호, 티·크로스는 곡선 모서리). 피팅 구간만큼 직선 트레이를 겹치지 말고 끝에서 이어지게.")
    a("- **extend**: 랙마다 차선(lane)과 케이블 단 EL이 달라 트레이 끝이 피팅까지 닿지 않는 곳입니다. 각 항목의 tray를 from → to까지 같은 형상으로 연장해서 피팅에 붙이세요 (빈틈 금지).")
    a("- **drop_m** ≠ 0: 두 랙의 케이블 단 높이 차. 피팅 위치에서 수직 오프셋(수직 엘보 2개, 반경 radius_m)으로 높이를 맞춥니다. 케이블도 따라 내려갑니다.")
    a("- 데이터에 없는 꺾임을 새로 만들지 마세요.")
    a("")
    a(f"### 2-4. 간선 케이블 (E-CABLE 중 kind ≠ 분기, 그리고 트레이의 geometry.cable_section)")
    a("- 트레이·트렌치 안 케이블은 **cable_section 배열대로** 원통으로 그립니다: [cable, tier, x_m(왼쪽 벽에서), y_m(단 바닥에서), od_mm] → 트레이 길이 방향 원통, 지름 = od_mm.")
    a("  '왼쪽 벽' = a→b 방향을 볼 때 왼쪽. 단 n의 바닥 = 1단 바닥 + (n−1) × tier_pitch_m. 사다리는 러그 윗면(+22 mm)에 얹힘.")
    a("- 색: 멀티·패키지·MCC 보라, 통신(광) 분홍. 단면에서 꽉 찬 원으로 보이게 양면 재질.")
    a("- 트레이 밖 구간(JB → 랙 오르내림 라이저)은 E-CABLE의 polyline 중 **수직 마디만** 그립니다.")
    a("- **수직 단면 보기(Section view)** 기능: X/Z 위치 슬라이더 + '트레이 클릭 → 그 트레이 직각 단면'(카메라를 트레이 축 정면으로, 잘린 면에 케이블 원 캡). 기존 Seed의 Y 단면과 함께 동작. 잘린 쪽 객체는 클릭 안 되게.")
    a("")
    a(f"### 2-5. JB와 JB 타피컬 서포트 (E-JB) — {cnt.get('E-JB', 0)}개 (" + ", ".join(f"{k} {v_}" for k, v_ in mount.items()) + ")")
    a(f"- 외형: geometry.box_mm = 폭 × 높이 × 깊이 (일반값 타피컬: {jbt} mm, SUS 회색 금속, 앞면 문 테두리, 아래면 케이블 글랜드 표시 원).")
    a("- 위치: point = JB **하단 중앙**, bottom_el_m = 하단 EL. JB 앞면은 가장 가까운 트레이/랙 반대쪽(통로 쪽)을 향함.")
    a("- geometry.mount = RACK_COLUMN_BRACKET: 가장 가까운 랙 기둥(Seed 랙 기둥) 옆면에 C75×40 채널 2개를 수평으로(JB 상·하단 높이) 클램프로 붙이고 JB를 채널에 볼트 고정. 기둥과 JB 사이 100 mm.")
    a("- geometry.mount = PIPE_STAND: 2\" 파이프 스탠드(Ø60.3 mm, 높이 = 하단 EL + JB 높이 + 100 mm), 베이스 플레이트 250×250×12 mm, 콘크리트 패드 400×400×150 mm(지면). JB는 스탠드 앞면에 U볼트 브래킷 2개로.")
    a("- JB 아래 → 트레이까지 멀티 케이블 라이저(수직)를 2-4 규칙으로.")
    a("")
    a(f"### 2-6. 트레이 서포트 (E-SUPPORT) — " + ", ".join(f"{k} {v_}" for k, v_ in sp.items()) + f", 익스펜션 조인트(E-JOINT) {cnt.get('E-JOINT', 0)}")
    a(f"- 주 부재 {g('sp_member')} (포스트·팔·빔). point = 트레이 받침 높이의 서포트 중심.")
    a("- RT 랙 위 T: 랙 빔 위 포스트 + 단마다 양팔(팔 길이 = 트레이 폭 합 + " + str(g('sp_arm_add')) + " mm). RF 랙 위 보조: 랙 빔 사이 짧은 보조 빔(피팅 끝 600 mm 안). RC 클램프: 레일을 랙 빔에 누르는 홀드다운 클램프(작은 금속 블록 2개).")
    a("- L형: 바닥 포스트 + 한쪽 팔(캔틸레버). T형: 포스트 + 양팔. 문형(H): 포스트 2 + 단마다 빔. 바닥에 베이스 플레이트.")
    a("- UB 트렌치 브래킷: 트렌치 벽에 단마다 채널 브래킷. 조인트: 익스펜션 스플라이스 플레이트(레일 양쪽 덧판, 빨간 표시).")
    a("")
    a("## 3. 그리지 않을 것 (데이터에는 있음, 물량은 7종에 그대로)")
    a("- 계기(E-INSTRUMENT)와 계기 스탠드, 분기 케이블(E-CABLE kind = 분기), Perforated 트레이(E-PERFORATED). 계기 위치 다수가 '추정'이라 배치하지 않음 (사용자 결정 2026-11-27).")
    a("- 데이터에 없는 객체 (임의의 트레이·케이블·장비).")
    a("")
    a("## 4. 공간 설계 기준 (설계 가이드 = 현재 체크리스트·설정 값)")
    rows = [
        ("랙 위 트레이 EL", "Seed 랙의 케이블 단 EL (RK.cable)" if str(g("rack_el_src")).startswith("3D") else f"{g('rack_el')} m"),
        ("계장 차선 (랙 폭 방향)", g("tw_lane")), ("랙 가장자리 여유", f"{g('tw_margin')} m"), ("다른 공종과 이격", f"{g('tw_gap')} m"),
        ("충돌 시", f"{g('tw_yield')} · 위로 비키면 {g('tw_step')} m씩 최대 {g('tw_max_up')}단"),
        ("랙 밖 간선", f"{g('trunk_off')} (AG EL {g('sup_el')} m / UG 깊이 {g('ug_depth')} m)"),
        ("JB 하단 EL", f"{g('jb_el')} m"), ("JB 자리", f"랙 기둥에서 {g('rack_off')} m · 장비에서 {g('eq_off')} m · 3D 장비 상자 안 금지 ({g('slot_3d_eq')})"),
        ("룸 인입 EL", f"{g('room_el')} m"),
        ("트레이 폭 / 높이 / Fill", f"{g('tray_widths')} mm / {g('tray_height')} mm / {g('tray_fill')}"),
        ("통신 · IS 별도 트레이", f"{g('sep_comm')} · {g('sep_is')} (같은 구간이면 나란히 100 mm 띄움)"),
        ("적층 단 간격", f"{g('sp_tier_gap')} mm"), ("트렌치 폭 / 단 높이", f"{g('ug_widths')} mm / {g('ug_height')} mm"),
        ("서포트 간격 상한 / 랙 빔 간격", f"{g('sp_span')} m / {g('sp_bay')} m"),
        ("피팅 서포트", f"피팅 끝에서 {g('sp_fit_d')} mm 안 (NEMA VE 2), 엘보 반경 {g('sp_fit_r')} mm"),
        ("익스펜션", f"ΔT {g('sp_dt')} °C · 이동량 {g('sp_gap')} mm/조인트"),
    ]
    a("| 기준 | 값 |")
    a("|---|---|")
    for k, x in rows:
        a(f"| {k} | {x} |")
    a("")
    a("## 5. 표현 · 속성")
    a("- 객체 클릭 → 팝업에 records의 attributes 전부 + object_id + 좌표. 트레이 팝업에는 단면 그림(케이블 번호·외경)과 '이 트레이 단면 보기' 버튼.")
    a("- 레이어 패널에 '계장 찾기' 입력칸: object_id 또는 태그·JB·트레이·케이블 번호 → 그 객체로 카메라 이동 + 팝업.")
    a("- object_id 없는 객체를 만들지 않습니다. 계장 객체의 userData에 object_id·scope_ids·rule_id를 넣습니다.")
    a("")
    a("## 6. 코멘트 반영 규칙 (사람 승인, 이전 Rev에서 누적)")
    if active:
        for r in active:
            a(f"- **{r['rule_id']}** (R{r.get('round_applied', '?')}, {r.get('scope', '프로젝트')}){' 대상 ' + r['target'] if r.get('target') else ''}: "
              f"{r.get('computer_text') or r['rule_text']}"
              + (f" — (번역 확인 전, 기준인 엔지니어 원문: {r['rule_text']})" if r.get("needs_review") and r.get("computer_text") != r["rule_text"] else ""))
    else:
        a("- (아직 없음 - R0)")
    retired = [r for r in rules if r["status"] == "RETIRED" and r.get("rule_id")]
    if retired:
        a("- 폐기된 규칙(적용하지 말 것): " + ", ".join(r["rule_id"] for r in retired))
    a("")
    if common:
        from .common_rules import render, state, master_text
        a(f"## 6-1. 공통 프로토콜 v{common.get('version')} — 컴퓨터 관점 (번역본)")
        a("- 기준은 엔지니어 관점(마스터)입니다 (COMMON_PROTOCOL.md). 아래 번역본이 마스터와 다르게 읽히면 **마스터를 따르세요**.")
        for r in common.get("rules", []):
            if not r.get("master"):
                a(f"- **{r['id']}**: {r.get('text', '')}")
                continue
            st = state(r, "computer")
            tr = render(((r.get("translations") or {}).get("computer") or {}).get("text"), r.get("params") or {})
            if st in ("다시 번역 필요", "질문 있음"):
                a(f"- **{r['id']} {r.get('title', '')}** (번역 {st} - 마스터 원문을 따름): {master_text(r)}")
            else:
                a(f"- **{r['id']} {r.get('title', '')}**{'' if st == '확정' else ' (번역 확인 전)'}: {tr}")
        a("")
    a("## 7. 끝나면 확인하고 보고")
    a("1. 레이어별 객체 수 = records 수 (계기·분기·Perforated 제외).")
    a("2. 트레이 1개를 골라 단면 보기 → cable_section 개수만큼 원이 보이는지.")
    a("3. JB 30개 모두 mount 형식대로 서포트가 붙었는지, 공중에 뜬 JB 없는지.")
    a("4. Seed 객체 수·위치가 원본과 같은지 (배관·장비·랙 변경 0).")
    a("5. 보고: 그리면서 이상했던 곳을 object_id로 (예: 트레이가 장비를 지나감, JB가 기둥에서 멂). 고치지 말고 적기만.")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ PLOT 마크업 그림
def markup_png(plot_png: Path, plot_size, res, tr, layout, v, dec: dict, out: Path):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(plot_png).convert("RGB")
    k = im.width / float(plot_size[0])
    S = lambda p: (p[0] * k, p[1] * k)
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(9, int(im.width / 160)))
    except Exception:                                      # noqa: BLE001
        font = ImageFont.load_default()
    for r in (layout.rack_rects(float(v["rack_width"])) if layout else []):
        d.rectangle([*S(r[:2]), *S(r[2:4])], fill=(44, 127, 192, 45), outline=(44, 127, 192, 160))
    for poly in (dec.get("racks_add") or []):
        d.line([S(p) for p in poly], fill=(220, 0, 120, 200), width=max(3, int(6 * k)))
    edited = set((dec.get("routes_edit") or {}).keys())
    col = {"jb": (240, 138, 36, 200), "pkg": (209, 51, 93, 200), "irp": (126, 102, 203, 200), "comm": (79, 161, 224, 200)}
    for r in ((res.get("geo") or {}).get("routes") or []):
        d.line([S(p) for p in r["poly"]], fill=(224, 0, 42, 255) if r["rid"] in edited else col.get(r["kind"], (120, 120, 120, 200)),
                width=max(2, int((4 if r["rid"] in edited else 2) * k)))
    kind_over = set((dec.get("tray_kind") or {}).keys()) | set((dec.get("tray_size") or {}).keys())
    for sg in tr.get("segments") or []:
        a, b = sg["poly"]
        if sg["id"] in kind_over:
            d.line([S(a), S(b)], fill=(220, 0, 120, 255), width=max(4, int(7 * k)))
        elif sg["kind"] == "UG":
            d.line([S(a), S(b)], fill=(138, 109, 0, 230), width=max(2, int(3 * k)))
        else:
            w = max((t["width"] for t in sg["trays"]), default=300)
            d.line([S(a), S(b)], fill=(11, 61, 145, 230) if w >= 900 else (44, 127, 192, 230) if w >= 600 else (95, 180, 234, 230),
                   width=max(2, int((2 + w / 300) * k)))
    moved = set((dec.get("jb_moves") or {}).keys())
    for j in ((res.get("geo") or {}).get("jbs") or []):
        x, y = S((j[1], j[2]))
        r_ = max(3, 5 * k)
        d.rectangle([x - r_, y - r_, x + r_, y + r_], fill=(240, 138, 36, 255), outline=(224, 0, 42, 255) if j[0] in moved else (255, 255, 255, 255),
                    width=3 if j[0] in moved else 1)
        d.text((x + r_ + 2, y - r_), j[0].replace("JB-", ""), fill=(60, 40, 0, 255), font=font)
    im = Image.alpha_composite(im.convert("RGBA"), over)
    lg = Image.new("RGBA", (int(im.width * 0.36), int(im.width * 0.15)), (255, 255, 255, 235))
    dl = ImageDraw.Draw(lg)
    items = [((44, 127, 192), "랙 (인식/3D)"), ((95, 180, 234), "사다리 300"), ((44, 127, 192), "사다리 600"), ((11, 61, 145), "사다리 900"),
             ((138, 109, 0), "UG 트렌치"), ((240, 138, 36), "JB"), ((224, 0, 42), "사람이 고친 경로·옮긴 JB"), ((220, 0, 120), "사람이 그린 랙·바꾼 트레이")]
    kf = font
    cands = [Path("C:/Windows/Fonts/malgun.ttf"), Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
             *sorted(Path("/usr/share/fonts").glob("**/*CJK*Regular*.tt*")),
             *sorted(Path("/usr/share/fonts").glob("**/*Nanum*.ttf"))]
    for fp in cands:
        try:
            kf = ImageFont.truetype(str(fp), max(10, int(im.width / 110)))
            break
        except Exception:                                  # noqa: BLE001
            continue
    h_ = lg.height / (len(items) / 2 + 0.5)
    for i, (c, t) in enumerate(items):
        x0, y0 = (i % 2) * lg.width / 2 + 8, (i // 2) * h_ + 6
        dl.rectangle([x0, y0 + h_ * .25, x0 + h_ * .8, y0 + h_ * .65], fill=c)
        dl.text((x0 + h_, y0 + h_ * .15), t, fill=(0, 0, 0), font=kf)
    im.alpha_composite(lg, (im.width - lg.width - 10, 10))
    im.convert("RGB").save(out, optimize=True)


# ------------------------------------------------------------------ Base 요약
def base_summary(project: str, n: int, meta: dict, items: list, v: dict, defaults: dict, names: dict, corr: list, sources: list,
                 prev: dict | None, rules: list, zip_list: list, p11: list | None = None) -> str:
    L = []
    a = L.append
    a(f"# Base 요약 — 계장 (T1-CI) · {project} · R{n}")
    a("")
    a(f"scope {meta['scope_rev']} · rule {meta['rule_rev']} · model {meta['model_rev']} · {now_iso()} · 상태 DRAFT_NOT_READY (공종 승인 전)")
    a("")
    a("Base = 산출근거(pid_io 계산: 체크리스트 + STEP 6~9 설정 + 사람 결정) + PLOT 마크업(`PLOT_MARKUP.png`). 원본 큰 파일은 제출하지 않고 아래 '원본 목록'으로 참조합니다.")
    a("")
    a("## 1. 물량 요약 (01_scope.csv와 같음)")
    a("| scope_id | 항목 | 규격 | 단위 | 물량 | 여유(margin) | Rule |" + (" R" + str(prev["round"]) + " 대비 |" if prev else ""))
    a("|---|---|---|---|---|---|---|" + ("---|" if prev else ""))
    pq = (prev or {}).get("qty") or {}
    for x in items:
        if x["disposition"] != "DIRECT":
            continue
        diff = ""
        if prev:
            o = pq.get(x["scope_id"])
            diff = " | 신규" if o is None else (f" | {x['value'] - o:+g}" if x["value"] != o else " | -")
        a(f"| {x['scope_id']} | {x['item_name']} | {x['spec']} | {x['unit']} | {x['value']:g} | {'' if x['margin'] is None else format(x['margin'], 'g')} | {x['rule_id']}{diff} |")
    for k in pq:
        if prev and k not in {x["scope_id"] for x in items}:
            a(f"| {k} | (없어짐) | | | 0 | | | {-pq[k]:+g} |")
    a("")
    a("범위 밖: " + "; ".join(f"{x['scope_id']} {x['item_name']} = {x['disposition']} ({x['exclude']})" for x in items if x["disposition"] != "DIRECT"))
    a("")
    a("## 2. 기본값과 다른 설계 가정 (현재 값)")
    ch = [(k, names.get(k, k), v.get(k), d_) for k, d_ in defaults.items() if v.get(k) != d_]
    if ch:
        a("| 설정 | 현재 | 기본값 |")
        a("|---|---|---|")
        for k, nm, cur, d_ in ch:
            a(f"| {nm} (`{k}`) | {cur} | {d_} |")
    else:
        a("(없음)")
    a("")
    a("## 3. 사람 결정 (원도 보정 · 배치 수정) — 자세히 evidence/correction_log.csv")
    from collections import Counter
    for kind, c in Counter(x["kind"] for x in corr).items():
        a(f"- {kind}: {c}건")
    a("")
    a(f"## 4. 이번 Rev(R{n})에 반영한 코멘트")
    now_ = [r for r in rules if r.get("round_applied") == n]
    if now_:
        for r in now_:
            a(f"- {r['id']} → {r.get('rule_id') or 'Base 수정'}: \"{r['text']}\"" + (f" (대상 {r['target']})" if r.get("target") else ""))
    else:
        a("- 없음" + (" (R0 기준선)" if n == 0 else ""))
    a("")
    a("## 5. 3D와 PLOT이 다른 곳 (프로토콜 P11) — 자세히 evidence/plot_vs_3d.csv")
    p11 = p11 or []
    if p11:
        a("| 구분 | 항목 | 3D | 물량 영향 | 판정 | 조치 |")
        a("|---|---|---|---|---|---|")
        big = lambda x: x[5] == "HOLD" or "큰 차이" in x[5]
        a("그림은 3D를 따르고 물량은 Base 그대로입니다 (P11). 아래는 차이 기록이며 질문이 아닙니다.")
        a("")
        for r in [x for x in p11 if big(x)] + [x for x in p11 if not big(x) and x[0] != "높이"][:12]:
            a(f"| {r[0]} | {r[1]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |")
    else:
        a("- 없음 (3D 모델 없음)")
    a("")
    a("## 6. 원본 목록 (제출하지 않음 · 요청 시 제공)")
    a("| source_id | 파일 | Rev | authority | SHA-256 |")
    a("|---|---|---|---|---|")
    for s in sources:
        a(f"| {s['source_id']} | {s['filename']} | {s['revision']} | {s['authority']} | {(s.get('checksum') or '')[7:23]}… |")
    a("")
    a("## 7. 이 제출 묶음")
    for z in zip_list:
        a(f"- {z}")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ 제출 zip
SUBMIT_EVIDENCE = ("correction_log.csv", "model_checks.json", "pid_io_audit.csv", "plot_vs_3d.csv", "COMMON_PROTOCOL.md", "COMMON_PROTOCOL.json")


def make_zip(pkg: Path, n: int, seven_only: bool = False) -> Path:
    z = pkg / f"{PROFILE}_R{n}_제출{'_7종' if seven_only else ''}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(pkg.iterdir()):
            if f.is_file() and f.suffix != ".zip" and (not seven_only or re.match(r"^0\d_", f.name)):
                zf.write(f, f.name)
        if not seven_only:
            for f in sorted((pkg / "model").iterdir()):
                zf.write(f, f"model/{f.name}")
            for f in sorted((pkg / "evidence").iterdir()):
                if f.name in SUBMIT_EVIDENCE or f.name.startswith("run_"):
                    zf.write(f, f"evidence/{f.name}")
    return z


def zip_list(seven_only=False) -> list:
    l = ["00_manifest.json ~ 06_model_handoff.json (표준 7종)"]
    if not seven_only:
        l += ["model/ 보강 모델 HTML + STRUCTURED_MODEL_DATA (DELTA)", PROMPT_NAME + " (회사 AI용 3D 구현 프롬프트)",
              "BASE_SUMMARY.md + PLOT_MARKUP.png", "checkpoint_*.json (회사 Copilot RESUME)",
              "evidence/ COMMON_PROTOCOL.md (공통 프로토콜, 엔지니어 · 컴퓨터 · 유지보수 관점) · plot_vs_3d.csv (3D와 PLOT 차이, P11) · run_*.json · correction_log.csv · model_checks.json · pid_io_audit.csv (큰 근거 파일은 참조)"]
    return l


# ------------------------------------------------------------------ AI가 그린 3D를 패키지에 붙이기
def attach_ai_model(pkg: Path, n: int, src: Path) -> dict:
    """the company AI's model becomes the SUPPLEMENTED_MODEL of this round; our program's drawing stays as a reference."""
    dst = pkg / "model" / f"{PROFILE}_Seed03_R{n}_AI.html"
    shutil.copy2(src, dst)
    h6p = pkg / "06_model_handoff.json"
    h6 = json.loads(h6p.read_text(encoding="utf-8"))
    ref = [x for x in h6["artifacts"] if x["kind"] == "SUPPLEMENTED_MODEL" and not x["path"].endswith("_AI.html")]
    for x in ref:
        x["kind"] = "SUPPORTING_FILE"
        x["note"] = "pid_io 참고 그림 (회사 AI 작성본이 SUPPLEMENTED_MODEL)"
    h6["artifacts"] = [x for x in h6["artifacts"] if not x["path"].endswith("_AI.html")]
    h6["artifacts"].insert(0, {"path": f"model/{dst.name}", "kind": "SUPPLEMENTED_MODEL", "sha256": sha(dst), "size_bytes": dst.stat().st_size,
                               "note": f"회사 AI가 {PROMPT_NAME} R{n}로 작성"})
    for c in h6["checks"]:
        if c["check_id"] in ("BASELINE_INTEGRITY", "GEOMETRY_ATTRIBUTES", "REPRODUCIBILITY"):
            c["status"] = "HOLD"
            c["evidence"] = ("AI 작성본: 사람이 원본 Seed와 열어 비교 필요 (자동 바이트 대조는 pid_io 참고 그림에만). " + c["evidence"])[:600]
    h6p.write_text(json.dumps(h6, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"file": dst.name, "sha256": sha(dst)}


# ------------------------------------------------------------------ v13.9 코파일럿 대화 (프로토콜 P12)
GUIDE_NAME = "COPILOT_GUIDE.md"
ANSWERS_NAME = "COPILOT_ANSWERS.json"
ANSWERS_FORMAT = "pid_io-copilot-answers-1"
ANSWER_FIELDS = ("id", "about", "picture", "question", "recommendation", "answer", "what", "reason", "scope", "kind", "by")


def _rule_text(common: dict, rid: str, view: str = "computer") -> str:
    from .common_rules import master_text, render, state
    r = next((x for x in (common or {}).get("rules", []) if x["id"] == rid), None)
    if not r:
        return ""
    if state(r, view) in ("다시 번역 필요", "질문 있음"):
        return master_text(r)
    return render(((r.get("translations") or {}).get(view) or {}).get("text"), r.get("params") or {})


def answers_template(project: str, n: int) -> dict:
    return {"format": ANSWERS_FORMAT, "project": project, "round": f"R{n}",
            "how": "코파일럿이 사람과 대화한 뒤 items에 한 건씩 적는다. reason(왜)과 scope(이번만 / 항상)가 빠진 항목은 pid_io가 읽지 않고 되돌린다.",
            "items": []}


def copilot_guide(project: str, n: int, common: dict, p11: list, rules: list, picks: list | None = None) -> str:
    """the conversation guide for VS Code Copilot (Korean). The rule itself is P12 of the common protocol - this file
    only puts it next to this round's material."""
    from .common_rules import master_text
    p12 = next((x for x in (common or {}).get("rules", []) if x["id"] == "P12"), None)
    mq = ((p12 or {}).get("params") or {}).get("max_q", 5)
    L = []
    a = L.append
    a(f"# 코파일럿 대화 안내 — {project} · R{n}")
    a("")
    a("> 이 파일은 VS Code 코파일럿이 읽고 사람과 **한국어로** 대화하기 위한 안내입니다. 규칙의 원본은 공통 프로토콜 "
      "P12 · P11의 엔지니어 관점(마스터)이고, 여기 글과 다르면 마스터(COMMON_PROTOCOL.md)를 따릅니다.")
    a("")
    a("## 1. 너의 역할")
    a("- 사람이 3D 결과(AI가 그린 3D)를 보고 한 코멘트를 **규칙으로 바꾸는 것**이 일이다. 질문은 드물게 한다.")
    a("- 길이 · 위치 · 물량을 재거나 계산하지 않는다. 숫자는 이 폴더의 pid_io 파일(BASE_SUMMARY.md, evidence/plot_vs_3d.csv)에 있는 값만 쓴다.")
    a("- 어느 도면(PLOT / 3D)이 맞는지는 묻지 않는다. 차이는 P11대로 처리되어 있다: **그림은 3D, 물량은 Base**.")
    a("")
    a("## 2. 대화 규칙 (P12)")
    a(_rule_text(common, "P12") or (master_text(p12) if p12 else "(P12 없음 - 공통 프로토콜을 확인하세요)"))
    a("")
    a("## 3. 대화 순서")
    a("1. 시작 인사 한 줄 + \"3D 보시고 코멘트 있으면 말씀해 주세요. 제가 먼저 물어볼 것은 N건이에요.\"")
    a(f"2. 아래 4번 '물어볼 후보'가 있으면 한 건씩 (최대 {mq}건): 그림 파일 이름 → 상황 한 줄 → **추천안** → 다른 선택과 결과 → \"이대로 할까요? (응 / 다르게)\"")
    a("3. 사람이 코멘트하거나 '다르게'라고 하면: \"왜요?\" 한 번. 이유를 짧게 받아 적는다.")
    a("4. \"이번만이에요, 항상이에요?\" — 이번만 = 이 프로젝트 3D 프롬프트, 항상 = 공통 프로토콜 개정안(엔지니어 승인 후).")
    a("5. 'PLOT이 옛 도면'처럼 Base 입력이 틀린 얘기면 kind = BASE 로 적고 \"새 PLOT을 넣고 pid_io를 다시 돌려야 해요\"라고 알린다.")
    a("6. 다 끝나면 6번 형식으로 답 파일을 쓰고, 사람에게 \"pid_io 앱 STEP 10 → 3D 루프 → '코파일럿 답 읽기'를 눌러 주세요\"라고 안내한다.")
    a("")
    a("예시")
    a("```")
    a("AI: Q3_OB3.png 를 열어 주세요. 3D에는 OB3 다리가 있고 PLOT에는 없어요.")
    a("    추천: 그림은 3D대로 다리를 두고, 케이블은 Base대로 다리 위로 보내지 않을게요. (케이블 변화 0 m)")
    a("    다른 길: 케이블을 다리로 보내면 +3,175 m (BASE_SUMMARY 5번 표). 이대로 할까요? (응 / 다르게)")
    a("사람: 다르게. 다리는 PLOT의 X 표시 자리에 그려.")
    a("AI: 왜요?")
    a("사람: 도로 횡단은 PLOT이 정한 자리라서.")
    a("AI: 이번만이에요, 항상이에요?")
    a("사람: 항상.")
    a("```")
    a("")
    a("## 4. 물어볼 후보 (pid_io가 찾은 것)")
    if picks:
        for i, q in enumerate(picks[:mq], 1):
            a(f"{i}. **{q.get('about', '')}** — {q.get('question', '')} 추천: {q.get('recommendation', '')}"
              + (f" (그림 {q['picture']})" if q.get("picture") else ""))
    else:
        a("- 없음. 사람의 코멘트를 기다린다. (PLOT에도 3D에도 없는 배치, 3D를 따라 그렸더니 이상한 곳이 생기면 pid_io가 여기에 올린다)")
    a("")
    a("## 5. 묻지 말 것 — 이미 P11로 처리된 차이 (참고)")
    big = [r for r in (p11 or []) if r[5] == "HOLD" or "큰 차이" in r[5]]
    for r in (big + [r for r in (p11 or []) if r not in big and r[0] != "높이"])[:10]:
        a(f"- {r[0]} · {r[1]}: {r[3]} {r[4]} → {r[6]}")
    if not p11:
        a("- (3D 모델 없음)")
    a("")
    a("## 6. 답 파일 쓰는 법")
    a(f"이 폴더의 `{ANSWERS_NAME}` 의 items 에 한 건씩 추가한다. 한 코멘트 = 한 항목.")
    a("")
    a("| 칸 | 내용 |")
    a("|---|---|")
    for k, t in (("id", "A1, A2 … (이 파일 안에서 겹치지 않게)"), ("about", "대상 (예: OB3 오버브리지, 10-TK-801 주변 트레이)"),
                 ("picture", "보여 준 그림 파일 이름 (없으면 빈칸)"), ("question", "AI가 물은 말 (사람이 먼저 코멘트했으면 빈칸)"),
                 ("recommendation", "AI 추천안 (없으면 빈칸)"), ("answer", "응 / 다르게 / 코멘트"),
                 ("what", "3D에 무엇을 어떻게 그릴지 한 문장 (숫자는 pid_io 값만)"), ("reason", "왜 — 사람이 말한 이유 (필수)"),
                 ("scope", "이번만 / 항상 (필수)"), ("kind", "3D (그리는 법) / BASE (PLOT · 산출근거 입력이 틀림)"), ("by", "답한 사람 이름")):
        a(f"| {k} | {t} |")
    a("")
    a("```json")
    a(json.dumps({"id": "A1", "about": "OB3 오버브리지", "picture": "Q3_OB3.png", "question": "그림은 3D대로 둘까요?",
                  "recommendation": "다리는 3D대로, 케이블은 Base대로", "answer": "다르게", "what": "OB3 다리를 PLOT의 X 표시 자리에 그린다",
                  "reason": "도로 횡단 위치는 PLOT이 정한다", "scope": "항상", "kind": "3D", "by": "홍길동"}, ensure_ascii=False))
    a("```")
    a("")
    a("## 7. 지금 프롬프트에 들어 있는 규칙 (중복 코멘트 피하기)")
    on = [c for c in rules if c.get("status") == "APPLIED" and c.get("rule_id")]
    for c in on:
        a(f"- {c['rule_id']}: {c.get('computer_text') or c.get('rule_text')}")
    if not on:
        a("- 없음")
    a("")
    return "\n".join(L)


def import_answers(pdir: Path, data: dict) -> dict:
    """COPILOT_ANSWERS.json -> comments (OPEN, a person approves in STEP 10). scope 이번만 -> 프로젝트, 항상 -> 공통.
    kind BASE -> a Base-fix comment. Missing reason / scope -> HOLD (sent back, not imported). Same item twice -> skipped."""
    if (data or {}).get("format") != ANSWERS_FORMAT:
        raise ValueError(f"답 파일 형식이 다릅니다 (format = {ANSWERS_FORMAT} 이어야 함)")
    d = load_rules(pdir)
    have = {c.get("answer_key") for c in d["comments"] if c.get("answer_key")}
    added, hold, skipped = [], [], []
    for it in data.get("items") or []:
        it = {k: str(it.get(k) or "").strip() for k in ANSWER_FIELDS}
        key = hashlib.sha256(json.dumps([data.get("round"), it], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        if key in have:
            skipped.append(it["id"])
            continue
        why = [w for w, bad in (("이유(reason) 없음", not it["reason"]), ("범위(scope: 이번만 / 항상) 없음", it["scope"] not in ("이번만", "항상")),
                                ("무엇을(what) 없음", not it["what"])) if bad]
        if why:
            hold.append({"id": it["id"], "why": ", ".join(why)})
            continue
        base = it["kind"].upper() == "BASE"
        comment_update(pdir, {"add": {"text": f"{it['what']} (이유: {it['reason']})", "target": it["about"],
                                      "kind": "BASE" if base else "PROMPT", "rule_text": f"{it['what']} — 이유: {it['reason']}",
                                      "scope": "공통" if it["scope"] == "항상" else "프로젝트", "by": it["by"]}})
        d = load_rules(pdir)
        c = d["comments"][-1]
        c.update(answer_key=key, src="copilot", answer=it)
        save_rules(pdir, d)
        have.add(key)
        added.append(c["id"])
    return {"added": added, "hold": hold, "skipped": skipped}
