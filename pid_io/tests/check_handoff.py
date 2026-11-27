"""Structure check of a company handoff package (AI3D-HANDOFF-1.1, 가이드 Rev.6 T1 계장) - form only, not engineering.

    python tests/check_handoff.py <package folder T1-CI_scopeRevNN_ruleRevNN>

Prints FAIL lines; exit 1 if any. PASS here does not mean READY_FOR_DEVELOPER (approvals / independent checks are people's).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

H01 = "scope_id,scope_kind,item_name,item_type,spec,unit,work_master_code,source_discipline,owner,disposition,rule_id,include_boundary,exclude_boundary,source_id,locator,approval_by,approval_date".split(",")
H05 = "case_id,scope_id,rule_id,unit,comparator,tolerance,expected_value,actual_value,expected_status,actual_status,expected_source_id,expected_locator,expected_locked_at,executed_at,execution_ref,verdict,verified_by,raw_value,correction_rule_id,margin_value".split(",")
AUTH = {"APPROVED_STANDARD", "APPROVED_PROJECT", "APPROVED_ENGINEERING", "VERIFIED_SOURCE", "VERIFIED_ACTUAL", "SEED_PROTOTYPE", "REFERENCE"}
F = []


def fail(m):
    F.append(m)
    print("FAIL", m)


def main(pkg: Path):
    j = lambda n: json.loads((pkg / n).read_text(encoding="utf-8"))
    for n in ("00_manifest.json", "01_scope.csv", "02_input_model_contract.json", "03_engineering_rules.json", "04_test_inputs.json",
              "05_validation.csv", "06_model_handoff.json"):
        if not (pkg / n).exists():
            fail(f"{n} 없음")
    m, c2, r3, t4, h6 = (j(n) for n in ("00_manifest.json", "02_input_model_contract.json", "03_engineering_rules.json",
                                        "04_test_inputs.json", "06_model_handoff.json"))
    meta_keys = ("schema_version", "profile_id", "scope_rev", "rule_rev", "model_rev")
    for name, d in (("02", c2), ("03", r3), ("04", t4), ("06", h6)):
        for k in meta_keys:
            if d.get(k) != m.get(k):
                fail(f"{name} {k} = {d.get(k)} != 00 {m.get(k)}")
    for k in ("schema_version", "profile_id", "task_id", "discipline_id", "instruction_rev", "scope_rev", "rule_rev", "model_rev", "status",
              "scope_approval", "engineering_approval", "sources", "expected_scope_ids", "model_required_scope_ids",
              "required_standard_codes", "linked_standard_codes", "gate_results", "issues"):
        if k not in m:
            fail(f"00 {k} 없음")
    if m.get("schema_version") != "AI3D-HANDOFF-1.1" or m.get("task_id") != "T1":
        fail("00 schema / task")
    if m.get("status") not in ("DRAFT_NOT_READY", "READY_FOR_DEVELOPER"):
        fail("00 status")
    if m.get("required_standard_codes") != [] or m.get("linked_standard_codes") != []:
        fail("00 standard codes는 [] 고정")
    sids = [s["source_id"] for s in m["sources"]]
    if len(sids) != len(set(sids)):
        fail("source_id 중복")
    for s in m["sources"]:
        if s["authority"] not in AUTH:
            fail(f"authority {s['authority']}")
    if sorted(g["gate_id"] for g in m["gate_results"]) != [f"G{i}" for i in range(1, 7)]:
        fail("gate_results G1~G6")
    if m["status"] == "READY_FOR_DEVELOPER" and (any(g["status"] != "PASS" for g in m["gate_results"])
                                                   or any(i["status"] == "OPEN" for i in m["issues"])):
        fail("READY인데 Gate PASS 아님 / OPEN 이슈")
    # 01
    rows = list(csv.reader(open(pkg / "01_scope.csv", encoding="utf-8")))
    if rows[0] != H01:
        fail("01 헤더")
    sc = {r[0]: dict(zip(H01, r)) for r in rows[1:]}
    if len(sc) != len(rows) - 1:
        fail("01 scope_id 중복")
    if sorted(sc) != sorted(m["expected_scope_ids"]):
        fail("01 ≠ expected_scope_ids")
    direct = {k for k, v in sc.items() if v["disposition"] == "DIRECT"}
    for k, v in sc.items():
        if v["disposition"] not in ("DIRECT", "LOT_INCLUDED", "OTHER_PACKAGE", "OUT_OF_SCOPE", "HOLD"):
            fail(f"01 {k} disposition")
        if v["disposition"] == "DIRECT" and not all(v[x] for x in ("owner", "unit", "rule_id", "include_boundary", "exclude_boundary")):
            fail(f"01 {k} DIRECT 필수 칸")
        if v["disposition"] != "DIRECT" and v["rule_id"]:
            fail(f"01 {k} 비직접인데 rule_id")
        if v["source_id"] and v["source_id"] not in sids:
            fail(f"01 {k} source_id {v['source_id']}")
    # 02
    fids = {f["field_id"] for f in c2["fields"]}
    if len(fids) != len(c2["fields"]):
        fail("02 field_id 중복")
    ents = {e["entity_id"] for e in c2["entities"]}
    for f in c2["fields"]:
        if f["entity_id"] not in ents:
            fail(f"02 {f['field_id']} entity {f['entity_id']}")
        if f["input_mode"] not in ("PROJECT", "DERIVED", "APPROVED_DEFAULT", "REFERENCE", "CALIBRATION_ONLY"):
            fail(f"02 {f['field_id']} input_mode")
        if f["required"] and f["missing_action"] != "HOLD":
            fail(f"02 {f['field_id']} missing_action")
        if f["input_mode"] != "APPROVED_DEFAULT" and f["default_value"] is not None:
            fail(f"02 {f['field_id']} default_value는 APPROVED_DEFAULT만")
    for i in c2["interfaces"]:
        for x in i["field_ids"]:
            if x not in fids:
                fail(f"02 interface {i['interface_id']} field {x}")
    # 03
    covered = {}
    for r in r3["rules"]:
        for x in r["input_field_ids"]:
            if x not in fids:
                fail(f"03 {r['rule_id']} input {x} 02에 없음")
                break
        if sorted(r["scope_ids"]) != sorted(o["scope_id"] for o in r["outputs"]):
            fail(f"03 {r['rule_id']} outputs ≠ scope_ids")
        for o in r["outputs"]:
            if o["scope_id"] not in sc or sc[o["scope_id"]]["unit"] != o["unit"]:
                fail(f"03 {r['rule_id']} output {o['scope_id']} 단위/범위")
        for s_ in r["scope_ids"]:
            covered[s_] = covered.get(s_, 0) + 1
        if r["missing_policy"] != "HOLD" or not r["steps"] or not r["evidence"]:
            fail(f"03 {r['rule_id']} missing_policy/steps/evidence")
        if any("AI가 계산" in s["operation"] for s in r["steps"]):
            fail(f"03 {r['rule_id']} 'AI가 계산'")
    for s_ in direct:
        if covered.get(s_) != 1:
            fail(f"03 DIRECT {s_} Rule {covered.get(s_, 0)}개 (1개여야)")
    # 04 / 05
    cases = {cs["case_id"]: cs for cs in t4["cases"]}
    for cs in t4["cases"]:
        if any(k in json.dumps(cs, ensure_ascii=False) for k in ("expected_value", "tolerance")):
            fail(f"04 {cs['case_id']} 기대값이 실행 입력에 있음")
        if cs["test_type"] == "HOLDOUT" and not cs.get("independent"):
            fail(f"04 {cs['case_id']} HOLDOUT independent")
    v5 = list(csv.reader(open(pkg / "05_validation.csv", encoding="utf-8")))
    if v5[0] != H05:
        fail("05 헤더")
    seen = set()
    for r in v5[1:]:
        d = dict(zip(H05, r))
        key = (d["case_id"], d["scope_id"])
        if key in seen:
            fail(f"05 중복 {key}")
        seen.add(key)
        if d["case_id"] not in cases or d["scope_id"] not in sc:
            fail(f"05 {key} 사례/범위")
        if d["unit"] != sc.get(d["scope_id"], {}).get("unit"):
            fail(f"05 {key} 단위")
        if d["comparator"] == "PCT" and d["expected_value"] in ("0", "0.0"):
            fail(f"05 {key} PCT 기준 0")
        if d["expected_locked_at"] and d["expected_locked_at"] >= d["executed_at"] and d["verdict"] != "HOLD":
            fail(f"05 {key} 잠금이 실행보다 늦음")
        if cases.get(d["case_id"], {}).get("test_type") == "MISSING" and d["verdict"] == "PASS" and d["expected_status"] != "HOLD":
            fail(f"05 {key} MISSING은 HOLD 기대")
        if d["execution_ref"] and not (pkg / d["execution_ref"]).exists():
            fail(f"05 {key} execution_ref 파일 없음")
        if d["verdict"] not in ("PASS", "FAIL", "HOLD"):
            fail(f"05 {key} verdict")
    # 06 + model
    if sorted(h6["model_scope_ids"]) != sorted(m["model_required_scope_ids"]):
        fail("06 model_scope_ids ≠ 00 model_required_scope_ids")
    if h6["disposition"] == "SUPPLEMENTED":
        kinds = {a["kind"] for a in h6["artifacts"]}
        if not {"SUPPLEMENTED_MODEL", "STRUCTURED_MODEL_DATA"} <= kinds:
            fail("06 artifacts 2종")
        for a in h6["artifacts"]:
            p = pkg / a["path"]
            if not p.exists():
                fail(f"06 {a['path']} 없음")
                continue
            if hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"] or p.stat().st_size != a["size_bytes"]:
                fail(f"06 {a['path']} 해시/크기")
        if sorted(c["check_id"] for c in h6["checks"]) != sorted(["BASELINE_INTEGRITY", "GEOMETRY_ATTRIBUTES", "QUANTITY_RECONCILIATION", "REPRODUCIBILITY"]):
            fail("06 checks 4종")
        smd = json.loads((pkg / next(a["path"] for a in h6["artifacts"] if a["kind"] == "STRUCTURED_MODEL_DATA")).read_text(encoding="utf-8"))
        for k in meta_keys:
            if smd.get(k) != m.get(k):
                fail(f"SMD {k}")
        if smd["baseline_sha256"] != h6["baseline"]["sha256"]:
            fail("SMD baseline_sha256")
        oids = [r["object_id"] for r in smd["records"]]
        if len(oids) != len(set(oids)):
            fail("SMD object_id 중복")
        ch = {(c["object_id"], c["operation"]) for c in h6["changes"]}
        if smd["data_mode"] == "DELTA" and ch != {(r["object_id"], r["operation"]) for r in smd["records"]}:
            fail("SMD DELTA records ≠ 06 changes")
        for r in smd["records"]:
            if r["entity_id"] not in ents:
                fail(f"SMD {r['object_id']} entity")
                break
            if any(s_ not in sc for s_ in r["scope_ids"]):
                fail(f"SMD {r['object_id']} scope")
                break
    print(f"\n결과: FAIL {len(F)}  (형식 검사만 - 승인·독립 검증은 사람)")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
