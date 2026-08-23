'use client';

import { useState } from 'react';
import {
  beginAuthentication,
  markAuthenticationReady,
  resumeAfterAuthentication,
} from '../lib/api';
import type { Investigation, SessionPublic } from '../lib/types';
import styles from './auth-pause-panel.module.css';

interface AuthPausePanelProps {
  investigation: Investigation;
  session: SessionPublic | null | undefined;
  onUpdate: () => void;
}

function formatReason(reason: string | undefined): string {
  if (!reason) return 'Authentication required';
  return reason.replace(/_/g, ' ');
}

function targetLabel(investigation: Investigation): string {
  if (investigation.application_name) return investigation.application_name;
  try {
    const url = new URL(investigation.target_url);
    return url.pathname || investigation.target_url;
  } catch {
    return investigation.target_url;
  }
}

export function AuthPausePanel({ investigation, session, onUpdate }: AuthPausePanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sessionStatus = session?.session_status ?? 'auth_required';
  const isAuthenticating = sessionStatus === 'authenticating' || sessionStatus === 'auth_required';
  const humanReady = session?.human_ready ?? false;
  const authVerified = session?.has_persisted_storage && session.auth_state === 'authenticated';

  async function run(action: string, fn: () => Promise<unknown>) {
    setBusy(action);
    setError(null);
    try {
      await fn();
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(null);
    }
  }

  function startAuthFlow() {
    void run('begin', () => beginAuthentication(investigation.id));
  }

  return (
    <section className={styles.panel}>
      <header className={styles.header}>
        <span className={styles.badge}>Investigation Paused</span>
        <h2>Authentication is required</h2>
        <p className={styles.subtitle}>
          Log in only in the <strong>Chrome for Testing</strong> window opened by{' '}
          <code>browser:worker-headed</code>. A normal Chrome/Safari tab does not share cookies with
          the worker — do not use “open in new tab” for login.
        </p>
      </header>

      <dl className={styles.meta}>
        <div>
          <dt>Investigation</dt>
          <dd>{investigation.id.slice(0, 8)}…</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{formatReason(investigation.auth_pause?.reason)}</dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd>{targetLabel(investigation)}</dd>
        </div>
        <div>
          <dt>Browser session</dt>
          <dd>
            {authVerified
              ? 'Login verified by worker'
              : humanReady
                ? 'Waiting for worker to verify Chromium session…'
                : isAuthenticating
                  ? 'Log in in Chrome for Testing, then confirm below'
                  : 'Waiting for human'}
          </dd>
        </div>
      </dl>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        {sessionStatus !== 'authenticating' && sessionStatus !== 'authenticated' ? (
          <button type="button" className={styles.primary} disabled={!!busy} onClick={startAuthFlow}>
            I&apos;m ready to log in
          </button>
        ) : (
          <>
            <p className={styles.progress}>
              {authVerified
                ? '● Worker verified login and saved the session'
                : humanReady
                  ? 'Worker is checking the headed Chromium window and will auto-resume when the login wall is gone. Keep that window open.'
                  : 'Complete login in Chrome for Testing (SPID/password), leave the window open, then confirm below.'}
            </p>
            {!humanReady && (
              <button
                type="button"
                className={styles.secondary}
                disabled={!!busy}
                onClick={() => run('ready', () => markAuthenticationReady(investigation.id))}
              >
                I&apos;ve completed authentication
              </button>
            )}
            <button
              type="button"
              className={styles.primary}
              disabled={!!busy || !humanReady || !authVerified}
              title={
                !humanReady
                  ? 'Confirm authentication completion first'
                  : !authVerified
                    ? 'Worker has not verified login / saved storage yet'
                    : undefined
              }
              onClick={() => run('resume', () => resumeAfterAuthentication(investigation.id))}
            >
              Resume Investigation
            </button>
          </>
        )}
      </div>
    </section>
  );
}
