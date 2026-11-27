# Base 요약 — 계장 (T1-CI) · 서남해 200MW 수전해-2 · R0

scope 01 · rule 01 · model 01 · 2026-11-27T08:39:14+09:00 · 상태 DRAFT_NOT_READY (공종 승인 전)

Base = 산출근거(pid_io 계산: 체크리스트 + STEP 6~9 설정 + 사람 결정) + PLOT 마크업(`PLOT_MARKUP.png`). 원본 큰 파일은 제출하지 않고 아래 '원본 목록'으로 참조합니다.

## 1. 물량 요약 (01_scope.csv와 같음)
| scope_id | 항목 | 규격 | 단위 | 물량 | 여유(margin) | Rule |
|---|---|---|---|---|---|---|
| CI-INST | 계기 | Tag (P&ID + Typical 파생 + 트레인·대수 복제) | EA | 1252 |  | R-INST |
| CI-IO-AI | I/O AI | AI (스페어 포함) | PT | 152 |  | R-IO |
| CI-IO-AO | I/O AO | AO (스페어 포함) | PT | 26 |  | R-IO |
| CI-IO-DI | I/O DI | DI (스페어 포함) | PT | 484 |  | R-IO |
| CI-IO-DO | I/O DO | DO (스페어 포함) | PT | 300 |  | R-IO |
| CI-IO-COMM | 통신 포트 | Serial / Comm (패키지 · MCC) | EA | 12 |  | R-IO |
| CI-CB-MC-48PX125SQOS | 계장 케이블 (MCC) | 48P x 1.25SQ OS | m | 925 |  | R-CB-MCC |
| CI-CB-MU-40PX125SQISOS | 계장 케이블 (멀티) | 40P x 1.25SQ IS-OS | m | 4575 |  | R-CB-MULTI |
| CI-CB-MU-40PX125SQOS | 계장 케이블 (멀티) | 40P x 1.25SQ OS | m | 3390 |  | R-CB-MULTI |
| CI-CB-MU-60PX125SQISOS | 계장 케이블 (멀티) | 60P x 1.25SQ IS-OS | m | 285 |  | R-CB-MULTI |
| CI-CB-MU-60PX125SQOS | 계장 케이블 (멀티) | 60P x 1.25SQ OS | m | 285 |  | R-CB-MULTI |
| CI-CB-BR-1PX125SQOS | 계장 케이블 (분기) | 1P x 1.25SQ OS | m | 4090 |  | R-CB-BRANCH |
| CI-CB-BR-2CX20SQOS | 계장 케이블 (분기) | 2C x 2.0SQ OS | m | 245 |  | R-CB-BRANCH |
| CI-CB-CM-FO12CSMARMOURED | 계장 케이블 (통신) | FO 12C SM Armoured | m | 3380 |  | R-CB-COMM |
| CI-CB-PK-6PX125SQOS | 계장 케이블 (패키지) | 6P x 1.25SQ OS | m | 38400 |  | R-CB-PKG |
| CI-JB-40P | 정션 박스 | 40P | EA | 28 |  | R-JB |
| CI-JB-60P | 정션 박스 | 60P | EA | 2 |  | R-JB |
| CI-TR-SIG-300 | 사다리 트레이 | 신호 300×150 | m | 355 | 36 | R-TR |
| CI-TR-SIG-600 | 사다리 트레이 | 신호 600×150 | m | 84 | 9 | R-TR |
| CI-TR-SIG-900 | 사다리 트레이 | 신호 900×150 | m | 256 | 26 | R-TR |
| CI-TR-COM-300 | 사다리 트레이 | 통신 300×150 | m | 311 | 32 | R-TR |
| CI-UG-W300 | UG 트렌치 | 폭 300 | m | 715 | 36 | R-UG |
| CI-UG-W450 | UG 트렌치 | 폭 450 | m | 78 | 4 | R-UG |
| CI-UG-W1200 | UG 트렌치 | 폭 1200 | m | 111 | 6 | R-UG |
| CI-PT-100 | Perforated 트레이 | 폭 100 | m | 4335 |  | R-PT |
| CI-SP-RT | 트레이 서포트 | 랙 위 T 서포트 (적층) (TS-04 (일반값)) | EA | 16 |  | R-SP |
| CI-SP-RF | 트레이 서포트 | 랙 위 피팅 보조 서포트 (TS-07 (일반값)) | EA | 146 |  | R-SP |
| CI-SP-RC | 트레이 서포트 | 랙 위 클램프 () | EA | 30 |  | R-SP |
| CI-SP-UB | 트레이 서포트 | 트렌치 브래킷 (TS-05 (일반값)) | EA | 667 |  | R-SP |
| CI-SP-PB | 트레이 서포트 | Perforated 브래킷 (TS-06 (일반값)) | EA | 2988 |  | R-SP |
| CI-SP-KG | 서포트 강재 | C100×50×5/7.5 외 (할증 별도) | kg | 11217.5 | 1123.5 | R-SP |
| CI-SP-EXP | 익스펜션 스플라이스 | 플레이트 세트 | SET | 6 |  | R-SP-EXP |

