# Clone workflow — URL to faithful implementation

This is the end-to-end flow WebTwin supports for building a **source of truth** that Cursor (or any builder) can implement against — without inventing behavioral logic.

## 1. Define intent

In **Investigations → New investigation**:

| Field | Purpose |
|-------|---------|
| Application URL | Reference system entry point |
| Focus | Biases exploration (e.g. `address`, `checkout`) — **not** exploration policy |
| Exploration mode | `Site map (deep crawl)` or `Form / behavior` |
| Investigation scope | `full_site`, `catalog`, `checkout`, etc. — for scoped workers |
| URL prefix | Limit crawl to paths like `/product-category/` |
| Role | Partitions maps (`applicant`, `recruiter`, `admin`) |
| Application name | Stabilizes `application_key` across runs |
| SPA mode | Soft navigation for hash/router apps |

Start a **headed worker** for authenticated targets:

```bash
pnpm nx run browser:worker-headed
```

## 2. Investigate

The browser worker:

1. Opens the URL (Playwright)
2. Pauses for login if needed (HITL in the Playwright window)
3. Explores with **form-first** bias (selects/inputs before nav chrome)
4. Records observations, diffs, candidate rules, network shapes

## 3. Verify

After exploration, each candidate rule gets verification experiments:

- Set trigger → assert effect
- Alternate/clear → assert inverse
- Required/enabled checks where applicable

Only **verified** rules are clone-grade truth. Candidates are hypotheses.

## 4. Review

Open the investigation → **System** tab:

- **Site graph** — interactive map of screens and discovered links (visited vs unvisited)
- **Role map** — screens, entities, rules for this persona
- **Shared catalog** — merged knowledge across runs (same `application_key`)
- **Entities / screens / flows / logic**

## 5. Export clone spec

Use **Export Clone Spec** (JSON) or **Copy for Cursor** (markdown + structured context).

Clone Spec includes:

- Screens with selectors, field types, entities
- **`site_graph`** — full adjacency (nodes, edges, coverage, unvisited sample)
- Navigation and flows
- Verified / candidate / contradicted behavior tiers
- Unknown fields (not yet probed)
- API hints from network capture

For large sites, also fetch `GET /investigations/{id}/site-graph` or use the bundled JSON.

### Reference folder layout (clone repos)

```
reference/
  clone-spec.json      # includes site_graph section
  site-graph.json      # optional copy from API
  CURSOR.md            # generated context
```
- Test scenarios per verified rule

API:

- `GET /investigations/{id}/export/clone-spec`
- `GET /applications/{key}/export/clone-spec` (catalog + golden)

## 6. Implement in Cursor

Paste Clone Spec or Cursor export. Instruct the model:

- Implement **verified rules only** as behavioral contracts
- Treat **candidates** as TODO/hypothesis
- Do **not** invent API or role rules not in the spec
- Match **behavior**, not pixels

## 7. Validate the clone

Run synthetic fixtures derived from verified rules:

```bash
cd python/webtwin_core && uv run pytest tests/test_reference_system.py -q
python tests/evaluation/generate_rule_fixtures.py --investigation-id <uuid>
pnpm nx run webtwin-core:test
```

Benchmark regression:

```bash
python tests/evaluation/run_benchmark.py
```

## 8. Pin golden reference

When a catalog is good enough for production clone work:

```bash
curl -X POST http://127.0.0.1:8060/applications/{application_key}/golden/v1
```

Golden snapshots survive API restart when using Postgres + file-backed catalog store.

## Success checklist

See [CLONE_READINESS.md](./CLONE_READINESS.md) for metrics and case matrix.
