'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  beginAuthentication,
  getAuthForm,
  markAuthenticationReady,
  resumeAfterAuthentication,
  submitAuthForm,
} from '../lib/api';
import type {
  AuthFormField,
  AuthFormSchema,
  Investigation,
  SessionPublic,
} from '../lib/types';
import styles from '../app/ui.module.css';

interface AuthPausePanelProps {
  investigation: Investigation;
  session: SessionPublic | null | undefined;
  onUpdate: () => void;
}

function fieldInputType(field: AuthFormField): string {
  if (field.is_secret || field.input_type === 'password') return 'password';
  if (field.input_type === 'email') return 'email';
  if (field.input_type === 'tel') return 'tel';
  if (field.input_type === 'number') return 'number';
  return 'text';
}

export function AuthPausePanel({ investigation, session, onUpdate }: AuthPausePanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [form, setForm] = useState<AuthFormSchema | null>(
    investigation.auth_pause?.form ?? null,
  );
  const [values, setValues] = useState<Record<string, string>>({});

  const sessionStatus = session?.session_status ?? 'auth_required';
  const started = sessionStatus === 'authenticating' || sessionStatus === 'authenticated';
  const humanReady = session?.human_ready ?? false;
  const authVerified = Boolean(session?.has_persisted_storage && session.auth_state === 'authenticated');
  const hasDynamicForm = Boolean(form?.fields?.length);

  useEffect(() => {
    setForm(investigation.auth_pause?.form ?? null);
  }, [investigation.auth_pause?.form]);

  useEffect(() => {
    let cancelled = false;
    async function loadForm() {
      try {
        const payload = await getAuthForm(investigation.id);
        if (!cancelled && payload.form?.fields?.length) {
          setForm(payload.form);
        }
      } catch {
        // Worker may not have published the schema yet.
      }
    }
    loadForm();
    const timer = setInterval(loadForm, 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [investigation.id]);

  const title = useMemo(() => {
    if (form?.page_kind === 'register') return 'Registration form detected';
    if (form?.page_kind === 'mfa') return 'Verification form detected';
    if (hasDynamicForm) return 'Login form detected';
    return 'Login required';
  }, [form?.page_kind, hasDynamicForm]);

  async function run(action: string, fn: () => Promise<unknown>) {
    setBusy(action);
    setError(null);
    setNote(null);
    try {
      await fn();
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(null);
    }
  }

  async function submitForm(useDummy: boolean) {
    setBusy(useDummy ? 'dummy' : 'submit');
    setError(null);
    setNote(null);
    try {
      if (!started) {
        await beginAuthentication(investigation.id);
      }
      await submitAuthForm(investigation.id, {
        values: useDummy ? {} : values,
        use_dummy: useDummy,
      });
      setNote(
        useDummy
          ? 'Dummy values sent to the worker — watch Chrome for Testing fill the form.'
          : 'Credentials sent to the worker — watch Chrome for Testing fill the form.',
      );
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submit failed');
    } finally {
      setBusy(null);
    }
  }

  const step = !started ? 1 : !humanReady ? 2 : authVerified ? 3 : 2;

  return (
    <section className={styles.panel} style={{ borderColor: '#e0b35c' }}>
      <h2 className={styles.panelTitle}>{title}</h2>
      <p className={styles.hint} style={{ marginBottom: '1rem' }}>
        {hasDynamicForm
          ? 'Fill the mirrored form below (dummy or real). The headed worker injects values into the live site. SSO/CAPTCHA may still need the Chrome window.'
          : 'Waiting for the worker to detect login/register fields, or sign in directly in Chrome for Testing.'}
      </p>

      {hasDynamicForm && (
        <div style={{ marginBottom: '1rem' }}>
          {form?.notes?.map((item) => (
            <p key={item} className={styles.hint} style={{ marginBottom: '0.35rem' }}>
              {item}
            </p>
          ))}
          <div
            style={{
              display: 'grid',
              gap: '0.75rem',
              marginTop: '0.75rem',
              maxWidth: '28rem',
            }}
          >
            {form?.fields.map((field) => (
              <label key={field.key} style={{ display: 'grid', gap: '0.25rem' }}>
                <span className={styles.fieldLabel}>
                  {field.label}
                  {field.required ? ' *' : ''}
                </span>
                {field.input_type === 'select' && field.options?.length ? (
                  <select
                    className={styles.input}
                    value={values[field.key] ?? ''}
                    onChange={(event) =>
                      setValues((prev) => ({ ...prev, [field.key]: event.target.value }))
                    }
                  >
                    <option value="">Select…</option>
                    {field.options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className={styles.input}
                    type={fieldInputType(field)}
                    autoComplete={field.is_secret ? 'current-password' : 'off'}
                    placeholder={field.placeholder ?? undefined}
                    value={values[field.key] ?? ''}
                    onChange={(event) =>
                      setValues((prev) => ({ ...prev, [field.key]: event.target.value }))
                    }
                  />
                )}
              </label>
            ))}
          </div>
          <div className={styles.row} style={{ marginTop: '0.85rem' }}>
            <button
              type="button"
              className={styles.btn}
              disabled={!!busy}
              onClick={() => submitForm(false)}
            >
              {busy === 'submit' ? 'Sending…' : form?.submit_label || 'Send to browser'}
            </button>
            {form?.supports_dummy && (
              <button
                type="button"
                className={styles.btnSecondary}
                disabled={!!busy}
                onClick={() => submitForm(true)}
              >
                {busy === 'dummy' ? 'Sending…' : 'Use dummy values'}
              </button>
            )}
          </div>
        </div>
      )}

      <ol className={styles.timeline} style={{ marginBottom: '1rem' }}>
        <li>
          <strong>1. Ready</strong> — tell WebTwin you’re about to log in
          {step > 1 ? ' ✓' : ''}
        </li>
        <li>
          <strong>2. Sign in</strong> — dashboard form and/or Chrome for Testing
          {humanReady ? ' ✓' : ''}
        </li>
        <li>
          <strong>3. Continue</strong> — worker verifies cookies
          {authVerified ? ' ✓' : ''}
        </li>
      </ol>

      {error && <p className={styles.error}>{error}</p>}
      {note && <p className={styles.hint}>{note}</p>}

      <div className={styles.row}>
        {!started ? (
          <button
            type="button"
            className={styles.btn}
            disabled={!!busy}
            onClick={() => run('begin', () => beginAuthentication(investigation.id))}
          >
            I’m ready to log in
          </button>
        ) : (
          <>
            {!humanReady && (
              <button
                type="button"
                className={styles.btnSecondary}
                disabled={!!busy}
                onClick={() => run('ready', () => markAuthenticationReady(investigation.id))}
              >
                I’ve finished logging in
              </button>
            )}
            <button
              type="button"
              className={styles.btn}
              disabled={!!busy || !humanReady || !authVerified}
              onClick={() => run('resume', () => resumeAfterAuthentication(investigation.id))}
            >
              {authVerified ? 'Continue investigation' : 'Waiting for verification…'}
            </button>
          </>
        )}
      </div>
      {humanReady && !authVerified && (
        <p className={styles.hint} style={{ marginTop: '0.75rem' }}>
          Keep Chrome for Testing open. The worker will detect when the login wall is gone.
        </p>
      )}
    </section>
  );
}