범위 밖: CI-X-MCCIRP MCC ↔ IRP 배선 = OTHER_PACKAGE (전기실 안 배선 - 전기 공종 범위 (STEP 6 'MCC 신호 출발점 = IRP')); CI-X-VENDOR 벤더 패키지 내부 IO · 배선 = OTHER_PACKAGE (벤더 공급 범위 (체크리스트 A03, 벤더 경계)); CI-X-FG F&G 검지기 (GD / FD) · 알람 = HOLD (P&ID에 없음 - F&G 배치도 필요 (레퍼런스 인덱스에는 있음))

## 2. 기본값과 다른 설계 가정 (현재 값)
| 설정 | 현재 | 기본값 |
|---|---|---|
| 랙 최상단 높이 (트레이 EL) (`rack_el`) | 11.0 | 6.0 |
| 랙 출처 (`rack_src`) | 3D 모델 랙 | PLOT 인식 |
| 랙 트레이 EL 출처 (`rack_el_src`) | 3D 모델 케이블 단 | 체크리스트 값 |
| 3D 모델 장비 상자 피하기 (`slot_3d_eq`) | 사용 (3D 모델 있을 때) | 안 함 |

## 3. 사람 결정 (원도 보정 · 배치 수정) — 자세히 evidence/correction_log.csv
- 노트 해석 (ONLY ONE SHOWN): 1건
- 3D 반영 관문: 3건
- 합계 (보정 전 → 후): 1건

## 4. 이번 Rev(R0)에 반영한 코멘트
- 없음 (R0 기준선)

## 5. 원본 목록 (제출하지 않음 · 요청 시 제공)
| source_id | 파일 | Rev | authority | SHA-256 |
|---|---|---|---|---|
| SRC-PID | 200MW PEM 수전해 플랜트 PID_Rev.A 1.pdf | Rev.A (파일명·타이틀 블록) | VERIFIED_SOURCE | a29f5fc969b8f4f5… |
| SRC-PLOT | Plot_plan_261109_r2.pdf | 파일명 기준 | VERIFIED_SOURCE | fc4d967b8d623511… |
| SRC-PLOTREF | Plot_Plan_Rev.2_260202.pdf | 파일명 기준 | REFERENCE | 55c0bfec8aa4e471… |
| SRC-TEMPLATE | Instrument_Index_Template.xlsx | 회사 양식 | APPROVED_STANDARD | f2032d021f24eba5… |
| SRC-REF | (서남해 수전해) Instrument Index_Rev.A_26.03.20_Metering IO 삭제.xlsx | 이전 리비전 | REFERENCE | 4da0e12c5272f94a… |
| SRC-CHECKLIST | concept.xlsx + cable.json | 프로젝트 현재값 | REFERENCE | c5b5f9661263f675… |
| SRC-BASE | 02-AI-Assisted.Conceptual.3D.Model_Final.html | 3d-rev0 | SEED_PROTOTYPE | 35d0e456ad1bbb7f… |
| SRC-CATALOGUE | 케이블 외경표 (STEP 8 T10~T15E) | 외장형 제조사 공개 카탈로그 값 | REFERENCE | … |
| SRC-NEMA | NEMA VE 2 | 판본 확인 전 | REFERENCE | … |
| SRC-PIDIO | pid_io v13.3 | 프로그램 | REFERENCE | … |

## 6. 이 제출 묶음
- 00_manifest.json ~ 06_model_handoff.json (표준 7종)
- model/ 보강 모델 HTML + STRUCTURED_MODEL_DATA (DELTA)
- 3D_BUILD_PROMPT.md (회사 AI용 3D 구현 프롬프트)
- BASE_SUMMARY.md + PLOT_MARKUP.png
- checkpoint_*.json (회사 Copilot RESUME)
- evidence/ run_*.json · correction_log.csv · model_checks.json · pid_io_audit.csv (큰 근거 파일은 참조)
