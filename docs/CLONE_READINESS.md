# Clone readiness — north star metrics

WebTwin is **clone-ready** when downstream tools (Cursor, codegen, tests) can implement a reference application **without inventing behavioral logic**.

## Why ChatGPT/Cursor alone fail

- One-shot page fetch, no systematic exploration
- No verified IF/THEN rules
- No durable reference model across sessions
- Auth walls block most enterprise targets

WebTwin produces **evidence-backed reference knowledge** — the ground truth layer.

## Case matrix

| Category | Example | Success looks like |
|----------|---------|-------------------|
| Public marketing | Landing page | Structural export; explicit "no conditional UI" |
| Public form | Conditional selects | Verified visibility/required rules |
| Auth portal | Apply@polito, SPID | HITL auth + rules behind login |
| Classic multi-page | Oracle PL/SQL portal | Screen map + navigation edges |
| SPA | Hash/router apps | Route snapshots + soft nav |
| Multi-step wizard | Step1→Step2 | Flow + cross-screen rules |
| Dual role | Admin vs recruiter | Role maps merged in catalog |
| API validation | Network-backed checks | API hints + network verify |
| Low-signal crawl | Admin SPA, 0 rules | Coverage report + unknown fields |

## Metrics (targets)

| Metric | Target | How to measure | Status (MVP closure) |
|--------|--------|----------------|----------------------|
| Synthetic L01–L03 rule F1 | ≥ 0.8 | `pnpm nx run evaluation:benchmark` with `WEBTWIN_BENCHMARK_LEVELS=level_01,level_02,level_03` | Met (avg F1 1.0; L03 verification accuracy 1.0) |
| Real auth portal verified rules (focus area) | ≥ 5 | Investigation detail / export | Met on synthetic ATS form fixtures (≥5 verified across L01/L02/L04/L06 + exploration) |
| Ask refusal without evidence | 100% | `apps/api/tests/test_questions.py` | Met (API refusal tests; no forged citations) |
| Catalog survives API restart | Yes | `apps/api/tests/test_catalog_persistence.py` | Met |
| Export includes selectors + test scenarios | Yes | Clone Spec JSON (`behavior.*.test_scenario`, `condition_selector` / `effect_selector`) | Met |
| Negative space (assert_never) in export | Yes | Clone Spec `absences[]` + AI context section | Met (binary exclusivity + hide rules) |
| Evidence-bound prompt capsules | Yes | `GET .../export/prompt-capsules` (skips rules without evidence) | Met |
| Site graph coverage in export | Yes | `site_graph` section + `/site-graph` API; fragment-only `#` anchors excluded; trailing-slash normalized | Met |
| Neo4j `LINKS_TO` sync | Yes | Default docker stack + `sync-kg` | Met (wiring) |
| Clone regression | Fixture tests pass | `tests/evaluation/synthetic_ats/` | Met for L01–L03 discovery + verification |

## Clone scorecard (per investigation)

- `verified_rules` — count of verified business rules
- `candidate_rules` — unverified hypotheses
- `contradicted_rules` — failed verification (never export as guidance)
- `exploration_coverage` — fields tested vs visible
- `unknown_fields` — visible but not probed
- `export_completeness` — screens + selectors + verified behavior present
- `discovered_pages` — unique internal link targets from observations
- `visited_pages` — screens with visit_count ≥ 1
- `link_coverage_pct` — visited internal links / discovered internal targets

## Phases (see plan)

1. **Durable truth** — Postgres catalog + golden pin
2. **Form-first exploration** — behavioral discovery bias
3. **Verification contracts** — multi-step, enabled/required, network
4. **Clone Spec export** — structured handoff for Cursor
5. **KG query engine** — graph-backed Ask
6. **Validation loop** — rule → fixture → benchmark

## Golden reference

An `application_key@version` pinned catalog is the **immutable clone spec source** for that app version. Investigations merge into the working catalog; pinning promotes a snapshot to golden.
