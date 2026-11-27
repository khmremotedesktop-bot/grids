"""공통 프로토콜 세 관점 일치 점검.  python tests/check_protocol.py   (exit 1 when a problem is found)

- 규칙마다 엔지니어 · 컴퓨터 · 유지보수 관점이 다 있는지
- 기준값(params)을 세 관점이 모두 {이름}으로 쓰는지 (숫자를 따로 적으면 어긋날 수 있음)
- params 밖에 숫자 기준이 문장에 적혀 있지 않은지
- 프로그램이 쓰는 값이 프로토콜 params와 같은지 (P11)
뜻이 같은지는 사람 확인 (needs_review 표시된 규칙).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pid_io import common_rules as CR, orders as OR  # noqa: E402

home = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "projects"
c = OR.load_common(home)
bad = CR.check(c["rules"])
for i, p in bad:
    print("FAIL" if "사람 확인" not in p else "참고", i, p)
print(f"공통 프로토콜 v{c['version']} · 규칙 {len(c['rules'])}개 · 문제 {sum(1 for _, p in bad if '사람 확인' not in p)}")
sys.exit(1 if any("사람 확인" not in p for _, p in bad) else 0)
