import Link from 'next/link';
import styles from './dashboard.module.css';

export default function HomePage() {
  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <div>
          <p className={styles.kicker}>WebTwin</p>
          <h1>Evidence-grounded investigation</h1>
        </div>
      </header>
      <p className={styles.target}>
        Observe applications, discover behavioral rules, and verify them experimentally.
      </p>
      <Link href="/investigations" className={styles.back}>
        View investigations →
      </Link>
    </main>
  );
}
