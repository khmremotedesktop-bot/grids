# 회사 가이드 Rev.6 vs pid_io 3D 인계 세트 (v13.4) 비교

- 가이드: `AI_3D_Platform_Copilot_Appendix_Rev6.html` (과제별 Engineering Agent 개발 인계 지침 Rev.6, 2026-11-25)
- 비교 대상: 과제 1 · 개념설계 공통 + **T1-CI 계장** (SKILL `ai3d-t1-ci-r9`, R9-G6, 스키마 `AI3D-HANDOFF-1.1`), Quality Gate, 인계 7종, 실증. **과제 2(가설)는 제외** (사용자 지시 2026-11-27).
- 우리 쪽: `projects/서남해 200MW 수전해-2/output/LATEST/3D인계/` (00~06, 보강 HTML, STRUCTURED_MODEL_DATA_FULL.json, 3D_REVIEW_*, COMMON_PROTOCOL)

## 1. 맞는 것 (이미 가이드 방향과 같음)

| 가이드 | 우리 |
|---|---|
| 기준 Seed `03_3D_Digital_Twin_Final.html`, SHA-256 `35d0e456…f9a` | 우리 입력 `02-AI-Assisted.Conceptual.3D.Model_Final.html`의 SHA-256이 **같음** → 파일 이름만 다르고 같은 Seed |
| 원본 Seed 잠금, 보강본은 별개 파일 | 원본 그대로 + 별도 `…_계장보강.html` |
| Three.js 0.164.1 · importmap · 데이터 구조 호환 유지 | 원본 module script 끝에 계장 레이어 블록만 추가, 버전 그대로 |
| 보강 모델 + 구조화 데이터 둘 다 필수 | 보강 HTML + `STRUCTURED_MODEL_DATA_FULL.json` |
| 7종 파일 이름 (00~06) | 같은 이름으로 냄 |
| 빈 양식·미승인은 `DRAFT_NOT_READY` | status = DRAFT_NOT_READY, G1~G6 = HOLD |
| AI는 제안만, 승인 대체 안 함 | 공통 프로토콜 P10, 3D 반영 관문(승인한 것만) |
| 원도/AI 판독/엔지니어 보정 구분 | 검토 판단(decisions), 사람 결정 > 3D > PLOT 자동 > 체크리스트 |
| 타 공종 Seed 영역 삭제·덮어쓰기 금지 | 배관 모델 읽기 전용, 충돌 시 계장이 비킴 |
| 계기 · I/O · JB · 계장케이블 · Tray 개략 물량 | IO / JB / 케이블 / 사다리·트렌치·Perforated / 서포트 (28개 Scope) |
| 최소 입력 + 승인 Rule (전체 I/O List 전제 안 함) | P&ID + PLOT + 체크리스트(설계 가정)로 산출 |
| 예외: 현장 지시계·패키지 통신·직결·공용 트레이 | IO 없는 계기, 패키지 PLC 통신(광), 패키지 UCP 직결, 통신 별도 트레이 규칙 있음 |
| 독립 검증 시나리오: JB 이동, 신호/직결 변경, 누락 | T-CHANGED-JB60 / AG / SPARE30, T-MISSING-PLOT, 점검 스크립트의 JB 이동·경로 수정 |

## 2. 다른 것 · 빠진 것

### A. 형식 (규격 AI3D-HANDOFF-1.1과 필드가 다름) — 프로그램으로 맞출 수 있음

