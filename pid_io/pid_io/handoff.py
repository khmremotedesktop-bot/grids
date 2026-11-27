"""Company handoff package, AI3D-HANDOFF-1.1 (회사 가이드 Rev.6, 과제 1 · T1-CI 계장) - v13.5.

Writes, next to the app's own 3D handoff files, one standard package folder

    T1-CI_scopeRevNN_ruleRevNN/
        00_manifest.json  01_scope.csv  02_input_model_contract.json  03_engineering_rules.json
        04_test_inputs.json  05_validation.csv  06_model_handoff.json
        checkpoint_T1-CI_<stage>_R<YYYYMMDD-HHMMSS>.json
        model/     T1-CI_Seed03_<model_rev>.html (SUPPLEMENTED_MODEL) + .json (STRUCTURED_MODEL_DATA, DELTA)
        evidence/  run_<case>.json, pid_io_audit.csv, correction_log.csv, model_checks.json, 3D review, protocol, settings

Field names follow the guide exactly. What only people can give (approvals, reviewer names, independent expected
values) is left empty / PENDING / HOLD and the package stays DRAFT_NOT_READY - the guide asks for exactly that.
Expected values for 05 come from the project's validation plan (validation_plan.json), locked by an engineer
before the run (expected_locked_at < executed_at); a case without locked values is HOLD.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path

SCHEMA = "AI3D-HANDOFF-1.1"
PROFILE, TASK, DISC = "T1-CI", "T1", "CI"
INSTRUCTION_REV = "R9-G6"
GUIDE_SEED_SHA = "35d0e456ad1bbb7fe95a8046adcd96e7c56fc52aba4f7aeafa1f9d498fd79f9a"   # 03_3D_Digital_Twin_Final.html
TZ = "+09:00"

KIND_CODE = {"분기": "BR", "멀티": "MU", "패키지": "PK", "MCC": "MC", "통신": "CM"}
KIND_RULE = {"분기": "R-CB-BRANCH", "멀티": "R-CB-MULTI", "패키지": "R-CB-PKG", "MCC": "R-CB-MCC", "통신": "R-CB-COMM"}
CLS_CODE = {"신호": "SIG", "IS": "IS", "통신": "COM"}
IO_TYPES = ("AI", "AO", "DI", "DO")
PLOT_RULES = ("R-CB-", "R-TR", "R-UG", "R-PT", "R-SP", "R-JB")    # quantities that need the plot plan coordinates


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S") + TZ


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def slug(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(s).upper().replace("×", "X"))[:24] or "X"


# ------------------------------------------------------------------ scope (01) and quantities
def scope_items(rows, res, tr, sp, v) -> list:
    """every quantity item of this profile with a stable ID, its rule and its current value (unit as in 01)."""
    out = []

    def add(sid, name, itype, spec, unit, rule, value, margin=None, include="", exclude="", source="SRC-PID", locator=""):
        out.append({"scope_id": sid, "item_name": name, "item_type": itype, "spec": spec, "unit": unit, "rule_id": rule,
                    "value": value, "margin": margin, "include": include, "exclude": exclude, "source_id": source,
                    "locator": locator, "disposition": "DIRECT"})

    inst = [r for r in rows if r.kind != "function"]
    io = Counter(r.io for r in inst)
    tags = {r.tag for r in inst if r.origin != "스페어" and r.kind == "instrument"}
    add("CI-INST", "계기", "INSTRUMENT", "Tag (P&ID + Typical 파생 + 트레인·대수 복제)", "EA", "R-INST", len(tags),
        include="인덱스 행의 고유 Tag (IO 없는 현장 지시계 포함)", exclude="스페어 행, 기능(소프트) 태그", locator="Instrument Index 전체")
    for t in IO_TYPES:
        add(f"CI-IO-{t}", f"I/O {t}", "IO_POINT", f"{t} (스페어 포함)", "PT", "R-IO", io.get(t, 0),
            include="IO 1점 = 인덱스 1행, 스페어 행 포함 (H01~H04)", exclude="통신 포트, 벤더 PLC 내부 IO", locator="Instrument Index I/O Type 열")
    add("CI-IO-COMM", "통신 포트", "COMM_PORT", "Serial / Comm (패키지 · MCC)", "EA", "R-IO", io.get("Serial/Comm", 0),
        include="패키지 PLC · MCC 통신 포트 (C04 이중화면 A/B)", exclude="하드와이어 IO")
    spec = Counter()
    for c in res["cables"]:
        spec[(c["kind"], c["spec"])] += c["length"]
    for (kind, sp_), m in sorted(spec.items()):
        add(f"CI-CB-{KIND_CODE.get(kind, 'XX')}-{slug(sp_)}", f"계장 케이블 ({kind})", "CABLE", sp_, "m", KIND_RULE.get(kind, "R-CB-MULTI"),
            int(m), include="길이 = 경로 + 높이, 여유율·올림 포함 (R-CB)", exclude="MCC↔IRP 배선 (전기), 벤더 패키지 내부 배선",
            source="SRC-PLOT", locator="Cable_Schedule 시트")
    for sz, n in sorted(Counter(j["size"] for j in res["jbs"]).items()):
        add(f"CI-JB-{slug(sz)}", "정션 박스", "JB", sz, "EA", "R-JB", n, include="필드 JB · Skid JB", exclude="룸 안 마샬링 캐비닛",
            locator="JB_List 시트")
    for x in tr["summary"]["ladder"]:
        add(f"CI-TR-{CLS_CODE.get(x['cls'], slug(x['cls']))}-{x['width']}", "사다리 트레이", "LADDER_TRAY",
            f"{x['cls']} {x['width']}×{int(float(v['tray_height']))}", "m", "R-TR", x["length"], x["order"] - x["length"],
            include="랙 위 · AG 서포트 위 간선 트레이 (적층은 단 수만큼)", exclude="전기 전력 트레이, Perforated (분기)",
            source="SRC-PLOT", locator="Tray_Segments 시트")
    for x in tr["summary"].get("ug_by_width") or []:
        add(f"CI-UG-W{x['width']}" + (f"X{x['tiers']}" if x["tiers"] > 1 else ""), "UG 트렌치", "UG_TRENCH",
            f"폭 {x['width']}" + (f" × {x['tiers']}단" if x["tiers"] > 1 else ""), "m", "R-UG", x["length"], x["order"] - x["length"],
            include="랙 밖 간선 트렌치", exclude="토목 굴착·되메우기 (토목 공종)", source="SRC-PLOT", locator="Trench_Runs 시트")
    add(f"CI-PT-{v['pt_width']}", "Perforated 트레이", "PERFORATED_TRAY", f"폭 {v['pt_width']}", "m", "R-PT", tr["summary"]["pt_m"],
        include="JB → 계기 분기 케이블 1~2가닥", exclude="간선", source="SRC-PLOT", locator="Perforated_Tray 시트")
    for x in sp["summary"]["rows"]:
        add(f"CI-SP-{x['type']}", "트레이 서포트", "SUPPORT", f"{x['name']} ({x.get('typical', '')})", "EA", "R-SP", x["count"],
            include="계장 트레이 전용 서포트", exclude="파이프랙 구조 (철골 공종)", source="SRC-PLOT", locator="Support_List 시트")
    add("CI-SP-KG", "서포트 강재", "STEEL", "C100×50×5/7.5 외 (할증 별도)", "kg", "R-SP", round(sp["summary"]["kg"], 1),
        round(sp["summary"]["kg_order"] - sp["summary"]["kg"], 1), include="서포트 부재 중량", exclude="랙 빔 (철골)",
        source="SRC-PLOT", locator="Support_Summary 시트")
    add("CI-SP-EXP", "익스펜션 스플라이스", "EXPANSION_JOINT", "플레이트 세트", "SET", "R-SP-EXP", sp["summary"]["joint_plates"],
        include="NEMA VE 2 조인트 (사다리 직선 구간)", exclude="파이프랙 구조 신축 이음 (철골)", source="SRC-PLOT", locator="Expansion_Joints 시트")
    # in the profile's scope but not computed here (kept in the list, never hidden)
    out += [
        {"scope_id": "CI-X-MCCIRP", "item_name": "MCC ↔ IRP 배선", "item_type": "CABLE", "spec": "", "unit": "m", "rule_id": "",
         "value": None, "margin": None, "include": "", "exclude": "전기실 안 배선 - 전기 공종 범위 (STEP 6 'MCC 신호 출발점 = IRP')",
         "source_id": "SRC-CHECKLIST", "locator": "cable.json mcc_from", "disposition": "OTHER_PACKAGE", "owner": "EL"},
        {"scope_id": "CI-X-VENDOR", "item_name": "벤더 패키지 내부 IO · 배선", "item_type": "PACKAGE", "spec": "", "unit": "LOT", "rule_id": "",
         "value": None, "margin": None, "include": "", "exclude": "벤더 공급 범위 (체크리스트 A03, 벤더 경계)", "source_id": "SRC-CHECKLIST",
         "locator": "concept A03 / 벤더 경계", "disposition": "OTHER_PACKAGE", "owner": "VENDOR"},
        {"scope_id": "CI-X-FG", "item_name": "F&G 검지기 (GD / FD) · 알람", "item_type": "INSTRUMENT", "spec": "", "unit": "EA", "rule_id": "",
         "value": None, "margin": None, "include": "", "exclude": "P&ID에 없음 - F&G 배치도 필요 (레퍼런스 인덱스에는 있음)",
         "source_id": "SRC-REF", "locator": "레퍼런스 GD 184 · FD 82 · AA/AL 57", "disposition": "HOLD", "owner": "CI"},
    ]
    return out


def quantities(rows, res, tr, sp, v) -> dict:
    return {x["scope_id"]: x["value"] for x in scope_items(rows, res, tr, sp, v) if x["disposition"] == "DIRECT"}


# ------------------------------------------------------------------ rules (03)
def rule_defs(v) -> dict:
    """rule_id -> (title, input setting ids, steps, grouping, dedup, rounding, exceptions)."""
    f = lambda *ids: list(ids)
    return {
        "R-INST": ("계기 수", f(), [
            ("S1", "P&ID 심볼 인식 (태그 글자 + 번호 짝, 외곽선) → 검토 판단(사람) 적용 → 체크리스트 Typical 파생 · 트레인/대수 복제", "rows"),
            ("S2", "count = |{ tag : row.kind = instrument, origin ≠ 스페어 }|", "CI-INST")],
         "고유 Tag", "Tag (대소문자·공백 무시)", "정수", ["벤더 경계 안 계기는 Skid 위치로 계산하되 수량 포함"]),
        "R-IO": ("I/O 점수", f("H01", "H02", "H03", "H04", "C04"), [
            ("S1", "행 생성: 계기 1개 × 기능코드 IO 규칙(io_rules.yaml) → IO 1점 = 1행 (System: DCS/ESD/F&G)", "rows"),
            ("S2", "스페어 = ceil(n(system, io) × H01~H04 율) 행 추가 (RTD는 H01)", "spare"),
            ("S3", "count(io) = |{ row : row.io = io }| (스페어 포함), 통신 포트 = Serial/Comm 행 (C04 ON이면 A/B 2점)", "CI-IO-*")],
         "IO 종류", "행 단위 (IO 1점 = 1행)", "정수", ["IO 없는 계기(현장 지시계, PSV) = '-' 행", "벤더 PLC 내부 IO 제외 (A03)"]),
        "R-CB-BRANCH": ("분기 케이블 (계기 → JB)", f("AI_form", "DI_form", "DO_form", "route_factor", "field_min", "len_margin", "len_round", "inst_el", "jb_el"), [
            ("S1", "IO 1점 = 1가닥, 사양 = 신호별 구성 × SQ × 차폐 (STEP 6)", "spec"),
            ("S2", "L = roundup((max(수평 PLOT 거리 × 우회계수, 최소) + |계기 EL − JB EL|) × (1 + 여유율), 올림 단위)", "length"),
            ("S3", "Σ L by spec", "CI-CB-BR-*")], "사양", "케이블 번호 (C-태그)", "len_round m 올림", ["PLOT 위치 없는 계기 = 가정 길이 (len_field, '가정' 표시)"]),
        "R-CB-MULTI": ("멀티 케이블 (JB → 룸)", f("jb_sizes", "jb_spare", "multi_sq", "multi_shield_A", "multi_shield_D", "rack_el", "room_el", "len_margin", "len_round"), [
            ("S1", "JB 1개 = 멀티 1가닥, 페어 = JB 크기 (R-JB)", "spec"),
            ("S2", "경로 = 제어실에서 1 m 격자 Dijkstra (랙 1/m, 랙 밖 '랙 우선도'/m, 장애물 통과 불가)", "route"),
            ("S3", "L = roundup((랙 m + 랙 밖 m + 오르내림 높이) × (1 + 여유율), 올림)", "length"), ("S4", "Σ L by spec", "CI-CB-MU-*")],
         "사양", "케이블 번호 (MC-JB)", "len_round m 올림", ["룸 위치 미정 = JB→룸 가정 길이"]),
        "R-CB-PKG": ("패키지 제어반 → 룸 멀티", f("pkg_if", "seg_system", "jb_spare", "multi_sq"), [
            ("S1", "패키지 Typical 행을 (패키지 단위, 시스템, 신호) 묶음 → 페어 = ceil(n × (1 + 스페어)) → 표준 규격(6·12·24·36·48) 올림", "spec"),
            ("S2", "L = 패키지 중심 → 룸 경로 (R-CB-MULTI S2~S3)", "length"), ("S3", "Σ L by spec", "CI-CB-PK-*")],
         "사양", "케이블 번호 (MC-패키지-시스템신호)", "len_round m 올림", ["중간 마샬링 묶음 안 함 (사용자 결정 2026-11-27)"]),
        "R-CB-MCC": ("IRP → 룸 멀티", f("mcc_from", "mcc_mode", "mcc_sq", "len_mcc"), [
            ("S1", "MCC 행 묶음 (멀티페어 집합 / 모터당 멀티코어)", "spec"), ("S2", "L = IRP → 룸 경로", "length"), ("S3", "Σ L", "CI-CB-MC-*")],
         "사양", "케이블 번호 (CC-)", "len_round m 올림", ["MCC↔IRP = 전기 범위 (CI-X-MCCIRP)"]),
        "R-CB-COMM": ("통신 케이블", f("comm_pkg", "comm_redund", "FO_spec", "COMM_spec", "ETH_spec"), [
            ("S1", "통신 포트 1개 = 1가닥 (C04 이중화) 또는 패키지당 1가닥, 매체 = C03", "spec"),
            ("S2", "L = 패키지 → 룸 경로", "length"), ("S3", "Σ L by spec", "CI-CB-CM-*")], "사양", "케이블 번호 (FO-/CB-)", "len_round m 올림", []),
        "R-JB": ("JB 수 · 크기", f("group_by", "seg_system", "seg_ad", "seg_do", "rtd_mode", "is_rule", "jb_sizes", "jb_spare", "term_spare", "jb_radius", "jb_place"), [
            ("S1", "묶음 = (경로 종류, 유닛, 시스템, 신호, IS) - STEP 6 분리 기준", "groups"),
            ("S2", "묶음 안에서 반경 jb_radius 안 계기끼리 공간 클러스터 (용량 = 최대 JB 크기 / (1 + 스페어))", "clusters"),
            ("S3", "크기 = 가장 작은 T: ceil(n × (1 + jb_spare)) ≤ 페어, ceil(n × (1 + term_spare)) ≤ 단자", "size"),
            ("S4", "위치 = 자리(랙 기둥 옆 · 장비 옆 · 3D 랙) 중 분기 길이 최소, 3D 장비 상자 안 제외", "slot"), ("S5", "count by size", "CI-JB-*")],
         "크기", "JB 번호", "정수", ["사람이 옮긴 JB는 그 자리 유지 (결정 보호)"]),
        "R-TR": ("사다리 트레이", f("tray_widths", "tray_height", "tray_fill", "sep_comm", "sep_is", "tray_fit"), [
            ("S1", "간선 경로를 격자 변으로 나눠 같은 케이블 묶음 · 같은 종류(랙/AG/UG)가 이어지는 직선 = 구간", "segments"),
            ("S2", "구간 × 트레이 구분(신호/IS/통신): A = Σ π/4 · OD² (OD = 사양별 외경표)", "area"),
            ("S3", "W = 가장 작은 폭: A ≤ W × H × Fill, 가장 넓은 폭으로도 넘치면 단 n = ceil(A / (Wmax × H × Fill))", "width"),
            ("S4", "length(cls, W) = Σ 구간 길이 × 단 수; 물량 = × (1 + tray_fit) → margin", "CI-TR-*")],
         "구분 × 폭", "구간 id (끝점 격자 좌표)", "m 정수", ["사람이 바꾼 폭·단 / 트렌치↔트레이 종류는 그 값 (tray_size, tray_kind)"]),
        "R-UG": ("UG 트렌치", f("ug_widths", "ug_height", "ug_fill", "ug_fit", "ug_depth"), [
            ("S1", "랙 밖 간선 구간(trunk_off = UG) 단면적 합 → 폭 = A ≤ W × H × Fill 인 가장 작은 폭, 넘치면 브래킷 단", "width"),
            ("S2", "length(W) = Σ 구간 길이; 물량 × (1 + ug_fit) → margin", "CI-UG-*")], "폭 × 단", "구간 id", "m 정수", []),
        "R-PT": ("Perforated 트레이", f("pt_width", "route_factor"), [
            ("S1", "분기 케이블 1가닥 = Perforated 1개, 길이 = 분기 케이블 길이", "pt"), ("S2", "Σ 길이", "CI-PT-*")], "폭", "PT 번호", "m 정수", []),
        "R-SP": ("트레이 서포트 · 강재", f("sp_rules", "sp_span", "sp_bay", "sp_tier_gap", "sp_arm_add", "sp_member", "sp_rack_fit"), [
            ("S1", "고정점: 구간 끝, 피팅 끝 600 mm 안 (NEMA VE 2), 익스펜션 조인트 → 사이를 간격 규칙표 span 이하로 채움", "points"),
            ("S2", "형식: 랙 위 1단 = 클램프, 적층 = T(RT), 빔 멀면 보조 빔(RF), AG = L/T/문형(H) 규칙표(폭·단), UG = 브래킷", "type"),
            ("S3", "강재 kg = Σ 부재 길이 × 단위중량; 물량 × 할증 → margin", "CI-SP-*")], "형식", "서포트 번호", "정수 / kg 0.1",
         ["랙 빔 위치 = 구간 시작부터 베이 간격 가정 (S11)"]),
        "R-SP-EXP": ("익스펜션 조인트", f("sp_exp", "sp_dt", "sp_gap", "sp_alpha"), [
            ("S1", "조인트 간격 Lmax = 이동량 / (α × ΔT) (강 11.7e-6, ΔT 70°C → 31 m)", "spacing"),
            ("S2", "직선 사다리 길이 > Lmax 이면 조인트 ceil(L / Lmax) − 1개, 플레이트 = 조인트 × 2", "CI-SP-EXP")], "구간", "조인트 번호", "정수",
         ["NEMA VE 2 판본 확인 전 (열린 질문 7)"]),
    }


# ------------------------------------------------------------------ structured model data (DELTA records)
def records(inst: dict, scope_of) -> list:
    out = []

    def rec(oid, ent, sids, rule, geom, attrs):
        out.append({"object_id": oid, "entity_id": ent, "operation": "ADD", "scope_ids": sids, "rule_id": rule,
                    "geometry": geom, "attributes": attrs})
    for x in inst["instruments"]:
        rec(f"CI-INST:{x['id']}", "E-INSTRUMENT", ["CI-INST"], "R-INST", {"point": x["p"], "estimated": x["est"]}, x["props"])
    for j in inst["jbs"]:
        rec(f"CI-JB:{j['id']}", "E-JB", [scope_of("jb", j)], "R-JB", {"point": j["p"], "box_m": [0.8, 0.8, 0.35]}, j["props"])
    for c in inst["cables"]:
        rec(f"CI-CB:{c['id']}", "E-CABLE", [scope_of("cable", c)], KIND_RULE.get(c["kind"], "R-CB-MULTI"),
            {"polyline": c["path"], "od_mm": c["od"]}, c["props"])
    for t in inst["trays"]:
        rec(f"CI-TR:{t['id']}", "E-ROUTE_SEGMENT", [s for s in [scope_of("tray", t)] if s], "R-UG" if t["kind"] == "ug_trench" else "R-TR",
            {"a": t["a"], "b": t["b"], "width_m": t["w"], "height_m": t.get("h"), "tiers": t.get("tiers"), "tier_pitch_m": t.get("pitch"),
             "cable_section": [{"cable": c[0], "tier": c[1], "x_m": c[2], "y_m": c[3], "od_mm": c[4]} for c in t.get("lay") or []]},
            {**t["props"], "kind": t["kind"]})
    for p in inst.get("perforated") or []:
        rec(f"CI-PT:{p['id']}", "E-PERFORATED", [scope_of("pt", p)], "R-PT", {"polyline": p["path"], "width_m": p["w"]}, p["props"])
    for s in inst["supports"]:
        rec(f"CI-SP:{s['id']}", "E-SUPPORT", [scope_of("support", s)], "R-SP", {"point": s["p"], "base_el": s.get("base")}, {**s["props"], "type": s["type"]})
    for j in inst.get("joints") or []:
        rec(f"CI-EJ:{j['id']}", "E-JOINT", ["CI-SP-EXP"], "R-SP-EXP", {"point": j["p"]}, j["props"])
    for r in inst.get("rooms") or []:
        rec(f"CI-ROOM:{r['id']}", "E-ROOM", [], None, {"point": r["p"]}, r["props"])
    return out


# ------------------------------------------------------------------ validation plan (05) - expected values locked first
DEFAULT_CASES = [
    {"case_id": "T-NORMAL", "test_type": "NORMAL", "title": "현재 체크리스트 · 설정 + PLOT", "overrides": {}, "independent": False},
    {"case_id": "T-CHANGED-JB60", "test_type": "CHANGED", "title": "JB 크기 60P", "overrides": {"jb_sizes": "60"}, "independent": False},
    {"case_id": "T-CHANGED-AG", "test_type": "CHANGED", "title": "랙 밖 간선 AG 서포트", "overrides": {"trunk_off": "AG 서포트"}, "independent": False},
    {"case_id": "T-CHANGED-SPARE30", "test_type": "CHANGED", "title": "JB 스페어 30%", "overrides": {"jb_spare": 0.3}, "independent": False},
    {"case_id": "T-MISSING-PLOT", "test_type": "MISSING", "title": "PLOT 좌표 없음 (필수 입력 제거)", "overrides": {"plot_use": "가정 길이만"},
     "independent": False, "removed": ["PLOT PLAN 좌표"]},
    {"case_id": "T-HOLDOUT-1", "test_type": "HOLDOUT", "title": "독립 실적 대조 (이전 사업 실적 · 수기 계산서)", "overrides": {}, "independent": True},
]


def load_plan(pdir: Path) -> dict:
    f = Path(pdir) / "validation_plan.json"
    try:
        p = json.loads(f.read_text(encoding="utf-8"))
    except Exception:                                      # noqa: BLE001
        p = {}
    have = {c["case_id"] for c in p.get("cases") or []}
    p["cases"] = (p.get("cases") or []) + [dict(c, expected=[], locked_at=None, locked_by=None) for c in DEFAULT_CASES
                                           if c["case_id"] not in have]
    return p


def save_plan(pdir: Path, plan: dict):
    (Path(pdir) / "validation_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")


def plan_update(pdir: Path, b: dict) -> dict:
    """set expected rows of an unlocked case / lock it (who + time) / add a HOLDOUT case / new revision of a locked case."""
    plan = load_plan(pdir)
    case = next((c for c in plan["cases"] if c["case_id"] == b.get("case_id")), None)
    if b.get("add"):
        cid = re.sub(r"[^A-Za-z0-9_-]+", "-", b["add"].get("case_id") or f"T-HOLDOUT-{len(plan['cases'])}")
        if any(c["case_id"] == cid for c in plan["cases"]):
            raise ValueError(f"같은 사례 ID가 있습니다: {cid}")
        plan["cases"].append({"case_id": cid, "test_type": b["add"].get("test_type", "HOLDOUT"), "title": b["add"].get("title", ""),
                              "overrides": b["add"].get("overrides") or {}, "independent": b["add"].get("test_type", "HOLDOUT") == "HOLDOUT",
                              "expected": [], "locked_at": None, "locked_by": None})
    elif not case:
        raise ValueError("사례를 찾지 못했습니다")
    elif b.get("expected") is not None:
        if case.get("locked_at"):
            raise ValueError("잠근 사례는 바꿀 수 없습니다. '새 리비전으로 다시 작성'을 쓰세요 (잠금 기록 보존)")
        rows = []
        for e in b["expected"]:
            cmp_ = e.get("comparator") or "PCT"
            if cmp_ not in ("ABS", "PCT", "EXACT", "STATUS"):
                raise ValueError(f"comparator: {cmp_}")
            ev = e.get("expected_value")
            if cmp_ == "PCT" and ev in (0, "0", 0.0):
                raise ValueError(f"{e['scope_id']}: 기준값 0은 PCT로 비교할 수 없습니다 (ABS 또는 EXACT)")
            if ev in (None, "") and cmp_ != "STATUS":
                continue
            rows.append({"scope_id": e["scope_id"], "comparator": cmp_,
                         "tolerance": None if e.get("tolerance") in (None, "") else float(e["tolerance"]),
                         "expected_value": None if ev in (None, "") else float(ev),
                         "expected_status": e.get("expected_status") or ("HOLD" if case["test_type"] == "MISSING" else "VALUE"),
                         "expected_source_id": e.get("expected_source_id") or "", "expected_locator": e.get("expected_locator") or ""})
        case["expected"] = rows
    elif b.get("lock"):
        if not (b.get("by") or "").strip():
            raise ValueError("잠그는 사람(확인자) 이름을 적어 주세요")
        if not case["expected"]:
            raise ValueError("기대값이 하나도 없습니다")
        case["locked_at"], case["locked_by"] = now_iso(), b["by"].strip()
    elif b.get("revise"):
        old = dict(case)
        k = 2
        while any(c["case_id"] == f"{old['case_id']}-R{k}" for c in plan["cases"]):
            k += 1
        plan["cases"].append({**old, "case_id": f"{old['case_id']}-R{k}", "locked_at": None, "locked_by": None,
                              "expected": [dict(e) for e in old["expected"]], "supersedes": old["case_id"]})
        case["superseded"] = True
    save_plan(pdir, plan)
    return plan


def compare(cmp_: str, tol, exp, act) -> bool:
    if exp is None or act is None:
        return False
    if cmp_ == "EXACT":
        return float(act) == float(exp)
    if cmp_ == "ABS":
        return abs(float(act) - float(exp)) <= float(tol or 0)
    if cmp_ == "PCT":
        return float(exp) != 0 and 100 * abs(float(act) - float(exp)) / abs(float(exp)) <= float(tol or 0)
    return False


# ------------------------------------------------------------------ the package
def write_package(setdir: Path, ctx: dict) -> dict:
    """ctx: project, version, pdir, base, base_path, model_file, inst, tf, s, rows, res, tr, sp, sources (key -> file),
    audit (list rows), run_case (fn case -> (qty dict, status dict, info)), corrections (list of dict), concept_items,
    evidence_files (list of Path), stage."""
    v = ctx["s"]["values"]
    items = scope_items(ctx["rows"], ctx["res"], ctx["tr"], ctx["sp"], v)
    direct = [x for x in items if x["disposition"] == "DIRECT"]
    rdefs = rule_defs(v)
    from . import cable as C
    all_items = {it["id"]: it for g in C.SCHEMA + C.JB.SCHEMA + C.TR.SCHEMA + C.SP.SCHEMA for it in g["items"]}
    fid = lambda iid: "F-" + str(all_items[iid].get("code") or iid) if iid in all_items else "F-" + iid
    # --- revisions: scope / rule change when their content changes, model every time the data changes
    rv_f = Path(ctx["pdir"]) / "handoff_revs.json"
    try:
        revs = json.loads(rv_f.read_text(encoding="utf-8"))
    except Exception:                                      # noqa: BLE001
        revs = {}
    def bump(kind, content):
        h = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]
        r = revs.setdefault(kind, {"n": 0, "hash": None})
        if r["hash"] != h:
            r["n"], r["hash"] = r["n"] + 1, h
        return f"{r['n']:02d}"
    scope_rev = bump("scope", [[x["scope_id"], x["item_name"], x["spec"], x["unit"], x["disposition"], x["rule_id"]] for x in items])
    rule_rev = bump("rule", [rdefs, {k: v.get(k) for k in sorted(v)}])
    recs_probe = len(ctx["inst"]["cables"]), len(ctx["inst"]["trays"]), len(ctx["inst"]["supports"]), len(ctx["inst"]["jbs"])
    model_rev = bump("model", [scope_rev, rule_rev, recs_probe, sha(ctx["model_file"])])
    rv_f.write_text(json.dumps(revs, indent=1), encoding="utf-8")
    pkg = Path(setdir) / f"{PROFILE}_scopeRev{scope_rev}_ruleRev{rule_rev}"
    shutil.rmtree(pkg, ignore_errors=True)
    (pkg / "model").mkdir(parents=True)
    (pkg / "evidence").mkdir()
    written = {}

    def wjson(rel, obj):
        p = pkg / rel
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        written[rel] = p

    def wcsv(rel, header, rows):
        p = pkg / rel
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        written[rel] = p

    meta = {"schema_version": SCHEMA, "profile_id": PROFILE, "task_id": TASK, "discipline_id": DISC, "instruction_rev": INSTRUCTION_REV,
            "scope_rev": scope_rev, "rule_rev": rule_rev, "model_rev": model_rev}
    # --- sources (authority per the guide's enum; nothing is marked APPROVED_* without an approval record)
    pdir, base = Path(ctx["pdir"]), ctx["base"]
    inp = lambda f: pdir / "input" / f if f else None
    src = []

    def add_src(sid, fname, revision, authority, path=None, note=""):
        src.append({"source_id": sid, "filename": fname, "revision": revision, "authority": authority,
                    "checksum": ("sha256:" + sha(path)) if path is not None and Path(path).exists() else None, "note": note})
    S_ = ctx["sources"]
    add_src("SRC-PID", S_.get("pdf"), "Rev.A (파일명·타이틀 블록)", "VERIFIED_SOURCE", inp(S_.get("pdf")),
            "원도. 프로그램 판독값은 후보 - 엔지니어 검토 판단은 evidence/correction_log.csv")
    if S_.get("plot"):
        add_src("SRC-PLOT", S_["plot"], "파일명 기준", "VERIFIED_SOURCE", inp(S_["plot"]), "배치 원도. 축척·제어실·랙은 사람 확인 질문 카드")
    if S_.get("plotref"):
        add_src("SRC-PLOTREF", S_["plotref"], "파일명 기준", "REFERENCE", inp(S_["plotref"]), "축척 참고용")
    if S_.get("template"):
        add_src("SRC-TEMPLATE", S_["template"], "회사 양식", "APPROVED_STANDARD", inp(S_["template"]), "Instrument Index 양식")
    if S_.get("ref"):
        add_src("SRC-REF", S_["ref"], "이전 리비전", "REFERENCE", inp(S_["ref"]), "채점용 레퍼런스 인덱스 (보정·검증 전용)")
    add_src("SRC-CHECKLIST", "concept.xlsx + cable.json", "프로젝트 현재값", "REFERENCE", pdir / "cable.json",
            "설계 가정 (체크리스트 · STEP 6~9 설정). 공종 승인 전이라 REFERENCE - 승인되면 APPROVED_ENGINEERING")
    add_src("SRC-BASE", base["file"], "3d-rev0", "SEED_PROTOTYPE", ctx["base_path"],
            "기준 Seed. 가이드의 03_3D_Digital_Twin_Final.html과 SHA-256 " + ("일치" if base["sha256"] == GUIDE_SEED_SHA else "불일치 - 확인 필요"))
    add_src("SRC-CATALOGUE", "케이블 외경표 (STEP 8 T10~T15E)", "외장형 제조사 공개 카탈로그 값", "REFERENCE", None, "회사 데이터시트 받기 전")
    add_src("SRC-NEMA", "NEMA VE 2", "판본 확인 전", "REFERENCE", None, "피팅·익스펜션 서포트 규칙 근거")
    add_src("SRC-PIDIO", "pid_io " + ctx["version"], "프로그램", "REFERENCE", None, "산출 엔진 (개발자는 독립 구현)")
    # independent expected-value sources named in the validation plan (engineer's hand calc, previous project actuals ...)
    for c_ in load_plan(pdir)["cases"]:
        for e in c_.get("expected") or []:
            sid = e.get("expected_source_id")
            if sid and sid not in {x["source_id"] for x in src}:
                add_src(sid, e.get("expected_locator") or sid, "사용자 입력", "VERIFIED_ACTUAL" if c_["test_type"] == "HOLDOUT" else "REFERENCE",
                        None, "독립 검증 기대값 근거 (validation_plan.json, " + c_["case_id"] + ")")
    # --- 01 scope
    wcsv("01_scope.csv", ["scope_id", "scope_kind", "item_name", "item_type", "spec", "unit", "work_master_code", "source_discipline", "owner",
                          "disposition", "rule_id", "include_boundary", "exclude_boundary", "source_id", "locator", "approval_by", "approval_date"],
         [[x["scope_id"], "QUANTITY", x["item_name"], x["item_type"], x["spec"], x["unit"], "", "CI", x.get("owner", "CI"), x["disposition"],
           x["rule_id"] if x["disposition"] == "DIRECT" else "", x["include"], x["exclude"], x["source_id"], x["locator"], "", ""] for x in items])
    # --- 02 input / model contract
    fields = [
        {"field_id": "F-PID-TAG", "entity_id": "E-INSTRUMENT", "path": "instrument.tag", "data_type": "string", "unit": None, "required": True,
         "input_mode": "REFERENCE", "source_id": "SRC-PID", "locator": "P&ID 심볼 태그 (판독 후보 → 검토 판단)", "missing_action": "HOLD",
         "default_value": None, "approved_by": None, "default_application": None},
        {"field_id": "F-PID-FUNC", "entity_id": "E-INSTRUMENT", "path": "instrument.func", "data_type": "string", "unit": None, "required": True,
         "input_mode": "REFERENCE", "source_id": "SRC-PID", "locator": "태그 기능문자", "missing_action": "HOLD", "default_value": None,
         "approved_by": None, "default_application": None},
        {"field_id": "F-IO-TYPE", "entity_id": "E-IO", "path": "io.io_type", "data_type": "string", "unit": None, "required": True,
         "input_mode": "DERIVED", "source_id": "SRC-PIDIO", "locator": "protocols/io_rules.yaml + 체크리스트 Typical", "missing_action": "HOLD",
         "default_value": None, "approved_by": None, "default_application": None},
        {"field_id": "F-INST-XYZ", "entity_id": "E-INSTRUMENT", "path": "instrument.point", "data_type": "array", "unit": "m", "required": False,
         "input_mode": "DERIVED", "source_id": "SRC-PLOT", "locator": "장비 태그 위치 / 시트 장비 중심 ('추정' 표시)", "missing_action": "HOLD",
         "default_value": None, "approved_by": None, "default_application": None},
        {"field_id": "F-PLOT-SCALE", "entity_id": "E-QUANTITY", "path": "plot.m_per_pt", "data_type": "number", "unit": "m/pt", "required": True,
         "input_mode": "PROJECT", "source_id": "SRC-PLOT", "locator": "축척 질문 카드", "missing_action": "HOLD", "default_value": None,
         "approved_by": None, "default_application": None},
        {"field_id": "F-ROOM-XY", "entity_id": "E-ROOM", "path": "room.point", "data_type": "array", "unit": "pt", "required": True,
         "input_mode": "PROJECT", "source_id": "SRC-PLOT", "locator": "제어실 질문 카드", "missing_action": "HOLD", "default_value": None,
         "approved_by": None, "default_application": None},
        {"field_id": "F-RACK", "entity_id": "E-ROUTE_SEGMENT", "path": "racks[]", "data_type": "array", "unit": "m", "required": False,
         "input_mode": "REFERENCE", "source_id": "SRC-BASE" if str(v.get("rack_src", "")).startswith("3D") else "SRC-PLOT",
         "locator": "랙 출처 = " + str(v.get("rack_src")), "missing_action": "HOLD", "default_value": None, "approved_by": None,
         "default_application": None},
        {"field_id": "F-REF-INDEX", "entity_id": "E-QUANTITY", "path": "reference_index", "data_type": "object", "unit": None, "required": False,
         "input_mode": "CALIBRATION_ONLY", "source_id": "SRC-REF", "locator": "STEP 2 레퍼런스 채점", "missing_action": "HOLD",
         "default_value": None, "approved_by": None, "default_application": None},
    ]
    for iid, it in all_items.items():
        changed = v.get(iid) != it["default"]
        fields.append({"field_id": fid(iid), "entity_id": "E-QUANTITY", "path": f"settings.{iid}", "data_type": "number" if it["type"] == "number" else "string",
                       "unit": it.get("unit") or None, "required": True, "input_mode": "PROJECT" if changed else "APPROVED_DEFAULT",
                       "source_id": "SRC-CHECKLIST", "locator": f"{it['name']} = {v.get(iid)}", "missing_action": "HOLD",
                       "default_value": None if changed else it["default"], "approved_by": None,
                       "default_application": None if changed else "pid_io 기본값 / 회사 프리셋 (승인 전)"})
    for iid, it in (ctx.get("concept_items") or {}).items():
        fields.append({"field_id": f"F-CK-{iid}", "entity_id": "E-IO", "path": f"concept.{iid}", "data_type": "string", "unit": None,
                       "required": True, "input_mode": "PROJECT", "source_id": "SRC-CHECKLIST", "locator": f"{it.get('name', '')} = {it.get('value')}",
                       "missing_action": "HOLD", "default_value": None, "approved_by": None, "default_application": None})
    tf = ctx["tf"]
    wjson("02_input_model_contract.json", {**meta,
        "coordinate_system": {"id": "CS-SEED", "axes": "X east, Y up (EL), Z south (right-handed, Three.js)",
                              "origin": "기준 Seed 원점 (Rack A × E-W 랙 교점)", "length_unit": "m", "source_id": "SRC-BASE",
                              "locator": "Seed ASSUMPTIONS 'Origin = …'",
                              "plot_transform": {"formula": tf["formula"], "s": tf["s"], "tx": tf["tx"], "tz": tf["tz"], "anchors": tf["anchors"],
                                                 "residual_median_m": tf["median_m"], "residual_max_m": tf["max_m"]}},
        "entities": [
            {"entity_id": "E-INSTRUMENT", "id_key": "instrument_tag", "representation": "GEOMETRY", "source_id": "SRC-PID", "locator": "P&ID 태그"},
            {"entity_id": "E-IO", "id_key": "io_id = instrument_tag + io_type + 순번", "representation": "TABLE", "source_id": "SRC-PIDIO", "locator": "Instrument Index 행"},
            {"entity_id": "E-JB", "id_key": "jb_id", "representation": "GEOMETRY", "source_id": "SRC-PIDIO", "locator": "JB_List"},
            {"entity_id": "E-CABLE", "id_key": "circuit (cable_no)", "representation": "GEOMETRY", "source_id": "SRC-PIDIO", "locator": "Cable_Schedule"},
            {"entity_id": "E-ROUTE_SEGMENT", "id_key": "route_segment_id (TR- / UG-)", "representation": "GEOMETRY", "source_id": "SRC-PIDIO", "locator": "Tray_Segments"},
            {"entity_id": "E-PERFORATED", "id_key": "PT 번호", "representation": "GEOMETRY", "source_id": "SRC-PIDIO", "locator": "Perforated_Tray"},
            {"entity_id": "E-SUPPORT", "id_key": "support_id", "representation": "GEOMETRY", "source_id": "SRC-PIDIO", "locator": "Support_List"},
            {"entity_id": "E-JOINT", "id_key": "EJ 번호", "representation": "GEOMETRY", "source_id": "SRC-PIDIO", "locator": "Expansion_Joints"},
            {"entity_id": "E-ROOM", "id_key": "room id", "representation": "GEOMETRY", "source_id": "SRC-PLOT", "locator": "제어실 / IRP"},
            {"entity_id": "E-QUANTITY", "id_key": "scope_id", "representation": "CALCULATION", "source_id": "SRC-PIDIO", "locator": "01_scope.csv"},
            {"entity_id": "E-VIEWER", "id_key": "seed code location", "representation": "ATTRIBUTE", "source_id": "SRC-BASE", "locator": "Seed module script"}],
        "fields": fields,
        "interfaces": [
            {"interface_id": "IF-PI-RACK", "provider": "PI", "consumer": "CI", "field_ids": ["F-RACK"], "join_key": "rack id (Seed RK.*)",
             "boundary": "랙 위치·폭·케이블 단 EL 읽기 전용. 랙 구조는 철골(SS)", "approved_by": None, "approval_date": None, "status": "PROPOSED"},
            {"interface_id": "IF-PI-EQUIP", "provider": "PI", "consumer": "CI", "field_ids": ["F-INST-XYZ"], "join_key": "equipment tag",
             "boundary": "장비 위치·상자 (계기 위치 추정, JB 자리 제외) 읽기 전용", "approved_by": None, "approval_date": None, "status": "PROPOSED"},
            {"interface_id": "IF-EL-MCC", "provider": "EL", "consumer": "CI", "field_ids": [fid("mcc_from")], "join_key": "motor tag",
             "boundary": "MCC↔IRP 배선 = 전기, IRP→룸 = 계장 (CI-X-MCCIRP)", "approved_by": None, "approval_date": None, "status": "PROPOSED"},
            {"interface_id": "IF-EL-ROUTE", "provider": "EL", "consumer": "CI", "field_ids": ["F-RACK"], "join_key": "route_segment_id",
             "boundary": "공용 통로: 계장 트레이와 전력 트레이 분리, 귀속은 각 공종. 전기 3D 데이터 수신 후 합의", "approved_by": None,
             "approval_date": None, "status": "PROPOSED"},
            {"interface_id": "IF-VENDOR-PKG", "provider": "VENDOR", "consumer": "CI", "field_ids": [fid("pkg_if")], "join_key": "package unit tag",
             "boundary": "패키지 UCP 단자까지 벤더, UCP → 룸 = 계장", "approved_by": None, "approval_date": None, "status": "PROPOSED"}],
        "interface_assessment": "계기·케이블 중복 제거 키 = instrument_tag / io_id / circuit. 배관 Seed 객체는 읽기만 하고 수정·삭제 없음 "
                                "(뷰어 코드 1줄 수정은 06 changes에 기록). 전기와 공용 통로 귀속은 미합의 (PROPOSED)."})
    # --- 03 rules
    rules = []
    for rid, (title, inputs, steps, grouping, dedup, rounding, exc) in rdefs.items():
        sids = [x["scope_id"] for x in direct if x["rule_id"] == rid]
        if not sids:
            continue
        rules.append({"rule_id": rid, "title": title, "rule_kind": "QUANTITY", "scope_ids": sids,
                      "input_field_ids": [f"F-CK-{i}" if re.match(r"^[A-H]\d\d$", i) else fid(i) for i in inputs
                                          if i in all_items or (re.match(r"^[A-H]\d\d$", i) and i in (ctx.get("concept_items") or {}))]
                                         + (["F-PID-TAG", "F-PID-FUNC", "F-IO-TYPE"] if rid in ("R-INST", "R-IO") else ["F-PLOT-SCALE", "F-ROOM-XY", "F-RACK"]),
                      "preconditions": "추출 완료, 체크리스트·STEP 6~9 설정 적용" + (", PLOT 축척·제어실 확인" if rid not in ("R-INST", "R-IO") else ""),
                      "steps": [{"step_id": a, "operation": b, "result_key": c} for a, b, c in steps],
                      "outputs": [{"scope_id": x["scope_id"], "result_key": x["scope_id"], "unit": x["unit"]} for x in direct if x["rule_id"] == rid],
                      "grouping": grouping, "deduplication": dedup, "rounding": rounding,
                      "exceptions": exc or ["N/A: 예외 없음"], "missing_policy": "HOLD",
                      "evidence": [{"source_id": "SRC-CHECKLIST", "locator": "산출근거 엑셀 (STEP 5) 해당 시트 - 식에 숫자 대입"}]
                                  + ([{"source_id": "SRC-NEMA", "locator": "fitting / expansion"}] if rid.startswith("R-SP") else []),
                      "status": "DRAFT", "approved_by": None, "approval_date": None})
    wjson("03_engineering_rules.json", {**meta, "rules": rules,
                                        "note": "status = DRAFT: 공종 책임자 승인 전. 근거가 REFERENCE · SEED_PROTOTYPE 뿐이라 승인 전에는 G3 HOLD."})
    # --- 04 test inputs (no expected values) + execution
    plan = load_plan(pdir)
    cases = [c for c in plan["cases"] if not c.get("superseded")]
    wjson("04_test_inputs.json", {**meta, "cases": [
        {"case_id": c["case_id"], "test_type": c["test_type"], "rule_ids": sorted({x["rule_id"] for x in direct}),
         "scope_ids": [x["scope_id"] for x in direct], "input": {"base": "현재 프로젝트 입력 (sources)", "overrides": c.get("overrides") or {},
                                                                    "removed_required_inputs": c.get("removed") or []},
         "independent": bool(c.get("independent")), "title": c.get("title", "")} for c in cases]})
    unit_of = {x["scope_id"]: x["unit"] for x in direct}
    rule_of = {x["scope_id"]: x["rule_id"] for x in direct}
    margin_of = {x["scope_id"]: x["margin"] for x in direct}
    vrows = []
    for c in cases:
        executed_at = now_iso()
        qty, status, info = ctx["run_case"](c)
        ref = f"evidence/run_{c['case_id']}.json"
        wjson(ref, {**meta, "case_id": c["case_id"], "executed_at": executed_at, "overrides": c.get("overrides") or {},
                    "results": {k: {"value": qty.get(k), "status": status.get(k, "VALUE"), "unit": unit_of.get(k)} for k in unit_of}, "info": info})
        exp = {e["scope_id"]: e for e in c.get("expected") or []}
        locked = c.get("locked_at")
        for sid in unit_of:
            e = exp.get(sid)
            act, act_st = qty.get(sid), status.get(sid, "VALUE")
            if sid not in qty:                              # this run has no such item: 0 when it was computed, HOLD when it could not be
                act, act_st = (None, "HOLD") if (info.get("plot_gone") and rule_of[sid].startswith(PLOT_RULES)) else (0, "VALUE")
            if not (e and locked):
                verdict = "HOLD"
            elif e["comparator"] == "STATUS" or c["test_type"] == "MISSING":
                verdict = "PASS" if act_st == e["expected_status"] else "FAIL"
            else:
                verdict = "PASS" if act_st == "VALUE" and compare(e["comparator"], e["tolerance"], e["expected_value"], act) else "FAIL"
            if locked and locked >= executed_at:
                verdict = "HOLD"                            # the guide: expected values must be locked before the run
            vrows.append([c["case_id"], sid, rule_of[sid], unit_of[sid], (e or {}).get("comparator", ""),
                          "" if not e or e.get("tolerance") is None else e["tolerance"],
                          "" if not e or e.get("expected_value") is None else e["expected_value"],
                          "" if act is None or act_st != "VALUE" else act, (e or {}).get("expected_status", ""), act_st,
                          (e or {}).get("expected_source_id", ""), (e or {}).get("expected_locator", ""), locked or "", executed_at, ref,
                          verdict, "", "" if act is None or act_st != "VALUE" else act, "",
                          "" if margin_of.get(sid) is None or c["test_type"] == "MISSING" else margin_of[sid]])
    wcsv("05_validation.csv", ["case_id", "scope_id", "rule_id", "unit", "comparator", "tolerance", "expected_value", "actual_value",
                               "expected_status", "actual_status", "expected_source_id", "expected_locator", "expected_locked_at",
                               "executed_at", "execution_ref", "verdict", "verified_by", "raw_value", "correction_rule_id", "margin_value"], vrows)
    # --- model files (copies; the app keeps its own) + DELTA data
    mname = f"{PROFILE}_Seed03_R{model_rev}"
    shutil.copy2(ctx["model_file"], pkg / "model" / f"{mname}.html")
    sc_map = {}
    for x in direct:
        sc_map.setdefault((x["item_type"], x["spec"]), x["scope_id"])
    tray_scope = {}
    for t in ctx["tr"]["segments"]:
        if t["kind"] == "UG":
            tray_scope[t["no"]] = f"CI-UG-W{t['width']}" + (f"X{t['tiers']}" if t["tiers"] > 1 else "")
        for tt in t["trays"]:
            tray_scope[tt["no"]] = f"CI-TR-{CLS_CODE.get(tt['cls'], slug(tt['cls']))}-{tt['width']}"
    cable_scope = {c["no"]: f"CI-CB-{KIND_CODE.get(c['kind'], 'XX')}-{slug(c['spec'])}" for c in ctx["res"]["cables"]}

    def scope_of(kind, o):
        if kind == "jb":
            return f"CI-JB-{slug(o['props'].get('크기', ''))}"
        if kind == "cable":
            return cable_scope.get(o["id"])
        if kind == "tray":
            return tray_scope.get(o["id"])
        if kind == "pt":
            return f"CI-PT-{v['pt_width']}"
        if kind == "support":
            return f"CI-SP-{o['type']}"
    recs = records(ctx["inst"], scope_of)
    rec_hash = lambda rs: hashlib.sha256(json.dumps(rs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    h_recs = rec_hash(recs)
    seed_mod = ctx.get("seed_modifications") or []
    for m in seed_mod:
        recs.append({"object_id": m["object_id"], "entity_id": "E-VIEWER", "operation": "MODIFY", "scope_ids": [], "rule_id": None,
                     "geometry": None, "attributes": {"before": m["before"], "after": m["after"], "why": m["why"]}})
    smd = {**meta, "baseline_sha256": base["sha256"], "data_mode": "DELTA", "model_units": "m (외경 mm, 폭 m)",
           "coordinate_reference": {"coordinate_system_id": "CS-SEED", "plot_transform": tf["formula"]},
           "composition_notes": "기준 Seed HTML의 <script type=\"module\"> 끝에 계장 레이어 블록(INST = 이 records의 geometry·attributes)을 붙이고, "
                                "클릭 필터 1줄을 MODIFY 기록대로 바꾸면 model/" + mname + ".html과 같아짐 (pid_io twin.build_html). 배관 객체는 변경 없음.",
           "records": recs}
    wjson(f"model/{mname}.json", smd)
    # --- automatic model checks (status stays HOLD until a person reviews: the guide forbids self-approval)
    mf = pkg / "model" / f"{mname}.html"
    base_txt = Path(ctx["base_path"]).read_text(encoding="utf-8")
    sup_txt = mf.read_text(encoding="utf-8")
    i0 = sup_txt.find("/* ===================================================================================\n   pid_io 계장 레이어")
    j0 = sup_txt.find("</script>", i0)
    restored = (sup_txt[:i0 - 1] + sup_txt[j0:]) if i0 > 0 else ""   # the appended block starts with its own newline
    for m in seed_mod:
        restored = restored.replace(m["after"], m["before"], 1)
    chk_base = restored == base_txt
    ids = [r["object_id"] for r in recs]
    empty = [r["object_id"] for r in recs if r["operation"] == "ADD" and (not r["geometry"] or not r["attributes"])]
    nos = [r["object_id"] for r in recs if r["operation"] == "ADD" and r["entity_id"] != "E-ROOM" and not r["scope_ids"]]
    recon = []
    by = Counter()
    for r in recs:
        if r["operation"] != "ADD" or not r["scope_ids"]:
            continue
        sid = r["scope_ids"][0]
        a = r["attributes"]
        if sid.startswith("CI-CB-"):
            by[sid] += float(a.get("길이 (m)") or 0)
        elif sid.startswith(("CI-TR-", "CI-UG-")):
            by[sid] += float(a.get("길이 (m)") or 0) * (int(r["geometry"].get("tiers") or 1) if sid.startswith("CI-TR-") else 1)
        elif sid.startswith("CI-PT-"):
            by[sid] += float(a.get("길이 (m)") or 0)
        elif sid.startswith(("CI-JB-", "CI-SP-")) and sid not in ("CI-SP-KG", "CI-SP-EXP"):
            by[sid] += 1
    qn = quantities(ctx["rows"], ctx["res"], ctx["tr"], ctx["sp"], v)
    for sid, q in qn.items():
        if sid in by:
            recon.append({"scope_id": sid, "model": round(by[sid], 1), "quantity": q, "match": abs(by[sid] - float(q or 0)) <= max(1.0, 0.005 * float(q or 0))})
    determin = bool(ctx.get("reproduce")) and rec_hash(records(ctx["reproduce"](), scope_of)) == h_recs
    checks_auto = {
        "BASELINE_INTEGRITY": (chk_base and base["sha256"] == GUIDE_SEED_SHA,
                               f"기준 Seed SHA-256 {base['sha256'][:12]}… (가이드 {GUIDE_SEED_SHA[:12]}…: {'일치' if base['sha256'] == GUIDE_SEED_SHA else '불일치'}); "
                               f"보강본에서 계장 블록 제거 + MODIFY {len(seed_mod)}건 되돌리면 원본과 {'바이트 일치' if chk_base else '불일치'}"),
        "GEOMETRY_ATTRIBUTES": (len(ids) == len(set(ids)) and not empty and not nos,
                                f"records {len(recs)}, object_id 중복 {len(ids) - len(set(ids))}, geometry/attributes 빈 것 {len(empty)}, scope 없는 객체 {len(nos)}"),
        "QUANTITY_RECONCILIATION": (bool(recon) and all(x["match"] for x in recon),
                                    f"모델 records 합 vs 01 물량 {sum(1 for x in recon if x['match'])}/{len(recon)} 일치 (evidence/model_checks.json)"),
        "REPRODUCIBILITY": (bool(determin), "같은 입력·Rule로 다시 계산한 records 해시가 " + ("같음" if determin else "다르거나 재계산 안 함")),
    }
    wjson("evidence/model_checks.json", {**meta, "checked_at": now_iso(), "reconciliation": recon,
                                         "auto": {k: {"result": "PASS" if a else "FAIL", "evidence": b} for k, (a, b) in checks_auto.items()},
                                         "note": "자동 점검 결과. 사람이 원본/보강 모델을 열어 확인하고 reviewed_by를 채우기 전까지 06 checks는 HOLD"})
    # --- evidence copies
    for p in ctx.get("evidence_files") or []:
        if p and Path(p).exists():
            shutil.copy2(p, pkg / "evidence" / Path(p).name)
    wcsv("evidence/pid_io_audit.csv", ["case_id", "check", "expected", "actual", "result", "by", "detail"], ctx.get("audit") or [])
    corr = ctx.get("corrections") or []
    wcsv("evidence/correction_log.csv", ["correction_id", "kind", "object_id", "drawing", "page", "drawing_value", "read_value", "engineer_value",
                                         "origin", "reason", "confirmed_by", "decided_at", "effect"],
         [[c.get(k, "") for k in ("correction_id", "kind", "object_id", "drawing", "page", "drawing_value", "read_value", "engineer_value",
                                  "origin", "reason", "confirmed_by", "decided_at", "effect")] for c in corr])
    # --- 06 model handoff
    model_scope = [x["scope_id"] for x in direct]
    arts = [{"path": f"model/{mname}.html", "kind": "SUPPLEMENTED_MODEL"}, {"path": f"model/{mname}.json", "kind": "STRUCTURED_MODEL_DATA"}]
    for a in arts:
        p = pkg / a["path"]
        a.update(sha256=sha(p), size_bytes=p.stat().st_size)
    changes = [{"change_id": f"CH-{i + 1:05d}", "scope_ids": r["scope_ids"], "operation": r["operation"], "object_id": r["object_id"],
                "rule_id": r["rule_id"], "source_id": "SRC-BASE" if r["operation"] == "MODIFY" else "SRC-PIDIO",
                "locator": "Seed module script" if r["operation"] == "MODIFY" else f"model/{mname}.json records[{i}]"} for i, r in enumerate(recs)]
    wjson("06_model_handoff.json", {**meta,
        "baseline": {"source_id": "SRC-BASE", "filename": base["file"], "revision": "3d-rev0", "sha256": base["sha256"]},
        "disposition": "SUPPLEMENTED", "model_scope_ids": model_scope,
        "rationale": "계장 개략 물량의 객체(계기·JB·케이블·트레이/트렌치·Perforated·서포트·조인트)를 기준 Seed 좌표계에 추가 (ADD). "
                     "배관·장비·랙 객체는 읽기만. 뷰어 클릭 필터 1줄 MODIFY (수직 단면에서 잘린 쪽 클릭 제외).",
        "approval": {"by": None, "date": None, "rev": model_rev, "status": "PENDING"},
        "artifacts": arts, "changes": changes,
        "checks": [{"check_id": k, "status": "HOLD", "evidence": f"자동: {'PASS' if a else 'FAIL'} - {b} (evidence/model_checks.json)",
                    "reviewed_by": None} for k, (a, b) in checks_auto.items()]})
    # --- 00 manifest
    issues = [
        {"issue_id": "IS-001", "status": "OPEN", "scope_ids": [x["scope_id"] for x in direct], "reason": "범위·Rule·모델 공종 승인 없음",
         "action": "공종 책임자 확인 후 scope_approval / engineering_approval 기록", "owner": "CI 책임자"},
        {"issue_id": "IS-002", "status": "OPEN", "scope_ids": ["CI-X-FG"], "reason": "F&G 검지기가 P&ID에 없음", "action": "F&G 배치도 받기", "owner": "CI"},
        {"issue_id": "IS-003", "status": "OPEN", "scope_ids": [x["scope_id"] for x in direct if x["unit"] == "m"],
         "reason": f"계기 위치 다수 추정, 좌표 맞춤 잔차 중앙값 {tf['median_m']} m / 최대 {tf['max_m']} m", "action": "태그 위치 자료 · 3D 좌표 확인", "owner": "CI"},
        {"issue_id": "IS-004", "status": "OPEN", "scope_ids": [], "reason": "전기 공용 통로 인터페이스 미합의 (IF-EL-ROUTE)", "action": "전기 3D 데이터 수신 후 합의", "owner": "CI / EL"},
    ]
    if not any(c.get("locked_at") for c in cases):
        issues.append({"issue_id": "IS-005", "status": "OPEN", "scope_ids": [x["scope_id"] for x in direct],
                       "reason": "독립 검증 기대값 잠금 없음 (05 전부 HOLD)", "action": "STEP 10 '독립 검증 기대값 잠금'", "owner": "CI 책임자"})
    n_pass = sum(1 for r in vrows if r[15] == "PASS")
    gate = lambda g, ev: {"gate_id": g, "status": "HOLD", "evidence": ev, "reviewed_by": None}
    wjson("00_manifest.json", {**meta, "status": "DRAFT_NOT_READY",
        "scope_approval": {"by": None, "date": None, "rev": scope_rev},
        "engineering_approval": {"by": None, "date": None, "rev": rule_rev, "status": "PENDING"},
        "sources": src,
        "expected_scope_ids": [x["scope_id"] for x in items],
        "model_required_scope_ids": model_scope,
        "required_standard_codes": [], "linked_standard_codes": [],
        "gate_results": [
            gate("G1", f"01_scope.csv {len(items)}개 (DIRECT {len(direct)}, OTHER_PACKAGE 2, HOLD 1) - 범위 승인 전"),
            gate("G2", "02 fields·entities·좌표계, evidence/correction_log.csv (원도 보정 " + str(len(corr)) + "건) - 확인자 미기록"),
            gate("G3", f"03 rules {len(rules)}개 (DRAFT, 근거 REFERENCE) - 승인 전"),
            gate("G4", "02 interfaces 5개 PROPOSED - 합의 전"),
            gate("G5", f"05 {len(vrows)}행 중 PASS {n_pass} (잠근 사례 {sum(1 for c in cases if c.get('locked_at'))}/{len(cases)}), 06 checks 자동 결과 evidence/model_checks.json"),
            gate("G6", "표준 7종 + model/ 2개 + evidence/ - 승인·확인자 없음")],
        "issues": issues,
        "correction_policy": "보정 계수 없음. 원도 판독 보정은 사람 결정(evidence/correction_log.csv)으로만 입력을 바꾸고 다시 계산",
        "margin_policy": "피팅·할증은 margin_value로 분리 (트레이 T06, 트렌치 T21, 강재 할증). 케이블 여유율은 R-CB 식 안 (len_margin)",
        "generator": {"tool": "pid_io", "version": ctx["version"], "project": ctx["project"], "made_at": now_iso(),
                      "pid_io_check": ctx.get("check_summary", "")}})
    # --- checkpoint (for RESUME in the company Copilot)
    stage = ctx.get("stage") or ("S05" if any(c.get("locked_at") for c in cases) else "S04")
    cp_name = f"checkpoint_{PROFILE}_{stage}_R{time.strftime('%Y%m%d-%H%M%S')}.json"
    draft = [{"filename": n, "revision": f"scope{scope_rev}/rule{rule_rev}/model{model_rev}", "approval_state": "DRAFT_NOT_READY",
              "reattach": "지금 첨부" if n in ("00_manifest.json", "01_scope.csv") else "필요할 때 첨부",
              "reason": {"00_manifest.json": "상태·Gate·미결", "01_scope.csv": "범위 승인 (S02)", "02_input_model_contract.json": "입력·Rule 승인 (S03)",
                         "03_engineering_rules.json": "입력·Rule 승인 (S03)", "04_test_inputs.json": "독립 실행 (S05)",
                         "05_validation.csv": "독립 검증 대조 (S05)", "06_model_handoff.json": "모델 검토 (S04/S06)"}.get(n, ""),
              "note": ""} for n in ("00_manifest.json", "01_scope.csv", "02_input_model_contract.json", "03_engineering_rules.json",
                                    "04_test_inputs.json", "05_validation.csv", "06_model_handoff.json")]
    draft += [{"filename": a["path"], "revision": f"model{model_rev}", "approval_state": "DRAFT_NOT_READY", "reattach": "필요할 때 첨부",
               "reason": "모델 검토 (S04~S06)", "note": f"sha256 {a['sha256'][:16]}…"} for a in arts]
    wjson(cp_name, {"profile_id": PROFILE, "stage": stage,
                    "versions": {"instruction_rev": INSTRUCTION_REV, "scope_rev": scope_rev, "rule_rev": rule_rev, "model_rev": model_rev},
                    "source_registry": src, "confirmed_decisions": ctx.get("decisions") or [],
                    "pending_issues": issues, "draft_files": draft,
                    "next_step": ("S05 독립 검증: 잠근 기대값과 05 대조 확인 → S06 Gate" if stage == "S05"
                                  else "S02 범위 승인 · S03 Rule 승인, STEP 10에서 독립 검증 기대값 잠금 → 다시 만들기"),
                    "updated_at": now_iso()})
    return {"dir": pkg.name, "scope_rev": scope_rev, "rule_rev": rule_rev, "model_rev": model_rev, "files": sorted(written),
            "validation": {"rows": len(vrows), "pass": n_pass, "fail": sum(1 for r in vrows if r[15] == "FAIL"),
                           "hold": sum(1 for r in vrows if r[15] == "HOLD")},
            "checks": {k: "PASS" if a else "FAIL" for k, (a, b) in checks_auto.items()}, "corrections": len(corr)}


# ------------------------------------------------------------------ 원도 보정 이력 (evidence/correction_log.csv) - v13.5
def corrections(syms, ov: dict, ai_sug: list, dec: dict, plot_dec: dict, dlog: list, io_before: dict, io_after: dict) -> list:
    """drawing value / program reading / engineer value / origin / reason per correction, plus the IO effect overall.
    confirmed_by stays empty unless the record names a person (the tool has no login)."""
    out = []
    by_sid = {s.sid: s for s in syms}
    acc = {x.get("sid"): x for x in ai_sug or [] if x.get("status") == "accepted"}
    n = 0

    def add(**k):
        nonlocal n
        n += 1
        out.append({"correction_id": f"CR-{n:04d}", **k})
    for sid, o in sorted(((ov or {}).get("symbols") or {}).items()):
        s = by_sid.get(sid)
        read = f"{s.cls} {s.func}-{s.number} (점수 {round(s.score, 2)})" if s else "(원 심볼 없음)"
        eng = "태그 아님" if o.get("class") == "NOT_A_TAG" else f"{o.get('class')} {o.get('tag') or ''} IO {o.get('io') or '규칙대로'} {o.get('system') or ''}".strip()
        a = acc.get(sid)
        add(kind="P&ID 심볼 판정", object_id=f"SYM:{sid}", drawing=getattr(s, "dwg", ""), page=getattr(s, "page", ""),
            drawing_value=f"{s.func}-{s.number}" if s else "", read_value=read, engineer_value=eng,
            origin="AI 제안 → 사람 승인" if a else "사람 검토 (STEP 4)", reason=o.get("reason") or (a or {}).get("reason", ""),
            confirmed_by="", decided_at="", effect="")
    for x in (ov or {}).get("added") or []:
        add(kind="P&ID 누락 심볼 추가", object_id=f"ADD:{x.get('page')}:{x.get('tag')}", drawing="", page=x.get("page"),
            drawing_value=x.get("tag", ""), read_value="(판독 못 함)", engineer_value=f"{x.get('class')} {x.get('tag')} IO {x.get('io')}",
            origin="AI 누락 후보 → 사람 승인", reason=x.get("reason", ""), confirmed_by="", decided_at="", effect="")
    for r in (ov or {}).get("rules") or []:
        add(kind="기능코드 IO 규칙", object_id=f"RULE:{r.get('func')}", drawing="", page="", drawing_value=r.get("func", ""),
            read_value="규칙표에 없음", engineer_value=f"{r.get('desc')} IO {'/'.join(r.get('io') or []) or '-'} {r.get('system', '')}",
            origin="AI 제안 → 사람 승인", reason=r.get("reason", ""), confirmed_by="", decided_at="", effect="")
    for x in ai_sug or []:
        if x.get("status") == "rejected":
            add(kind="AI 제안 거절", object_id=f"AI:{x.get('sid')}", drawing="", page="", drawing_value=x.get("func") or x.get("tag") or "",
                read_value=f"AI: {x.get('desc', '')} IO {'/'.join(x.get('io') or []) or '-'} (신뢰도 {x.get('confidence')})",
                engineer_value="채택 안 함", origin="사람 거절", reason=x.get("reason", ""), confirmed_by="", decided_at="", effect="변화 없음")
    for k, v_ in ((dec or {}).get("only_one") or {}).items():
        add(kind="노트 해석 (ONLY ONE SHOWN)", object_id=f"NOTE:{k}", drawing=k, page="", drawing_value="노트", read_value="노트 인식",
            engineer_value=f"대수 {v_}", origin="사람 검토", reason="", confirmed_by="", decided_at="", effect="대수 복제")
    for k, v_ in ((dec or {}).get("rows") or {}).items():
        add(kind="인덱스 행 판단", object_id=f"ROW:{k}", drawing="", page="", drawing_value="", read_value="", engineer_value=str(v_),
            origin="사람 검토", reason="", confirmed_by="", decided_at="", effect="")
    pd = plot_dec or {}
    for j, slot in (pd.get("jb_moves") or {}).items():
        add(kind="JB 위치 (PLOT)", object_id=f"JB:{j}", drawing="PLOT", page="", drawing_value="", read_value="자동 자리",
            engineer_value=f"자리 {slot}", origin="사람 이동 (STEP 7)", reason="", confirmed_by="", decided_at="", effect="분기·멀티 길이")
    for rid in (pd.get("routes_edit") or {}):
        add(kind="경로 (PLOT)", object_id=f"ROUTE:{rid}", drawing="PLOT", page="", drawing_value="", read_value="자동 경로",
            engineer_value="끌어서 고친 경로", origin="사람 수정 (STEP 6)", reason="", confirmed_by="", decided_at="", effect="케이블 길이·트레이")
    for seg, o in (pd.get("tray_size") or {}).items():
        add(kind="트레이 크기", object_id=f"SEG:{seg}", drawing="PLOT", page="", drawing_value="", read_value="자동 폭",
            engineer_value=json.dumps(o, ensure_ascii=False), origin="사람 수정 (STEP 8)", reason="", confirmed_by="", decided_at="", effect="트레이 물량")
    for seg, k in (pd.get("tray_kind") or {}).items():
        add(kind="트렌치 ↔ 트레이", object_id=f"SEG:{seg}", drawing="PLOT", page="", drawing_value="", read_value="자동 판정",
            engineer_value=k, origin="사람 수정 (STEP 8)", reason="", confirmed_by="", decided_at="", effect="트레이·트렌치·서포트")
    for k in ("m_per_pt", "room", "irp"):
        if pd.get(k):
            add(kind="PLOT 질문 카드", object_id=f"PLOT:{k}", drawing="PLOT", page="", drawing_value="", read_value="자동 인식",
                engineer_value=json.dumps(pd[k], ensure_ascii=False), origin="사람 입력", reason="", confirmed_by="", decided_at="", effect="길이")
    for d in dlog or []:
        add(kind="3D 반영 관문", object_id=f"GATE:{d.get('what')}", drawing="3D", page="", drawing_value=str(d.get("before")),
            read_value=f"{d.get('source')} 제안", engineer_value=str(d.get("after")), origin=str(d.get("approved", "")),
            reason="", confirmed_by="", decided_at=str(d.get("at", "")), effect="")
    eff = ", ".join(f"{k} {io_before.get(k, 0)}→{io_after.get(k, 0)}" for k in IO_TYPES if io_before.get(k, 0) != io_after.get(k, 0)) or "IO 변화 없음"
    add(kind="합계 (보정 전 → 후)", object_id="TOTAL", drawing="", page="", drawing_value="", read_value="판독값만 (검토 판단 없이)",
        engineer_value="검토 판단 적용", origin="pid_io 재계산", reason="", confirmed_by="", decided_at="", effect=eff)
    return out
