'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  AppShell,
  formatStatus,
  shortHost,
  statusBadgeClass,
} from '../../components/app-shell';
import { createInvestigation, listInvestigations } from '../../lib/api';
import type { Investigation } from '../../lib/types';
import styles from '../ui.module.css';

export default function InvestigationsPage() {
  const router = useRouter();
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [targetUrl, setTargetUrl] = useState('');
  const [featureScope, setFeatureScope] = useState('');
  const [roleScope, setRoleScope] = useState('');
  const [applicationName, setApplicationName] = useState('');
  const [policy, setPolicy] = useState('information_gain');
  const [investigationScope, setInvestigationScope] = useState('full_site');
  const [urlPrefix, setUrlPrefix] = useState('');
  const [spaMode, setSpaMode] = useState(false);

  const refresh = () =>
    listInvestigations()
      .then((items) =>
        setInvestigations(
          [...items].sort(
            (a, b) =>
              new Date(b.updated_at).getTime() -
              new Date(a.updated_at).getTime(),
          ),
        ),
      )
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Failed to load'),
      );

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);

  return (
    <AppShell>
      <header className={styles.fadeIn}>
        <h1 className={styles.pageTitle}>Investigations</h1>
        <p className={styles.lede}>
          Point WebTwin at an application. It explores, discovers behavioral
          rules, verifies them, and lets you ask evidence-backed questions.
        </p>
      </header>

      {error && <p className={styles.error}>{error}</p>}

      <section className={`${styles.panel} ${styles.fadeIn}`}>
        <h2 className={styles.panelTitle}>New investigation</h2>
        <form
          className={styles.stack}
          onSubmit={async (event) => {
            event.preventDefault();
            if (!targetUrl.trim()) {
              setError('Enter a target URL');
              return;
            }
            setBusy(true);
            setError(null);
            try {
              const scope = featureScope.trim();
              const role = roleScope.trim();
              const appName = applicationName.trim();
              const created = await createInvestigation({
                goal: scope
                  ? `Understand ${scope}${role ? ` as ${role}` : ''}`
                  : role
                    ? `Discover business logic as ${role}`
                    : policy === 'site_map'
                      ? 'Map site structure (deep crawl)'
                      : 'Discover business logic',
                target_url: targetUrl.trim(),
                feature_scope: scope || undefined,
                exploration_policy: policy,
                investigation_scope: investigationScope,
                url_prefix: urlPrefix.trim() || undefined,
                role_scope: role || undefined,
                application_name: appName || undefined,
                spa_mode: spaMode,
                environment: spaMode ? 'spa' : 'eval',
                goal_spec: scope
                  ? {
                      type: 'discover_business_logic',
                      target: targetUrl.trim(),
                      scope,
                      description: `Understand ${scope}`,
                    }
                  : null,
              });
              router.push(`/investigations/${created.id}`);
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Create failed');
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Application URL</span>
            <input
              className={styles.input}
              value={targetUrl}
              onChange={(event) => setTargetUrl(event.target.value)}
              placeholder="https://example.com/app"
              required
              autoFocus
            />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Focus (optional)</span>
            <input
              className={styles.input}
              value={featureScope}
              onChange={(event) => setFeatureScope(event.target.value)}
              placeholder="e.g. conditions, address, checkout"
            />
            <span className={styles.hint}>
              Biases exploration toward related fields and controls.
            </span>
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Role (optional)</span>
            <input
              className={styles.input}
              value={roleScope}
              onChange={(event) => setRoleScope(event.target.value)}
              placeholder="e.g. applicant, recruiter, admin"
            />
            <span className={styles.hint}>
              Separates system maps by persona. Same app + different roles merge into one catalog.
            </span>
          </label>

          <details className={styles.advanced}>
            <summary>Advanced options</summary>
            <div className={styles.stack} style={{ marginTop: '0.75rem' }}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Application name</span>
                <input
                  className={styles.input}
                  value={applicationName}
                  onChange={(event) => setApplicationName(event.target.value)}
                  placeholder="Optional — stabilizes cross-run identity"
                />
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Exploration mode</span>
                <select
                  className={styles.select}
                  value={policy}
                  onChange={(event) => setPolicy(event.target.value)}
                >
                  <option value="information_gain">
                    Form / behavior (information gain)
                  </option>
                  <option value="site_map">Site map (deep crawl)</option>
                  <option value="first_unexplored">First unexplored</option>
                  <option value="random">Random</option>
                </select>
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Investigation scope</span>
                <select
                  className={styles.select}
                  value={investigationScope}
                  onChange={(event) => setInvestigationScope(event.target.value)}
                >
                  <option value="full_site">Full site</option>
                  <option value="catalog">Catalog</option>
                  <option value="product">Product</option>
                  <option value="checkout">Checkout</option>
                  <option value="account">Account</option>
                  <option value="custom">Custom</option>
                </select>
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>URL prefix filter (optional)</span>
                <input
                  className={styles.input}
                  value={urlPrefix}
                  onChange={(event) => setUrlPrefix(event.target.value)}
                  placeholder="/product-category/"
                />
              </label>
              <label className={styles.check}>
                <input
                  type="checkbox"
                  checked={spaMode}
                  onChange={(event) => setSpaMode(event.target.checked)}
                />
                Single-page app mode (soft navigation)
              </label>
            </div>
          </details>

          <div className={styles.row}>
            <button className={styles.btn} type="submit" disabled={busy}>
              {busy ? 'Starting…' : 'Start investigation'}
            </button>
          </div>
        </form>
      </section>

      <section style={{ marginTop: '1.5rem' }} className={styles.fadeIn}>
        <h2 className={styles.panelTitle}>Recent</h2>
        {investigations.length === 0 ? (
          <p className={styles.empty}>
            No investigations yet. Start one above.
          </p>
        ) : (
          <ul className={styles.list}>
            {investigations.map((investigation) => (
              <li key={investigation.id}>
                <Link
                  href={`/investigations/${investigation.id}`}
                  className={styles.item}
                >
                  <div className={styles.itemTop}>
                    <span className={statusBadgeClass(investigation.status)}>
                      {formatStatus(investigation.status)}
                    </span>
                    <span className={`${styles.mono} ${styles.empty}`}>
                      {investigation.id.slice(0, 8)}
                    </span>
                  </div>
                  <p className={styles.itemTitle}>{investigation.goal}</p>
                  <p className={styles.itemMeta}>
                    {shortHost(investigation.target_url)}
                    {investigation.role_scope ? ` · ${investigation.role_scope}` : ''}
                    {investigation.application_key
                      ? ` · ${investigation.application_key}`
                      : ''}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </AppShell>
  );
}
