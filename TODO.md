# Robotics 역문서엔진 — 구현 백로그

> 출처: 적대적 갭 감사(`dynamicWorkflow/docs/reverse_doc_loop_adversarial_review.md`) + 수정루프(`reverse_doc_source_fix_loop.md`) + 설계 §7(`HCA_Code2Rule/역문서엔진설계변경.md`) + MVP 설계(`docs/superpowers/specs/2026-06-16-역문서-mvp-현상파악-design.md`)
> 갱신: 2026-06-16
> ★ **방향 전환(2026-06-16):** 복잡한 수렴 기계는 **보류.** **의존성 순서 적재로 현상부터 파악**한다. 의존성 순서면 callee 방향은 자연 해결되고, 남는 caller 정보는 현상 파악 단계에선 수용.

---

## ✅ 완료 (커밋 `9d26a79`)

- [x] 🔵 B1 — validator 프로시저 누락 50% 임계 제거 → 0% 누락 fail
- [x] 🔵 B3 — HEADER/BODY 분리로 public 분모 과대제외 해소 (`_public_procs`, `PKG_BODY_RE`)
- [x] 🔵 B2 — 3회 실패 시 `content=""` 폐기 → 최선버전 보존 + `save_partial`

---

## 🟢 P0 — MVP 현상 파악. 설계: `2026-06-16-역문서-mvp-현상파악-design.md` / 계획: `plans/2026-06-16-역문서-mvp-현상파악.md`

- [x] **M1. 의존성 순서 정렬기** — `dependency_order.py` 위상 정렬(callee 우선)+테스트 (커밋 `c5f6845`,`9884167`)
- [x] **M2. 순차 적재 드라이버** — `ingest_driver.py` `run_ingestion`(DI)+`HttpRoboticsClient`+테스트 (커밋 `5dc4815`,`ead3691`)
- [x] **M3. 현상 요약/템플릿** — `observation.py` `summarize`+`docs/observations/TEMPLATE.md`+테스트 (커밋 `f638a59`)
- [ ] **M4. 사내망 실행** — 실 의존성 데이터+패키지 바디로 `run_ingestion` 돌리고 `TEMPLATE.md`로 현상 1건 기록 (이 PC 범위 밖, 사내망)

> 코드(M1~M3)는 master 머지 완료(신규 12테스트 green). **실관찰(M4)은 사내망에서.**
> 검증은 이미 있는 Inner 루프 **기준 1·2만** 사용. 3·4·5는 안 함.

---

## ⏸️ 보류 (deferred) — 현상 관찰이 필요성을 입증하면 꺼낸다

> 분석(적대적 감사·§7)에서 도출됐으나 MVP 단계엔 과함. **관찰이 근거를 줄 때까지 만들지 않는다.**

- [ ] (D) 보완 필요 항목 섹션(prompts 10섹션) + 기준5 검증 _(§7 개정1, weakest link)_
- [ ] (D) Outer 루프 substrate — parked 상태 / 재트리거 주체(이벤트훅 vs 스캐너) / admin 재처리 경로 _(§7 개정3)_
- [ ] (D) 캐시키 graph_epoch _(§7 개정4)_
- [ ] (D) caller 정보 back-fill (one-shot sweep) — "누가 X를 호출하나" 채우기
- [ ] (D) 비용·예산 게이트 _(§7 개정5)_
- [ ] (D) 기준3·4 judge / 그래프 추출기(PR#458) _(그래프 의존)_

---

## 🟡 P1 — 검증 강화 (MVP 현상 본 뒤)

- [ ] 기준1 정의 확정 — 0% 누락(완료) + HEADER 선언부만 스캔 명문화·테스트 _(§7 개정2)_
- [ ] 기준2 hard gate — `validator`에 "3. 입출력 파라미터" 섹션 존재 검증 추가
- [ ] check1 식별자 검증 보강 — `TBL_*` 등 참조 식별자도 검증 (`test_check1_fail_missing_identifier`) _(오늘 범위밖)_

---

## ⚪ P2 — 인프라 (독립)

- [ ] 업로드 크기 제한 — 초과 시 413 (`test_file_too_large`) _(오늘 범위밖)_
