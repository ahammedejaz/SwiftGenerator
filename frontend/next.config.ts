import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // This repository standardises on 127.0.0.1 rather than localhost, because the backend
  // binds 127.0.0.1 and a dual-stack machine resolves localhost to ::1 first (gotcha 21).
  // `next dev` treats any host it was not started on as a cross-origin dev host and blocks
  // its own /_next/hmr resources — and with HMR blocked the client never hydrates, so
  // Create Message sits on "Loading configured messages…" for ever and never calls the API.
  // Naming both spellings is what makes the address the documentation gives actually work.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Isolated Playwright runs use a separate build directory so they never adopt or stop
  // an operator's development server in this checkout.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
