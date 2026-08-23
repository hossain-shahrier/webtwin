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

| Metric | Target | How to measure |
|--------|--------|----------------|
| Synthetic L01–L03 rule F1 | ≥ 0.8 | `tests/evaluation/run_benchmark.py` |
| Real auth portal verified rules (focus area) | ≥ 5 | Investigation detail / export |
| Ask refusal without evidence | 100% | `apps/api/tests/test_questions.py` |
| Catalog survives API restart | Yes | `apps/api/tests/test_catalog_persistence.py` |
| Export includes selectors + test scenarios | Yes | Clone Spec JSON |
| Site graph coverage in export | Yes | `site_graph` section + `/site-graph` API |
| Neo4j `LINKS_TO` sync | Yes | Default docker stack + `sync-kg` |
| Clone regression | Fixture tests pass | `tests/evaluation/synthetic_ats/` |

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
