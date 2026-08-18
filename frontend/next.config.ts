import path from "node:path";
import type { NextConfig } from "next";

/**
 * Two deployment shapes are supported.
 *
 * 1. Server mode (default, and what the VPS uses). Next runs as a server and
 *    rewrites /api/* to the backend. Required when the frontend and backend sit
 *    behind separate domains — a static export cannot proxy anything, so
 *    eva-ai.dawrly.space/api/search would 404.
 *
 * 2. Static export (NEXT_OUTPUT=export). Emits frontend/out for the collapsed
 *    single-process image in the root Dockerfile, where FastAPI serves the SPA
 *    and the API from one origin and no rewrite is needed.
 *
 * BACKEND_URL points at the backend:
 *   local dev  -> http://127.0.0.1:8010
 *   compose    -> http://backend:8000  (service name on the compose network)
 *
 * WARNING: Next resolves `rewrites()` at BUILD time and serializes the result
 * into the build manifest. In Docker, BACKEND_URL must therefore be passed as a
 * build ARG — setting it only in the container environment is silently ignored
 * and the image keeps proxying to the local-dev default (ECONNREFUSED 8010).
 */
const isExport = process.env.NEXT_OUTPUT === "export";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  // standalone keeps the runtime image small (no full node_modules copy).
  output: isExport ? "export" : "standalone",
  outputFileTracingRoot: path.join(__dirname),

  async rewrites() {
    // A static export has no server, so rewrites cannot apply there.
    if (isExport) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