| 파일 | 가이드 규격 | 우리 지금 | 해야 할 일 |
|---|---|---|---|
| 공통 | 폴더 `T1-CI_scopeRev01_ruleRev01/` + `model/` + `evidence/` | 한 폴더에 섞여 있음 | 폴더 구조 맞추기 |
| 00_manifest | schema_version, profile_id, task_id=T1, discipline_id=CI, instruction_rev=R9-G6, scope/rule/model_rev, scope_approval, engineering_approval, sources[{source_id, filename, revision, authority, checksum}], expected_scope_ids, model_required_scope_ids, required/linked_standard_codes=[], gate_results[G1..G6], issues[] | profile, rev{}, sources{id,file}, gate_evidence 문장, open 문장 | 필드 이름·구조 변경, authority 분류(P&ID=VERIFIED_SOURCE, 체크리스트=APPROVED_ENGINEERING 후보, 배관 3D=SEED_PROTOTYPE …) |
| 01_scope.csv | 헤더 17개 고정: scope_id, scope_kind, item_name, item_type, spec, unit, work_master_code, source_discipline, owner, disposition(DIRECT/LOT_INCLUDED/OTHER_PACKAGE/OUT_OF_SCOPE/HOLD), rule_id, include_boundary, exclude_boundary, source_id, locator, approval_by, approval_date | 7개 (scope_id, 담당, 분류, 규격, 단위, 수량, rule_id), **수량이 들어 있음** | 헤더 교체. 수량은 01이 아니라 05/모델로. 포함·제외 경계 문장 추가 (예: MCC↔IRP = OTHER_PACKAGE 전기) |
| 02_input_model_contract | coordinate_system{id, axes, origin, length_unit, source_id, locator}, entities[], fields[]{field_id, path, data_type, unit, required, input_mode(PROJECT/DERIVED/APPROVED_DEFAULT/REFERENCE/CALIBRATION_ONLY), missing_action=HOLD, default_value, approved_by…}, interfaces[]{interface_id, provider, consumer, field_ids, join_key, boundary, status}, interface_assessment | inputs / entities(객체) / coordinates(문장) / interfaces(문장) | 필드 목록으로 펼치기. 체크리스트 항목 = APPROVED_DEFAULT 후보(승인자 칸 비움) |
| 03_engineering_rules | rules[]{rule_id, title, rule_kind=QUANTITY, scope_ids, input_field_ids, preconditions, steps[{step_id, operation(실제 식), result_key}], outputs[{scope_id, result_key, unit}], grouping, deduplication, rounding, exceptions, missing_policy=HOLD, evidence[], status, approved_by, approval_date} | formulas / settings / protocol / exceptions (rules 목록 없음) | 산출근거 엑셀의 식(IO·JB·케이블·트레이·서포트)을 Scope마다 Rule 하나로. "AI가 계산"은 불합격 → 우리는 실제 식이 있으니 옮기기만 하면 됨 |
| 04_test_inputs | cases[]{case_id, test_type, rule_ids, scope_ids, input…}, 기대값 없음, HOLDOUT은 independent=true | id/type/input 문장 6건 | 구조 맞추기. 입력을 실제 값으로 (예: jb_sizes=60) |
| 05_validation.csv | 헤더 20개: case_id, scope_id, rule_id, unit, comparator(ABS/PCT/EXACT/STATUS), tolerance, expected_value, actual_value, expected_status, actual_status, expected_source_id, expected_locator, **expected_locked_at < executed_at**, execution_ref, verdict, verified_by, raw_value, correction_rule_id, margin_value | 7개, 기대값 = 우리 불변 조건(자체 점검) | 헤더 교체. **독립 기대값은 엔지니어가 먼저 잠가야** (아래 B) |
| 06_model_handoff | baseline{source_id, filename, revision, sha256}, disposition=SUPPLEMENTED, model_scope_ids(=00과 동일), rationale, approval{}, artifacts[{path, kind(SUPPLEMENTED_MODEL/STRUCTURED_MODEL_DATA/SUPPORTING_FILE), sha256, size_bytes}], changes[{change_id, scope_ids, operation(ADD/MODIFY/REMOVE), object_id, rule_id, source_id, locator}], checks 4종(BASELINE_INTEGRITY, GEOMETRY_ATTRIBUTES, QUANTITY_RECONCILIATION, REPRODUCIBILITY) | seed / SUPPLEMENTED_MODEL / STRUCTURED_MODEL_DATA / changes / verification | 키 이름 맞추고 checks 4종 만들기. 우리는 객체 전부 ADD (배관 객체 수정 없음) |
| STRUCTURED_MODEL_DATA | schema_version·profile·rev, baseline_sha256, data_mode=FULL/DELTA, model_units, coordinate_reference, composition_notes, records[{object_id, entity_id, operation, scope_ids, rule_id, geometry, attributes}] | 종류별 배열(instruments/jbs/cables/trays/supports…) | **DELTA**(계장 객체만 ADD)로 records 한 줄씩 변환. geometry=좌표·경로, attributes=태그·JB·트레이 번호 (지금 props 그대로) |
| checkpoint | `checkpoint_T1-CI_<stage>_R<YYYYMMDD-HHMMSS>.json`: {profile_id, stage, versions{instruction_rev, scope_rev, rule_rev, model_rev}, source_registry, confirmed_decisions, pending_issues, draft_files[{filename, revision, approval_state, reattach(지금/필요할 때), reason, note}], next_step, updated_at} | 없음 (우리는 decision_log.json, revisions/) | 3D 인계 때 checkpoint 하나 같이 내기 (회사 Copilot 새 채팅 RESUME용) |

