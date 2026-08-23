'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { createInvestigation, listInvestigations } from '../../lib/api';
import type { Investigation } from '../../lib/types';
import styles from '../dashboard.module.css';

export default function InvestigationsPage() {
  const router = useRouter();
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [goal, setGoal] = useState('Discover business logic');
  const [targetUrl, setTargetUrl] = useState('file:///tmp/fixture.html');
  const [policy, setPolicy] = useState('information_gain');

  const refresh = () =>
    listInvestigations()
      .then(setInvestigations)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'));

  useEffect(() => {
    refresh();
  }, []);

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <div>
          <p className={styles.kicker}>WebTwin</p>
          <h1>Investigations</h1>
        </div>
      </header>

      {error && <p className={styles.error}>{error}</p>}

      <section className={styles.section}>
        <h2>Start investigation</h2>
        <form
          className={styles.form}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              const created = await createInvestigation({
                goal: `${goal} [${policy}]`,
                target_url: targetUrl,
                feature_scope: policy,
              });
              router.push(`/investigations/${created.id}`);
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Create failed');
            }
          }}
        >
          <input
            className={styles.input}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="Goal"
          />
          <input
            className={styles.input}
            value={targetUrl}
            onChange={(event) => setTargetUrl(event.target.value)}
            placeholder="Target URL"
          />
          <select
            className={styles.input}
            value={policy}
            onChange={(event) => setPolicy(event.target.value)}
          >
            <option value="random">random</option>
            <option value="first_unexplored">first_unexplored</option>
            <option value="information_gain">information_gain</option>
            <option value="llm">llm</option>
          </select>
          <button className={styles.button} type="submit">
            Create
          </button>
        </form>
        <p className={styles.empty}>
          Browser worker still runs via Nx (`browser:investigate` / evaluation targets). Policy is
          recorded on the goal for operator tracking.
        </p>
      </section>

      {investigations.length === 0 ? (
        <p className={styles.empty}>No investigations yet.</p>
      ) : (
        <ul className={styles.list}>
          {investigations.map((investigation) => (
            <li key={investigation.id}>
              <Link href={`/investigations/${investigation.id}`} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.status}>{investigation.status}</span>
                  <span className={styles.id}>{investigation.id.slice(0, 8)}…</span>
                </div>
                <p className={styles.goal}>{investigation.goal}</p>
                <p className={styles.target}>{investigation.target_url}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
