'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { AuthPausePanel } from '../../../components/auth-pause-panel';
import { getInvestigationDetail, getTransitions } from '../../../lib/api';
import type { InvestigationDetail, InvestigationTransition } from '../../../lib/types';
import styles from '../../dashboard.module.css';

export default function InvestigationDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [transitions, setTransitions] = useState<InvestigationTransition[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!params.id) return;
    try {
      const [nextDetail, nextTransitions] = await Promise.all([
        getInvestigationDetail(params.id),
        getTransitions(params.id),
      ]);
      setDetail(nextDetail);
      setTransitions(nextTransitions);
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
        </dl>
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
    </main>
  );
}