### B. 내용 (프로그램만으로는 못 채움 — 사람·회사 절차)

1. **승인 기록**: scope_approval, engineering_approval, approved_by/approval_date — 공종 책임자 실명·일자. 프로그램은 빈칸 + DRAFT_NOT_READY로 냄 (가이드도 그렇게 요구).
2. **독립 기대값 사전 잠금 (G5)**: 정상/변경/누락/독립(HOLDOUT) 사례의 기대값·허용차를 **실행 전에** 공종이 잠그고, 실행자는 기대값을 모른 채 실행. 지금 우리 05는 자체 불변 조건 점검이라 독립 검증으로 인정 안 됨 → 기대값 입력·잠금 화면(잠근 시각 기록) 필요. HOLDOUT은 다른 실적(이전 사업 물량·수기 계산서) 필요.
3. **원도 보정 증거 (G2)**: 원도 표시값 / AI 판독값 / 엔지니어 수정값 / 근거 / 확인자 + 수정 전후 물량. 우리 검토 판단(decisions.json, overrides)을 evidence/로 내보내면 됨 (프로그램 작업). 확인자 이름은 사람.
4. **A/B/C 배치안 비교**: 같은 Scope·Rule·Rev로 배치안 여러 개 물량·제약 비교, Rating(정규화 + 합의 가중치), 제약 위반은 HOLD. **우리에 없음.** 시나리오(체크리스트)는 있지만 배치안(PLOT 대안)별 비교는 없음.
5. **공종 인터페이스 (G4)**: instrument_tag / io_id / jb_id / circuit / route_segment ID, **전기(T1-EL)와 공용 통로 분리·귀속**, 중복 제거. 우리는 io_id·circuit(케이블 번호)·route_segment(트레이 구간 번호)는 있음. 전기와의 공용 트레이 귀속 규칙·join_key 합의는 전기 담당과 해야 함 (전기 3D 데이터 오면).
6. **S00 회사 Copilot 기능 시험**: 기술 등록·첨부 읽기·코드 실행·파일 생성/다운로드·수동 재첨부 — 회사 Agent에서 사람이 시험. 파일럿은 **T1-EL(전기)이 먼저** (가이드: 통과 전 다른 공종 확대를 완료로 기록하지 않음).
7. **Seed 원천 건수 확인**: 가이드 기준 raw 기기 92 · Line 562 · Node 88 · Valve 418 · Ref 82 / 수정 반영 91 · 562 · 88 · 418 · 104. 03 VALVES 418행은 계기 목록이 아님(우리도 계기는 P&ID에서 따로 읽음 → 맞음).

### C. 우리에만 있는 것 (가이드에 없음 — evidence/로 넣으면 됨)

- 3D 사전 점검(V01~V09) · 회사 AI 리뷰 프롬프트/답 스키마, 공통 프로토콜(P01~P10), 다른 공종 충돌 회피 기록, 결정 보호·3D 반영 관문 기록, 산출근거 엑셀(식에 숫자 대입), 트레이 단면 케이블 배열(Tray_Section).

## 3. 제안 순서

1. **(프로그램, 바로 가능)** 7종 + STRUCTURED_MODEL_DATA + checkpoint를 AI3D-HANDOFF-1.1 필드 그대로 출력. 폴더 `T1-CI_scopeRevNN_ruleRevNN/{model,evidence}`. 승인 칸은 비움, status DRAFT_NOT_READY. 06 checks 4종 중 BASELINE_INTEGRITY(해시)·QUANTITY_RECONCILIATION(모델 객체 수 = 물량)은 자동 점검 결과로 채우고 확인자는 비움.
2. **(프로그램 + 사람)** STEP 10에 '독립 검증 기대값 잠금' 화면: 엔지니어가 사례별 기대값·허용차 입력 → 잠금 시각 기록 → 그 뒤 실행 → 05 자동 대조.
3. **(프로그램)** 원도 보정 이력 evidence 내보내기 (검토 판단 → 원도/AI/수정/근거/전후 물량).
4. **(결정 필요)** A/B/C 배치안 비교 기능을 만들지 — PLOT 대안 2~3개를 같은 설정으로 돌려 물량·제약 비교표.
5. **(회사 절차)** T1-EL 파일럿 결과 보고 계장 S00~S07 진행, 공종 책임자 승인.
