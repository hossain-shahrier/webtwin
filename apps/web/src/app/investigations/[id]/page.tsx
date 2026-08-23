'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { AuthPausePanel } from '../../../components/auth-pause-panel';
import {
  askQuestion,
  getEvidence,
  getInvestigationDetail,
  getMetrics,
  getRules,
  getTimeline,
  getTransitions,
  restartFailedInvestigation,
  resumeFailedInvestigation,
} from '../../../lib/api';
import type {
  BusinessRule,
  EvaluationRun,
  Evidence,
  InvestigationDetail,
  InvestigationTransition,
  TimelineEvent,
} from '../../../lib/types';
import styles from '../../dashboard.module.css';

export default function InvestigationDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [transitions, setTransitions] = useState<InvestigationTransition[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [rules, setRules] = useState<BusinessRule[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [metrics, setMetrics] = useState<EvaluationRun[]>([]);
  const [question, setQuestion] = useState('Why does this field appear?');
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<
    Array<{ rule_id?: string; evidence_id?: string; confidence?: number }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!params.id) return;
    try {
      const [nextDetail, nextTransitions, nextTimeline, nextRules, nextEvidence, nextMetrics] =
        await Promise.all([
          getInvestigationDetail(params.id),
          getTransitions(params.id),
          getTimeline(params.id),
          getRules(params.id),
          getEvidence(params.id),
          getMetrics(params.id),
        ]);
      setDetail(nextDetail);
      setTransitions(nextTransitions);
      setTimeline(nextTimeline);
      setRules(nextRules);
      setEvidence(nextEvidence);
      setMetrics(nextMetrics);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load investigation');
    }
  }, [params.id]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!detail) {
    return (
      <main className={styles.page}>
        <p>{error ?? 'Loading investigation…'}</p>
      </main>
    );
  }

  const { investigation, session } = detail;
  const latestMetrics = metrics[metrics.length - 1];

  return (
    <main className={styles.page}>
      <Link href="/investigations" className={styles.back}>
        ← All investigations
      </Link>

      <header className={styles.topbar}>
        <div>
          <p className={styles.kicker}>Investigation</p>
          <h1>{investigation.id.slice(0, 8)}…</h1>
        </div>
        <span className={styles.statusPill}>{investigation.status}</span>
      </header>

      {error && <p className={styles.error}>{error}</p>}

      {investigation.status === 'auth_required' && (
        <AuthPausePanel investigation={investigation} session={session} onUpdate={refresh} />
      )}

      {investigation.status === 'failed' && (
        <section className={styles.section}>
          <h2>Recovery</h2>
          <p className={styles.empty}>{investigation.failure_reason ?? 'Investigation failed'}</p>
          {investigation.checkpoint ? (
            <button
              className={styles.button}
              type="button"
              onClick={async () => {
                try {
                  await resumeFailedInvestigation(investigation.id);
                  await refresh();
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Resume failed');
                }
              }}
            >
              Resume from checkpoint
            </button>
          ) : (
            <>
              <p className={styles.empty}>
                Failed before a checkpoint was saved (often during early auth). Re-queue so the
                headed worker can claim it again.
              </p>
              <button
                className={styles.button}
                type="button"
                onClick={async () => {
                  try {
                    await restartFailedInvestigation(investigation.id);
                    await refresh();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Restart failed');
                  }
                }}
              >
                Re-queue investigation
              </button>
            </>
          )}
        </section>
      )}

      <section className={styles.section}>
        <h2>Details</h2>
        <dl className={styles.detailGrid}>
          <div>
            <dt>Goal</dt>
            <dd>{investigation.goal}</dd>
          </div>
          <div>
            <dt>Target URL</dt>
            <dd>{investigation.target_url}</dd>
          </div>
          <div>
            <dt>Session status</dt>
            <dd>{session?.session_status ?? 'unknown'}</dd>
          </div>
          <div>
            <dt>SPA mode</dt>
            <dd>{investigation.spa_mode ? 'enabled' : 'off'}</dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{investigation.environment ?? '—'}</dd>
          </div>
        </dl>
      </section>

      {latestMetrics && (
        <section className={styles.section}>
          <h2>Metrics</h2>
          <dl className={styles.detailGrid}>
            <div>
              <dt>Policy</dt>
              <dd>{latestMetrics.policy}</dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>{latestMetrics.exploration_coverage}</dd>
            </div>
            <div>
              <dt>Rules / action</dt>
              <dd>{latestMetrics.rules_per_action}</dd>
            </div>
            <div>
              <dt>Safety violations</dt>
              <dd>{latestMetrics.safety_violations}</dd>
            </div>
            <div>
              <dt>Settle timeouts</dt>
              <dd>{latestMetrics.settle_timeouts ?? 0}</dd>
            </div>
            <div>
              <dt>Soft-nav success</dt>
              <dd>
                {latestMetrics.soft_nav_success_rate != null
                  ? latestMetrics.soft_nav_success_rate
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>Routes seen</dt>
              <dd>{latestMetrics.routes_seen ?? 0}</dd>
            </div>
          </dl>
        </section>
      )}

      <section className={styles.section}>
        <h2>Rules</h2>
        {rules.length === 0 ? (
          <p className={styles.empty}>No rules yet.</p>
        ) : (
          <ul className={styles.list}>
            {rules.map((rule) => (
              <li key={rule.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.status}>{rule.status}</span>
                  <span className={styles.id}>{rule.confidence}</span>
                </div>
                <p className={styles.goal}>{rule.name}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <h2>Evidence</h2>
        {evidence.length === 0 ? (
          <p className={styles.empty}>No evidence recorded.</p>
        ) : (
          <ul className={styles.list}>
            {evidence.map((item) => (
              <li key={item.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.status}>{item.type}</span>
                  <span className={styles.id}>{item.sensitivity}</span>
                </div>
                <p className={styles.target}>{item.content_hash?.slice(0, 16)}…</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <h2>Timeline</h2>
        <ol className={styles.timeline}>
          {timeline.map((event) => (
            <li key={event.id}>
              <code>{event.type}</code>
              <span> — {event.description}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.section}>
        <h2>Transition history</h2>
        <ol className={styles.timeline}>
          {transitions.map((transition) => (
            <li key={transition.id}>
              <code>{transition.from_status}</code>
              <span> → </span>
              <code>{transition.to_status}</code>
              <span className={styles.event}> ({transition.event})</span>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.section}>
        <h2>Ask</h2>
        <form
          className={styles.form}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              const result = await askQuestion(investigation.id, question);
              setAnswer(result.answer);
              setCitations(result.citations ?? []);
            } catch (err) {
              setAnswer(err instanceof Error ? err.message : 'Question failed');
              setCitations([]);
            }
          }}
        >
          <input
            className={styles.input}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button className={styles.button} type="submit">
            Ask
          </button>
        </form>
        {answer && <p className={styles.empty}>{answer}</p>}
        {citations.length > 0 && (
          <ul className={styles.list}>
            {citations.map((citation, index) => (
              <li key={`${citation.rule_id ?? 'r'}-${citation.evidence_id ?? index}`} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.status}>citation</span>
                  <span className={styles.id}>{citation.confidence ?? '—'}</span>
                </div>
                <p className={styles.target}>
                  rule={citation.rule_id?.slice(0, 8) ?? '—'} evidence=
                  {citation.evidence_id?.slice(0, 8) ?? '—'}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
