'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AppShell,
  formatStatus,
  shortHost,
  statusBadgeClass,
} from '../../../components/app-shell';
import { AuthPausePanel } from '../../../components/auth-pause-panel';
import { SiteGraph } from '../../../components/site-graph';
import {
  askQuestion,
  getEvidence,
  getInvestigationDetail,
  getMetrics,
  getReferenceSystem,
  getRuleProvenance,
  getRules,
  getTimeline,
  getTransitions,
  restartFailedInvestigation,
  resumeFailedInvestigation,
  exportCursorContext,
  exportCloneSpec,
  exportAiSpec,
  exportPromptCapsules,
  exportContracts,
  getDriftReport,
  pinGoldenCatalog,
} from '../../../lib/api';
import {
  copyOrDownloadText,
  exportFilename,
  exportResultMessage,
} from '../../../lib/export-download';
import type {
  BusinessRule,
  EvaluationRun,
  Evidence,
  InvestigationDetail,
  InvestigationTransition,
  ReferenceSystemContext,
  RuleProvenance,
  TimelineEvent,
} from '../../../lib/types';
import styles from '../../ui.module.css';

type Tab = 'findings' | 'system' | 'ask' | 'activity';

export default function InvestigationDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [transitions, setTransitions] = useState<InvestigationTransition[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [rules, setRules] = useState<BusinessRule[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [metrics, setMetrics] = useState<EvaluationRun[]>([]);
  const [referenceSystem, setReferenceSystem] = useState<ReferenceSystemContext | null>(null);
  const [tab, setTab] = useState<Tab>('findings');
  const [question, setQuestion] = useState('Why does this field appear?');
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<
    Array<{
      rule_id?: string;
      evidence_id?: string;
      confidence?: number;
      label?: string;
    }>
  >([]);
  const [asking, setAsking] = useState(false);
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<RuleProvenance | null>(null);

  const refresh = useCallback(async () => {
    if (!params.id) return;
    try {
      const [
        nextDetail,
        nextTransitions,
        nextTimeline,
        nextRules,
        nextEvidence,
        nextMetrics,
        nextReference,
      ] = await Promise.all([
        getInvestigationDetail(params.id),
        getTransitions(params.id),
        getTimeline(params.id),
        getRules(params.id),
        getEvidence(params.id),
        getMetrics(params.id),
        getReferenceSystem(params.id).catch(() => null),
      ]);
      setDetail(nextDetail);
      setTransitions(nextTransitions);
      setTimeline(nextTimeline);
      setRules(nextRules);
      setEvidence(nextEvidence);
      setMetrics(nextMetrics);
      setReferenceSystem(nextReference);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to load investigation',
      );
    }
  }, [params.id]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  const sortedRules = useMemo(
    () =>
      [...rules].sort((a, b) => {
        const rank = (status: string) => {
          if (status === 'verified') return 0;
          if (status === 'under_verification') return 1;
          if (status === 'candidate') return 2;
          if (status === 'contradicted') return 3;
          return 4;
        };
        return rank(a.status) - rank(b.status) || b.confidence - a.confidence;
      }),
    [rules],
  );

  const evidenceSummary = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of evidence) {
      counts[item.type] = (counts[item.type] ?? 0) + 1;
    }
    return counts;
  }, [evidence]);

  if (!detail) {
    return (
      <AppShell>
        <p className={styles.empty}>{error ?? 'Loading investigation…'}</p>
      </AppShell>
    );
  }

  const { investigation, session } = detail;
  const latestMetrics = metrics[metrics.length - 1];
  const verifiedCount = rules.filter(
    (rule) => rule.status === 'verified',
  ).length;
  const candidateCount = rules.filter(
    (rule) => rule.status === 'candidate',
  ).length;
  const underVerificationCount = rules.filter(
    (rule) => rule.status === 'under_verification',
  ).length;
  const contradictedCount = rules.filter(
    (rule) => rule.status === 'contradicted',
  ).length;
  const needsAttention =
    investigation.status === 'auth_required' ||
    investigation.status === 'failed';

  async function openProvenance(ruleId: string) {
    setSelectedRuleId(ruleId);
    try {
      setProvenance(await getRuleProvenance(investigation.id, ruleId));
    } catch (err) {
      setProvenance(null);
      setError(
        err instanceof Error ? err.message : 'Failed to load rule evidence',
      );
    }
  }

  return (
    <AppShell>
      <Link href="/investigations" className={styles.back}>
        ← Investigations
      </Link>

      <header className={styles.fadeIn}>
        <div className={styles.headerRow}>
          <div>
            <h1 className={styles.pageTitle}>{investigation.goal}</h1>
            <a
              className={styles.targetLink}
              href={investigation.target_url}
              target="_blank"
              rel="noreferrer"
            >
              {shortHost(investigation.target_url)}
            </a>
          </div>
          <span className={statusBadgeClass(investigation.status)}>
            {formatStatus(investigation.status)}
          </span>
        </div>
        <div className={styles.statLine}>
          <span>
            <strong>{verifiedCount}</strong> verified
          </span>
          <span>
            <strong>{candidateCount}</strong> candidates
          </span>
          {underVerificationCount > 0 && (
            <span>
              <strong>{underVerificationCount}</strong> verifying
            </span>
          )}
          {contradictedCount > 0 && (
            <span>
              <strong>{contradictedCount}</strong> contradicted
            </span>
          )}
          <span>
            <strong>{evidence.length}</strong> evidence
          </span>
          {latestMetrics && (
            <>
              <span>
                <strong>{latestMetrics.actions_taken}</strong> actions
              </span>
              <span>
                <strong>{latestMetrics.pages_seen}</strong> pages
              </span>
            </>
          )}
          <span className={styles.mono}>{investigation.id.slice(0, 8)}</span>
          <button
            type="button"
            className={styles.btnGhost}
            style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
            onClick={async () => {
              try {
                const payload = await exportAiSpec(investigation.id);
                const filename = exportFilename(investigation.id, 'ai-context', 'md');
                const result = await copyOrDownloadText({
                  text: payload.markdown,
                  filename,
                  mime: 'text/markdown;charset=utf-8',
                });
                setExportNote(exportResultMessage(result, 'AI context', filename));
              } catch (err) {
                setExportNote(
                  err instanceof Error ? err.message : 'Export failed',
                );
              }
            }}
            title="Copies markdown to clipboard, or downloads .md if the export is large"
          >
            Copy AI Context
          </button>
          <button
            type="button"
            className={styles.btnGhost}
            style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
            onClick={async () => {
              try {
                const payload = await exportCursorContext(investigation.id);
                const filename = exportFilename(investigation.id, 'cursor-context', 'md');
                const result = await copyOrDownloadText({
                  text: payload.markdown,
                  filename,
                  mime: 'text/markdown;charset=utf-8',
                });
                setExportNote(exportResultMessage(result, 'Cursor context', filename));
              } catch (err) {
                setExportNote(
                  err instanceof Error ? err.message : 'Export failed',
                );
              }
            }}
            title="Copies markdown to clipboard, or downloads .md for Cursor chat"
          >
            Copy for Cursor
          </button>
          <button
            type="button"
            className={styles.btnGhost}
            style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
            onClick={async () => {
              try {
                const spec = await exportCloneSpec(investigation.id);
                const json = JSON.stringify(spec, null, 2);
                const filename = exportFilename(investigation.id, 'clone-spec', 'json');
                const result = await copyOrDownloadText({
                  text: json,
                  filename,
                  mime: 'application/json;charset=utf-8',
                });
                setExportNote(exportResultMessage(result, 'Clone Spec JSON', filename));
              } catch (err) {
                setExportNote(
                  err instanceof Error ? err.message : 'Clone spec export failed',
                );
              }
            }}
          >
            Export Clone Spec
          </button>
          <button
            type="button"
            className={styles.btnGhost}
            style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
            onClick={async () => {
              try {
                const payload = await exportPromptCapsules(investigation.id);
                const filename = exportFilename(investigation.id, 'prompt-capsules', 'md');
                const result = await copyOrDownloadText({
                  text: payload.markdown,
                  filename,
                  mime: 'text/markdown;charset=utf-8',
                });
                setExportNote(
                  exportResultMessage(
                    result,
                    `${payload.capsules.length} prompt capsule(s)`,
                    filename,
                  ),
                );
              } catch (err) {
                setExportNote(
                  err instanceof Error ? err.message : 'Prompt capsule export failed',
                );
              }
            }}
            title="Evidence-bound Cursor capsules — skips rules without citations"
          >
            Export Capsules
          </button>
          <button
            type="button"
            className={styles.btnGhost}
            style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
            onClick={async () => {
              try {
                const pack = await exportContracts(investigation.id);
                const file = pack.files[0];
                const filename = exportFilename(investigation.id, 'contracts', 'py');
                const result = await copyOrDownloadText({
                  text: file?.content || JSON.stringify(pack, null, 2),
                  filename,
                  mime: 'text/x-python;charset=utf-8',
                });
                setExportNote(
                  exportResultMessage(
                    result,
                    `${pack.rule_count} contract(s)`,
                    filename,
                  ),
                );
              } catch (err) {
                setExportNote(
                  err instanceof Error ? err.message : 'Contract export failed',
                );
              }
            }}
            title="Executable Playwright pytest contracts from verified rules"
          >
            Export Contracts
          </button>
          <button
            type="button"
            className={styles.btnGhost}
            style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
            onClick={async () => {
              try {
                const report = await getDriftReport(investigation.id, 'v1');
                const filename = exportFilename(investigation.id, 'drift', 'md');
                const result = await copyOrDownloadText({
                  text: report.markdown,
                  filename,
                  mime: 'text/markdown;charset=utf-8',
                });
                setExportNote(
                  exportResultMessage(
                    result,
                    `Drift report (${Math.round((report.freshness_pct || 0) * 100)}% fresh)`,
                    filename,
                  ),
                );
              } catch (err) {
                setExportNote(
                  err instanceof Error ? err.message : 'Drift report failed',
                );
              }
            }}
            title="Compare live verified rules against golden pin"
          >
            Drift Report
          </button>
          {referenceSystem?.application_key && investigation.status === 'completed' && (
            <button
              type="button"
              className={styles.btnGhost}
              style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem' }}
              onClick={async () => {
                try {
                  await pinGoldenCatalog(referenceSystem.application_key!, 'v1');
                  setExportNote(`Pinned golden catalog for ${referenceSystem.application_key}`);
                  await refresh();
                } catch (err) {
                  setExportNote(
                    err instanceof Error ? err.message : 'Pin golden failed',
                  );
                }
              }}
            >
              Pin golden
            </button>
          )}
        </div>
        {exportNote && <p className={styles.hint}>{exportNote}</p>}
      </header>

      {error && <p className={styles.error}>{error}</p>}

      {investigation.status === 'auth_required' && (
        <div style={{ marginBottom: '1rem' }}>
          <AuthPausePanel
            investigation={investigation}
            session={session}
            onUpdate={refresh}
          />
        </div>
      )}

      {investigation.status === 'failed' && (
        <section
          className={styles.panel}
          style={{ marginBottom: '1rem', borderColor: '#f0b4b4' }}
        >
          <h2 className={styles.panelTitle}>Investigation stopped</h2>
          <p className={styles.hint} style={{ marginBottom: '0.85rem' }}>
            {investigation.failure_reason ??
              'Something went wrong during investigation.'}
          </p>
          {investigation.checkpoint ? (
            <button
              className={styles.btn}
              type="button"
              onClick={async () => {
                try {
                  const updated = await resumeFailedInvestigation(investigation.id);
                  setExportNote(
                    `Resumed at checkpoint (status: ${updated.status}). ` +
                      'Ensure the browser worker is running to continue the crawl.',
                  );
                  await refresh();
                } catch (err) {
                  setError(
                    err instanceof Error ? err.message : 'Resume failed',
                  );
                }
              }}
            >
              Resume from checkpoint
            </button>
          ) : (
            <button
              className={styles.btn}
              type="button"
              onClick={async () => {
                try {
                  await restartFailedInvestigation(investigation.id);
                  await refresh();
                } catch (err) {
                  setError(
                    err instanceof Error ? err.message : 'Restart failed',
                  );
                }
              }}
            >
              Re-queue investigation
            </button>
          )}
        </section>
      )}

      {!needsAttention && (
        <>
          <div className={styles.tabs}>
            {(
              [
                ['findings', 'Findings'],
                ['system', 'System'],
                ['ask', 'Ask'],
                ['activity', 'Activity'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`${styles.tab} ${tab === id ? styles.tabActive : ''}`}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'findings' && (
            <section className={`${styles.panel} ${styles.fadeIn}`}>
              <h2 className={styles.panelTitle}>Business rules</h2>
              {sortedRules.length === 0 ? (
                <p className={styles.empty}>
                  {investigation.status === 'completed'
                    ? 'No behavioral rules were discovered on this target.'
                    : 'Rules will appear as the worker explores and diffs UI states.'}
                </p>
              ) : (
                <ul className={styles.list}>
                  {sortedRules.map((rule) => (
                    <li key={rule.id} className={styles.item}>
                      <button
                        type="button"
                        className={styles.ruleBtn}
                        onClick={() => openProvenance(rule.id)}
                      >
                        <div className={styles.itemTop}>
                          <span className={statusBadgeClass(rule.status)}>
                            {formatStatus(rule.status)}
                          </span>
                          <span className={styles.mono}>
                            {Math.round(rule.confidence * 100)}%
                          </span>
                        </div>
                        <p className={styles.itemTitle}>{rule.name}</p>
                        <p className={styles.ruleIf}>
                          if {rule.condition.field} {rule.condition.operator}{' '}
                          {JSON.stringify(rule.condition.value)} →{' '}
                          {rule.effect.field}
                          {rule.effect.visible != null
                            ? ` visible=${String(rule.effect.visible)}`
                            : ''}
                          {rule.effect.required != null
                            ? ` required=${String(rule.effect.required)}`
                            : ''}
                        </p>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {provenance && selectedRuleId === provenance.rule.id && (
                <div className={styles.provenance}>
                  <h3>Evidence for this rule</h3>
                  <p
                    className={styles.hint}
                    style={{ marginBottom: '0.65rem' }}
                  >
                    {provenance.evidence.length} linked evidence ·{' '}
                    {provenance.experiments.length} verification run
                    {provenance.experiments.length === 1 ? '' : 's'}
                  </p>
                  {provenance.experiments.map((run) => (
                    <div key={run.id} style={{ marginBottom: '0.75rem' }}>
                      <div className={styles.itemTop}>
                        <span className={statusBadgeClass(run.status)}>
                          {formatStatus(run.status)}
                        </span>
                        <span className={styles.mono}>
                          {Math.round(run.confidence * 100)}%
                        </span>
                      </div>
                      <ul className={styles.timeline}>
                        {run.results.map((result, index) => (
                          <li key={`${run.id}-${index}`}>
                            <strong>{result.passed ? 'Pass' : 'Fail'}</strong> —{' '}
                            {result.details}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                  {provenance.evidence.slice(0, 6).map((item) => (
                    <p key={item.id} className={styles.hint}>
                      {item.type}
                      {item.url ? ` · ${shortHost(item.url)}` : ''} ·{' '}
                      {item.id.slice(0, 8)}
                    </p>
                  ))}
                </div>
              )}
            </section>
          )}

          {tab === 'system' && (
            <section className={`${styles.panel} ${styles.fadeIn}`}>
              <h2 className={styles.panelTitle}>Reference system</h2>
              {!referenceSystem ? (
                <p className={styles.empty}>Building system map from observations…</p>
              ) : (
                <>
                  <p className={styles.hint} style={{ marginBottom: '1rem' }}>
                    {referenceSystem.summary}
                  </p>
                  {(referenceSystem.clone_scorecard ||
                    referenceSystem.exploration_coverage !== undefined) && (
                    <div className={styles.split} style={{ marginBottom: '1.25rem' }}>
                      <div>
                        <h3 className={styles.panelTitle}>Clone scorecard</h3>
                        {referenceSystem.clone_scorecard ? (
                          <ul className={styles.timeline}>
                            <li>
                              <strong>{referenceSystem.clone_scorecard.verified_rules}</strong>{' '}
                              verified ·{' '}
                              <strong>{referenceSystem.clone_scorecard.candidate_rules}</strong>{' '}
                              candidate
                              {referenceSystem.clone_scorecard.contradicted_rules > 0
                                ? ` · ${referenceSystem.clone_scorecard.contradicted_rules} contradicted`
                                : ''}
                            </li>
                            <li>
                              export completeness{' '}
                              {Math.round(
                                referenceSystem.clone_scorecard.export_completeness * 100,
                              )}
                              % · clone ready{' '}
                              {referenceSystem.clone_scorecard.clone_ready ? 'yes' : 'no'}
                            </li>
                            {referenceSystem.clone_scorecard.gaps.length > 0 && (
                              <li>gaps: {referenceSystem.clone_scorecard.gaps.join('; ')}</li>
                            )}
                          </ul>
                        ) : (
                          <p className={styles.empty}>Scorecard unavailable.</p>
                        )}
                      </div>
                      <div>
                        <h3 className={styles.panelTitle}>Exploration coverage</h3>
                        <ul className={styles.timeline}>
                          <li>
                            coverage{' '}
                            {Math.round((referenceSystem.exploration_coverage ?? 0) * 100)}%
                          </li>
                          <li>
                            unexplored fields:{' '}
                            {referenceSystem.unexplored_fields?.length ?? 0}
                          </li>
                        </ul>
                        {(referenceSystem.unexplored_fields?.length ?? 0) > 0 && (
                          <p className={styles.hint} style={{ marginTop: '0.5rem' }}>
                            {referenceSystem.unexplored_fields!.slice(0, 8).join(', ')}
                            {(referenceSystem.unexplored_fields?.length ?? 0) > 8 ? '…' : ''}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  {(referenceSystem.role_map || referenceSystem.catalog) && (
                    <div className={styles.split} style={{ marginBottom: '1.25rem' }}>
                      <div>
                        <h3 className={styles.panelTitle}>
                          Role map ({referenceSystem.role_scope ?? 'default'})
                        </h3>
                        {referenceSystem.role_map ? (
                          <ul className={styles.timeline}>
                            <li>
                              <strong>{referenceSystem.role_map.screen_count}</strong> screens ·{' '}
                              <strong>{referenceSystem.role_map.navigation_count}</strong>{' '}
                              navigation
                            </li>
                            <li>
                              entities:{' '}
                              {referenceSystem.role_map.entity_names.join(', ') || '—'}
                            </li>
                            <li>
                              verified rules:{' '}
                              {referenceSystem.role_map.verified_rule_names.length}
                            </li>
                          </ul>
                        ) : (
                          <p className={styles.empty}>No role map yet.</p>
                        )}
                      </div>
                      <div>
                        <h3 className={styles.panelTitle}>Shared catalog</h3>
                        {!referenceSystem.catalog ? (
                          <p className={styles.empty}>
                            Completes into a shared catalog for this application key. Run another
                            role against the same URL to merge.
                          </p>
                        ) : (
                          <>
                            <p className={styles.hint}>
                              <span className={styles.mono}>
                                {referenceSystem.catalog.application_key}
                              </span>{' '}
                              · {referenceSystem.catalog.investigation_ids.length} runs ·{' '}
                              {Object.keys(referenceSystem.catalog.roles).length} roles
                            </p>
                            <ul className={styles.timeline}>
                              {Object.values(referenceSystem.catalog.roles).map((role) => (
                                <li key={role.role_scope}>
                                  <strong>{role.role_scope}</strong> —{' '}
                                  {role.entity_names.slice(0, 4).join(', ') || 'no entities'} ·{' '}
                                  {role.verified_rule_names.length} verified
                                </li>
                              ))}
                            </ul>
                            {referenceSystem.catalog.entities.length > 0 && (
                              <p className={styles.hint} style={{ marginTop: '0.5rem' }}>
                                Merged entities:{' '}
                                {referenceSystem.catalog.entities
                                  .map((entity) => entity.name)
                                  .join(', ')}
                              </p>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  )}
                  <h3 className={styles.panelTitle}>
                    Entities ({referenceSystem.entities?.length ?? 0})
                  </h3>
                  {(referenceSystem.entities?.length ?? 0) === 0 ? (
                    <p className={styles.empty} style={{ marginBottom: '1.25rem' }}>
                      No domain entities inferred yet — need form fields with recognizable names.
                    </p>
                  ) : (
                    <ul className={styles.list} style={{ marginBottom: '1.25rem' }}>
                      {referenceSystem.entities.map((entity) => (
                        <li key={entity.name} className={styles.item}>
                          <div className={styles.itemTop}>
                            <p className={styles.itemTitle}>{entity.name}</p>
                            <span className={styles.mono}>
                              {Math.round(entity.confidence * 100)}%
                            </span>
                          </div>
                          <p className={styles.hint}>
                            {entity.field_count} fields
                            {entity.screen_ids.length
                              ? ` · screens ${entity.screen_ids.slice(0, 3).join(', ')}`
                              : ''}
                          </p>
                          {entity.fields.slice(0, 5).map((ref, idx) => (
                            <p
                              key={`${entity.name}-field-${idx}-${ref.field}`}
                              className={styles.hint}
                            >
                              {ref.label ?? ref.field}
                            </p>
                          ))}
                          {entity.rule_names.slice(0, 3).map((name, idx) => (
                            <p
                              key={`${entity.name}-rule-${idx}-${name}`}
                              className={styles.hint}
                            >
                              rule · {name}
                            </p>
                          ))}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className={styles.split} style={{ marginBottom: '1.25rem' }}>
                    <div>
                      <h3 className={styles.panelTitle}>Screens ({referenceSystem.screens.length})</h3>
                      {referenceSystem.screens.length === 0 ? (
                        <p className={styles.empty}>No screens captured yet.</p>
                      ) : (
                        <ul className={styles.list}>
                          {referenceSystem.screens.map((screen) => (
                            <li key={screen.id} className={styles.item}>
                              <p className={styles.itemTitle}>{screen.name}</p>
                              <p className={styles.hint}>
                                <span className={styles.mono}>{screen.path}</span> · {screen.field_count}{' '}
                                fields · visited {screen.visit_count}×
                                {screen.primary_entity ? ` · ${screen.primary_entity}` : ''}
                              </p>
                              {screen.fields.slice(0, 6).map((field) => (
                                <p key={field.name} className={styles.hint}>
                                  {field.label ?? field.name}
                                  {field.entity ? ` → ${field.entity}` : ''}
                                  {field.required ? ' · required' : ''}
                                </p>
                              ))}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <h3 className={styles.panelTitle}>Site graph</h3>
                      {referenceSystem.site_graph_stats && (
                        <p className={styles.hint} style={{ marginBottom: '0.75rem' }}>
                          {referenceSystem.site_graph_stats.total_discovered ?? 0} links discovered ·{' '}
                          {referenceSystem.site_graph_stats.total_visited_links ?? 0} visited ·{' '}
                          {Math.round(
                            (referenceSystem.site_graph_stats.coverage_pct ?? 0) * 100,
                          )}
                          % internal coverage
                        </p>
                      )}
                      <SiteGraph investigationId={investigation.id} refreshKey={timeline.length} />
                    </div>
                    <div>
                      <h3 className={styles.panelTitle}>
                        Navigation ({referenceSystem.navigation.length})
                      </h3>
                      {referenceSystem.navigation.length === 0 ? (
                        <p className={styles.empty}>No cross-screen navigation observed.</p>
                      ) : (
                        <ol className={styles.timeline}>
                          {referenceSystem.navigation.slice(0, 8).map((edge, index) => (
                            <li key={`${edge.from_screen_id}-${edge.to_screen_id}-${index}`}>
                              <span className={styles.mono}>{edge.from_screen_id}</span> →{' '}
                              <span className={styles.mono}>{edge.to_screen_id}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  </div>
                  <h3 className={styles.panelTitle}>Flows ({referenceSystem.flows.length})</h3>
                  {referenceSystem.flows.length === 0 ? (
                    <p className={styles.empty}>No multi-step flows recorded.</p>
                  ) : (
                    <ul className={styles.list}>
                      {referenceSystem.flows.map((flow) => (
                        <li key={flow.name} className={styles.item}>
                          <p className={styles.itemTitle}>{flow.name}</p>
                          {flow.entity_names && flow.entity_names.length > 0 && (
                            <p className={styles.hint}>
                              entities · {flow.entity_names.join(', ')}
                            </p>
                          )}
                          <ol className={styles.timeline}>
                            {flow.steps.slice(0, 8).map((step) => (
                              <li key={`${flow.name}-${step.order}`}>
                                {step.screen_id ? (
                                  <span className={styles.mono}>[{step.screen_id}] </span>
                                ) : null}
                                {step.description}
                              </li>
                            ))}
                          </ol>
                        </li>
                      ))}
                    </ul>
                  )}
                  <h3 className={styles.panelTitle} style={{ marginTop: '1.25rem' }}>
                    Knowledge graph (screens → rules)
                  </h3>
                  {referenceSystem.rules_by_screen.length === 0 ? (
                    <p className={styles.empty}>No rule edges yet.</p>
                  ) : (
                    <ul className={styles.list}>
                      {referenceSystem.rules_by_screen.map((group) => (
                        <li key={`graph-${group.screen_id}`} className={styles.item}>
                          <p className={styles.itemTitle}>
                            <span className={styles.mono}>{group.screen_id}</span>
                          </p>
                          {group.verified.map((name) => (
                            <p key={`gv-${name}`} className={styles.hint}>
                              verified → {name}
                            </p>
                          ))}
                          {group.candidate.map((name) => (
                            <p key={`gc-${name}`} className={styles.hint}>
                              candidate → {name}
                            </p>
                          ))}
                        </li>
                      ))}
                    </ul>
                  )}
                  <h3 className={styles.panelTitle} style={{ marginTop: '1.25rem' }}>
                    Logic by screen
                  </h3>
                  {referenceSystem.rules_by_screen.length === 0 ? (
                    <p className={styles.empty}>No rules mapped to screens yet.</p>
                  ) : (
                    <ul className={styles.list}>
                      {referenceSystem.rules_by_screen.map((group) => (
                        <li key={group.screen_id} className={styles.item}>
                          <p className={styles.itemTitle}>
                            {group.screen_id === '_unscoped'
                              ? 'Unscoped rules'
                              : group.screen_id}
                          </p>
                          {group.verified.map((name) => (
                            <p key={`v-${name}`} className={styles.hint}>
                              verified · {name}
                            </p>
                          ))}
                          {group.candidate.map((name) => (
                            <p key={`c-${name}`} className={styles.hint}>
                              candidate · {name}
                            </p>
                          ))}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </section>
          )}

          {tab === 'ask' && (
            <section className={`${styles.panel} ${styles.fadeIn}`}>
              <h2 className={styles.panelTitle}>Ask about this application</h2>
              <p className={styles.hint} style={{ marginBottom: '0.85rem' }}>
                Answers only from discovered rules and linked evidence —
                refusals when evidence is missing.
              </p>
              <form
                className={styles.stack}
                onSubmit={async (event) => {
                  event.preventDefault();
                  setAsking(true);
                  try {
                    const result = await askQuestion(
                      investigation.id,
                      question,
                    );
                    setAnswer(result.answer);
                    setCitations(result.citations ?? []);
                  } catch (err) {
                    setAnswer(
                      err instanceof Error ? err.message : 'Question failed',
                    );
                    setCitations([]);
                  } finally {
                    setAsking(false);
                  }
                }}
              >
                <input
                  className={styles.input}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Why does this field appear?"
                />
                <button className={styles.btn} type="submit" disabled={asking}>
                  {asking ? 'Thinking…' : 'Ask'}
                </button>
              </form>
              {answer && <div className={styles.answer}>{answer}</div>}
              {citations.length > 0 && (
                <ul className={styles.list} style={{ marginTop: '0.85rem' }}>
                  {citations.map((citation, index) => (
                    <li
                      key={`${citation.rule_id ?? 'r'}-${citation.evidence_id ?? index}`}
                      className={styles.item}
                    >
                      <p className={styles.itemTitle}>
                        {citation.label ??
                          `Rule ${citation.rule_id?.slice(0, 8) ?? '—'}`}
                      </p>
                      <p className={styles.hint}>
                        confidence {citation.confidence ?? '—'}
                        {citation.evidence_id
                          ? ` · evidence ${citation.evidence_id.slice(0, 8)}`
                          : ''}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {tab === 'activity' && (
            <div
              className={`${styles.split} ${styles.splitTwo} ${styles.fadeIn}`}
            >
              <section className={styles.panel}>
                <h2 className={styles.panelTitle}>What the worker did</h2>
                {timeline.length === 0 ? (
                  <p className={styles.empty}>No activity yet.</p>
                ) : (
                  <ol className={styles.timeline}>
                    {timeline
                      .filter(
                        (event) =>
                          event.type !== 'settle' || timeline.length < 40,
                      )
                      .slice(-40)
                      .map((event) => (
                        <li key={event.id}>
                          <strong>{event.type}</strong> — {event.description}
                        </li>
                      ))}
                  </ol>
                )}
              </section>
              <section className={styles.panel}>
                <h2 className={styles.panelTitle}>Progress</h2>
                <ol className={styles.timeline}>
                  {transitions.map((transition) => (
                    <li key={transition.id}>
                      <strong>{formatStatus(transition.to_status)}</strong>
                      <span> via {transition.event.replace(/_/g, ' ')}</span>
                      {transition.reason ? ` — ${transition.reason}` : ''}
                    </li>
                  ))}
                </ol>
                <div style={{ marginTop: '1.25rem' }}>
                  <h3 className={styles.panelTitle}>Evidence inventory</h3>
                  {Object.keys(evidenceSummary).length === 0 ? (
                    <p className={styles.empty}>None yet.</p>
                  ) : (
                    <ul className={styles.timeline}>
                      {Object.entries(evidenceSummary).map(([type, count]) => (
                        <li key={type}>
                          <strong>{count}</strong> {type}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}
