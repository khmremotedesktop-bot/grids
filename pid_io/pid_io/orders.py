"""주문 → 다음 파일 (v13.2) + 공통 프로토콜 학습.

A person types an order in STEP 10 ("EW 랙 트레이 반대쪽 차선으로", "JB-18-DA-01 11-P-101A/B 밖으로").
  1. rule parser first (no AI): setting names / option words, JB moves, lane flips, "다시 만들기"
  2. only when the rules do not understand it, Copilot turns it into actions from the fixed ACTIONS list
  3. the program applies the actions (an order is a person's decision: it is recorded as one, with an undo copy),
     regenerates the supplemented 3D model as the next set, runs the 3D precheck, and shows the numbers that moved
  4. each order leaves a LESSON candidate. Lessons free of tag numbers / project names can become COMMON protocol
     rules (any concept design); they are promoted only after a person approves (repeats are counted as evidence).
The common protocol is a JSON + Markdown pair in <PID_IO_HOME>/_protocol/, copied into every 3D handoff set.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ACTIONS = {
    "set": "설정 하나 바꾸기 {key, value} - key는 설정 ID, value는 선택지 글자 그대로 또는 숫자",
    "jb_move": "JB 옮기기 {jb, near} - near = 장비 태그 또는 자리 ID (그 장비에서 가장 가까운, 막히지 않은 자리)",
    "jb_reset": "JB 이동 취소 {jb}",
    "tray_size": "구간 트레이 크기 {seg, cls, w, n} (cls = 신호/통신/IS, w = 폭 mm, n = 단)",
    "sup_over": "구간 서포트 {seg, type?, span?} (type L/T/H, span m)",
    "remake": "아무것도 안 바꾸고 다시 만들기·리뷰",
}

from . import common_rules as CR  # noqa: E402  (v13.7: one rule, three views)

COMMON_SEED = {
    "name": "pid_io 계장 개념설계 공통 프로토콜",
    "scope": "어떤 개념설계에든 쓰는 공통 부분만 (태그 번호·프로젝트 이름·프로젝트 값 없음)",
    "version": "3.0",
    "views": CR.VIEWS,
    "notice": CR.NOTICE,
    "rules": CR.RULES,
    "changelog": [{"version": "1.0", "at": "2026-11-27", "what": "처음 (v13.2 규칙을 공통으로)"},
                  {"version": "2.0", "at": "2026-11-27", "what": "세 관점(엔지니어 · 컴퓨터 · 유지보수)으로 다시 씀, 기준값 params 한 곳, P11 추가"},
                  {"version": "3.0", "at": "2026-11-27", "what": "엔지니어 관점 = 마스터 (설계실 Rule 양식 칸), 컴퓨터·유지보수 = 번역본 (지문·상태), P00 읽는 법 추가"}],
}

TAGLIKE = re.compile(r"\b(\d{2}-[A-Z]{1,5}-?\d+|JB-\S+|TR-\S+|UG-\S+|SP-\S+|MC-\S+|C-\S+)\b")


# ------------------------------------------------------------------ parsing
def _norm(t: str) -> str:
    return re.sub(r"\s+", "", str(t)).lower()


def parse_rule(text: str, items: dict, values: dict, ids: dict) -> list | None:
    """rules first. items = setting id -> item, ids = {"jbs": [...], "equipment": [...]}. None = not understood."""
    t = text.strip()
    tn = _norm(t)
    acts = []
    if re.search(r"(다시\s*만들|재생성|리뷰만|다시\s*점검)", t):
        return [{"type": "remake"}]
    # lane flip
    if "차선" in t and re.search(r"(반대|뒤집|바꿔)", t):
        cur = str(values.get("tw_lane", "+"))
        opts = items.get("tw_lane", {}).get("options") or []
        to = next((o for o in opts if o[:1] != cur[:1] and o[:1] in "+−-"), None)
        if to:
            return [{"type": "set", "key": "tw_lane", "value": to}]
    # JB move: "JB-18-DA-01 (을) 11-P-101A/B 밖/옆/근처/로"
    m = re.search(r"(JB-[\w-]+)", t)
    if m and m.group(1) in ids.get("jbs", []):
        jb = m.group(1)
        if re.search(r"(원래|취소|되돌|자동)", t):
            return [{"type": "jb_reset", "jb": jb}]
        eq = next((e for e in sorted(ids.get("equipment", []), key=len, reverse=True) if e and e in t), None)
        slot = re.search(r"\b((?:R|U|E|3D)[\w]*-\w+)\b", t.replace(jb, ""))
        if eq or slot:
            return [{"type": "jb_move", "jb": jb, "near": eq or slot.group(1)}]
    # setting by name + option word / number
    best = None
    for k, it in items.items():
        nm = _norm(it.get("name", ""))
        if len(nm) < 2 or nm not in tn:
            continue
        val = None
        for o in sorted(it.get("options") or [], key=lambda o: -len(str(o))):
            on = _norm(o)
            core = _norm(re.sub(r"\(.*?\)", "", str(o)))
            if on in tn or (len(core) >= 2 and core in tn.replace(nm, "", 1)):
                val = o
                break
        if val is None and it.get("type") == "number":
            mm = re.search(re.escape(it["name"].replace(" ", "")) + r"\D{0,8}?(-?\d+(?:\.\d+)?)", t.replace(" ", ""))
            if mm:
                val = float(mm.group(1))
        if val is not None and (best is None or len(nm) > best[0]):
            best = (len(nm), {"type": "set", "key": k, "value": val})
    if best:
        acts.append(best[1])
    return acts or None


def ai_prompt(text: str, items: dict, values: dict, ids: dict, common: dict) -> str:
    sets = "\n".join(f"- {k}: {it['name']} = {values.get(k)!r}" + (f" (선택지: {' / '.join(map(str, it['options']))})" if it.get("options") else
                                                                     f" ({it.get('unit', '')} 숫자)") for k, it in items.items())
    acts = "\n".join(f"- {k}: {v}" for k, v in ACTIONS.items())
    rules = "\n".join(f"- {r['id']} {CR.master_text(r) if r.get('master') else r.get('text', '')}" for r in common.get("rules", []))
    return f"""너는 계장 개념설계 프로그램(pid_io)의 주문 해석기다. 사람의 주문을 아래 '동작'으로만 바꿔라. 값을 지어내지 마라.
