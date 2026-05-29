import './globals.css';

export const metadata = {
  title: 'Home Finder & Optimizer | Find the Best Real Estate Deals',
  description: 'AI-powered home finder that analyzes every pricing variable to find the best deals in today\'s real estate market. Compare properties with exact raw valuations.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
