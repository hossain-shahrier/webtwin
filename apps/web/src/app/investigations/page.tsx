'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { listInvestigations } from '../../lib/api';
import type { Investigation } from '../../lib/types';
import styles from '../dashboard.module.css';

export default function InvestigationsPage() {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listInvestigations()
      .then(setInvestigations)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'));
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

      {investigations.length === 0 ? (
        <p className={styles.empty}>No investigations yet. Start one with the browser agent.</p>
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