주문: {text}

동작 (이것만):
{acts}

설정 (ID: 이름 = 현재 값):
{sets}

JB: {', '.join(ids.get('jbs', [])[:80])}
장비: {', '.join(ids.get('equipment', [])[:120])}
트레이 구간 예: {', '.join(ids.get('segs', [])[:40])}

공통 프로토콜 (지켜야 함):
{rules}

또 이 주문에서 배울 점이 있으면 lesson 하나를 써라. 다른 프로젝트에도 통하는 일반 규칙이면 scope "common"(태그 번호·프로젝트 이름 금지), 이 프로젝트만이면 "project".
JSON 하나만 답:
{{"actions": [{{"type": "set", "key": "...", "value": "..."}}], "explain": "<한국어로 무엇을 할지 한 줄>",
  "lesson": {{"text": "<한국어 규칙 한 줄 또는 빈 문자열>", "scope": "common|project"}}, "unclear": "<못 알아들은 부분, 없으면 빈 문자열>"}}
"""


def validate(acts: list, items: dict, ids: dict) -> tuple:
    ok, bad = [], []
    for a in acts or []:
        t = a.get("type")
        if t == "set":
            it = items.get(a.get("key"))
            if not it:
                bad.append(f"없는 설정: {a.get('key')}")
                continue
            v = a.get("value")
            if it.get("type") == "select" and v not in (it.get("options") or []):
                m = [o for o in it["options"] if _norm(v) in _norm(o)]
                if len(m) != 1:
                    bad.append(f"{it['name']}: 선택지에 없는 값 {v}")
                    continue
                v = m[0]
            ok.append({"type": "set", "key": a["key"], "value": v})
        elif t in ("jb_move", "jb_reset"):
            if a.get("jb") not in ids.get("jbs", []):
                bad.append(f"없는 JB: {a.get('jb')}")
                continue
            ok.append({k: a[k] for k in ("type", "jb", "near") if k in a})
        elif t in ("tray_size", "sup_over"):
            if str(a.get("seg")) not in ids.get("segs", []):
                bad.append(f"없는 구간: {a.get('seg')}")
                continue
            ok.append(a)
        elif t == "remake":
            ok.append({"type": "remake"})
        else:
            bad.append(f"모르는 동작: {t}")
    return ok, bad


def describe(a: dict, items: dict) -> str:
    t = a["type"]
    if t == "set":
        return f"{items[a['key']]['name']} → {a['value']}"
    if t == "jb_move":
        return f"{a['jb']} → {a.get('near')} 근처 자리"
    if t == "jb_reset":
        return f"{a['jb']} 이동 취소 (자동 자리)"
    if t == "tray_size":
        return f"{a['seg']} {a.get('cls')} 트레이 {a.get('w')}×{a.get('n')}단"
    if t == "sup_over":
        return f"{a['seg']} 서포트 {a.get('type', '')} {a.get('span', '')}"
    return "다시 만들기"


# ------------------------------------------------------------------ lessons / common protocol
def proto_dir(home: Path) -> Path:
    d = Path(home) / "_protocol"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_common(home: Path) -> dict:
    f = proto_dir(home) / "common_protocol.json"
    if not f.exists():
        save_common(home, json.loads(json.dumps(COMMON_SEED)))
    c = json.loads(f.read_text(encoding="utf-8"))
    if str(c.get("version", "1")).split(".")[0] < "3":          # v1 / v2 file -> master + translations (learned rules kept)
        c = CR.upgrade(c)
        save_common(home, c)
    if CR.sync_seed(c):                                         # v13.9: seed rules changed by a user decision
        save_common(home, c)
    return c


def save_common(home: Path, c: dict):
    d = proto_dir(home)
    # stored: master + translations only (no copied view text that someone could edit by mistake); md generated
    (d / "common_protocol.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "공통프로토콜.md").write_text(CR.markdown(c), encoding="utf-8")


def add_common_rule(home: Path, engineer: str, computer: str, maintenance: str, title: str, src: str, by: str = "") -> dict:
    """a rule approved as 공통 (e.g. from a 3D comment) -> common protocol, three views, version +0.1."""
    if TAGLIKE.search(engineer) or TAGLIKE.search(computer):
        raise ValueError("공통 규칙에는 태그 번호·JB·트레이 번호를 쓸 수 없습니다. 일반 표현으로 고쳐 주세요 (또는 범위를 '프로젝트'로)")
    c = load_common(home)
    n = sum(1 for r in c["rules"] if r.get("src") in ("lesson", "comment")) + 1
    major, minor = c["version"].split(".")
    c["version"] = f"{major}.{int(minor) + 1}"
    r = CR.make_rule({"id": f"L{n:02d}", "title": title[:30], "params": {},
                      "master": {"target": title[:40], "preconditions": "", "steps": [engineer], "exceptions": [],
                                 "verdict": "어기면 HOLD (사람 판단)", "evidence": [f"{src} 승인 {by}".strip()]},
                      "computer": computer, "maintenance": maintenance, "src": src}, by or src)
    r.update(src=src, by=by, at=time.strftime("%Y-%m-%d"))
    c["rules"].append(r)
    c.setdefault("changelog", []).append({"version": c["version"], "at": time.strftime("%Y-%m-%d"), "what": f"{src} 규칙 추가: {engineer[:60]}"})
    save_common(home, c)
    return c


def lesson_key(text: str) -> str:
    return re.sub(r"[\s.,·:()\-]+", "", text)[:60]


def add_lesson(home: Path, project: str, text: str, scope: str, order_id: str, by: str) -> dict | None:
    """lesson candidate (pending). Repeats raise its evidence count; tag-like text is forced to project scope."""
    text = (text or "").strip()
    if not text:
        return None
    if TAGLIKE.search(text) or (project and project in text):
        scope = "project"
    f = proto_dir(home) / "lessons.json"
    cur = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    k = lesson_key(text)
    hit = next((x for x in cur if x["key"] == k and x["status"] == "pending"), None)
    if hit:
        hit["evidence"] += 1
        hit["projects"] = sorted(set(hit["projects"]) | {project})
        hit["orders"].append(order_id)
    else:
        hit = {"id": f"L{len(cur) + 1:03d}", "key": k, "text": text, "scope": scope if scope in ("common", "project") else "project",
               "by": by, "evidence": 1, "projects": [project], "orders": [order_id], "status": "pending", "at": time.strftime("%Y-%m-%d %H:%M")}
        cur.append(hit)
    hit["suggest_promote"] = hit["scope"] == "common" and (hit["evidence"] >= 3 or len(hit["projects"]) >= 2)
    f.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return hit


def lessons(home: Path) -> list:
    f = proto_dir(home) / "lessons.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def decide_lesson(home: Path, lid: str, accept: bool, text: str | None = None, scope: str | None = None) -> dict:
    f = proto_dir(home) / "lessons.json"
    cur = lessons(home)
    x = next((y for y in cur if y["id"] == lid), None)
    if not x:
        raise ValueError("없는 교훈")
    if text:
        x["text"] = text.strip()
    if scope in ("common", "project"):
        x["scope"] = scope
    if accept and x["scope"] == "common" and TAGLIKE.search(x["text"]):
        raise ValueError("공통 규칙에는 태그 번호·JB·트레이 번호를 쓸 수 없습니다. 일반 표현으로 고쳐 주세요")
    x["status"] = ("approved_" + x["scope"]) if accept else "rejected"
    f.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    c = load_common(home)
    if accept and x["scope"] == "common":
        n = sum(1 for r in c["rules"] if r.get("src") == "lesson") + 1
        major, minor = c["version"].split(".")
        c["version"] = f"{major}.{int(minor) + 1}"
        r = CR.make_rule({"id": f"L{n:02d}", "title": x["text"][:30], "params": {},
                          "master": {"target": x["text"][:40], "preconditions": "", "steps": [x["text"]], "exceptions": [],
                                     "verdict": "어기면 HOLD (사람 판단)", "evidence": [f"배운 것: {', '.join(x['projects'])}, 근거 {x['evidence']}회"]},
                          "computer": x["text"], "maintenance": f"배운 규칙 (주문 교훈 {', '.join(x.get('orders') or [])}). 마스터를 고치면 번역 다시",
                          "src": "lesson"}, "교훈 원문 그대로 (번역 확인 필요)")
        r.update(src="lesson", **{"from": ", ".join(x["projects"])}, evidence=x["evidence"], at=time.strftime("%Y-%m-%d"))
        c["rules"].append(r)
        c.setdefault("changelog", []).append({"version": c["version"], "at": time.strftime("%Y-%m-%d"), "what": f"배운 규칙 추가: {x['text'][:60]}"})
        save_common(home, c)
    return {"lesson": x, "common_version": c["version"]}
