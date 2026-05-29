/** @type {import('next').NextConfig} */
// Backend origin: set BACKEND_URL in Vercel (e.g. https://home-finder-api.onrender.com).
// Falls back to local dev backend on :8001.
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
