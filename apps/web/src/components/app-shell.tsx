import Link from 'next/link';
import type { ReactNode } from 'react';
import styles from '../app/ui.module.css';

export function AppShell({
  children,
  showNav = true,
}: {
  children: ReactNode;
  showNav?: boolean;
}) {
  return (
    <div className={styles.shell}>
      {showNav && (
        <nav className={styles.nav}>
          <Link href="/investigations" className={styles.brand}>
            <span className={styles.brandMark}>WebTwin</span>
            <span className={styles.brandTag}>application investigation</span>
          </Link>
          <Link href="/investigations" className={styles.navLink}>
            Investigations
          </Link>
        </nav>
      )}
      {children}
    </div>
  );
}

export function statusBadgeClass(status: string): string {
  if (status === 'completed' || status === 'verified' || status === 'authenticated') {
    return `${styles.badge} ${styles.badgeOk}`;
  }
  if (
    status === 'failed' ||
    status === 'cancelled' ||
    status === 'contradicted' ||
    status === 'blocked'
  ) {
    return `${styles.badge} ${styles.badgeDanger}`;
  }
  if (status === 'auth_required' || status === 'candidate' || status === 'under_verification') {
    return `${styles.badge} ${styles.badgeWarn}`;
  }
  if (
    status === 'exploring' ||
    status === 'observing' ||
    status === 'verifying' ||
    status === 'generating_rule' ||
    status === 'initializing' ||
    status === 'auth_check' ||
    status === 'in_progress'
  ) {
    return `${styles.badge} ${styles.badgeActive}`;
  }
  return `${styles.badge} ${styles.badgeNeutral}`;
}

export function formatStatus(status: string): string {
  return status.replace(/_/g, ' ');
}

export function shortHost(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname + (parsed.pathname === '/' ? '' : parsed.pathname);
  } catch {
    return url;
  }
}
