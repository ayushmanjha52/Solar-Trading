/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // Route handlers read the recorded week and the static copies with fs at
    // runtime; make sure serverless bundles (Vercel) include them.
    outputFileTracingIncludes: {
      "/**/*": ["./data/**/*"],
    },
  },
};

export default nextConfig;
