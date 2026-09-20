/** @type {import('next').NextConfig} */
const nextConfig = {
  // eslint-config-next@16 + eslint@9 hits a circular JSON bug with Next 15.2 lint step
  eslint: {
    ignoreDuringBuilds: true,
  },
};

module.exports = nextConfig;
