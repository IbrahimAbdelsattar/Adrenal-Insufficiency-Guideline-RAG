import type { NextConfig } from "next";

/**
 * Development: proxy /api/* to the FastAPI backend on :8000 so the browser sees a
 * single origin and CORS stays off the critical path (plan.md Structure Decision).
 *
 * Production: `output: "export"` emits a static bundle that FastAPI serves via
 * StaticFiles, collapsing the app to one deployable process.
 */
const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  ...(isProd ? { output: "export" as const } : {}),

  async rewrites() {
    if (isProd) return [];
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
