const path = require('path');
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Next.js 15+: moved from experimental.serverComponentsExternalPackages
  serverExternalPackages: ['@ai-sdk/openai'],
  eslint: {
    // Disable ESLint during production builds inside Docker where devDependencies are omitted
    ignoreDuringBuilds: true,
  },
  images: {
    domains: ['localhost'],
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1',
  },
  webpack(config) {
    config.module.rules.push({
      test: /\.svg$/,
      use: ['@svgr/webpack'],
    });
    // Ensure path alias '@' resolves to 'src'
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@': path.resolve(__dirname, 'src'),
    };
    return config;
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL || 'http://localhost:8000/api/v1'}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;