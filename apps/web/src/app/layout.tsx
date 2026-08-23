import './global.css';

export const metadata = {
  title: 'WebTwin',
  description: 'Evidence-grounded autonomous software investigation',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
