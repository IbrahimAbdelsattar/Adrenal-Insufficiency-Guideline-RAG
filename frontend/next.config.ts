import type { NextConfig } from "next";

/**
 * Development: proxy /api/* to the FastAPI backend on :8000 so the browser sees a
 * single origin and CORS stays off the critical path (plan.md Structure Decision).
 *
 * Production: `output: "export"` emits a static bundle that FastAPI serves via
 * StaticFiles, collapsing the app to one deployable process.
 */
const isProd = process.env.NODE_ENV === "production";

// Override with BACKEND_URL if the default port is taken or blocked.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  ...(isProd ? { output: "export" as const } : {}),

  async rewrites() {
    if (isProd) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
