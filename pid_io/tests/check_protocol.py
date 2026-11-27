"""공통 프로토콜 점검 (v3: 엔지니어 관점 = 마스터, 컴퓨터 · 유지보수 = 번역본).   python tests/check_protocol.py

FAIL: 마스터 필수 칸(대상 · 할 일 · 판정) 빔, 기준값(params)을 어느 관점이 안 씀, 문장 안 숫자 기준, 번역본 '다시 번역 필요'(마스터가 바뀜) · '질문 있음'.
참고: 번역 확인 필요(사람), 마스터 승인 전.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pid_io import common_rules as CR, orders as OR  # noqa: E402

home = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "projects"
c = OR.load_common(home)
bad = CR.check(c["rules"])
for i, p, lv in bad:
    if lv == "FAIL":
        print("FAIL", i, p)
ref = sum(1 for b in bad if b[2] == "참고")
print(f"공통 프로토콜 v{c['version']} · 규칙 {len(c['rules'])}개 · FAIL {sum(1 for b in bad if b[2] == 'FAIL')} · 참고 {ref} (번역 확인 · 승인 대기)")
sys.exit(1 if any(b[2] == "FAIL" for b in bad) else 0)
