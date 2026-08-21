import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Isolated Playwright runs use a separate build directory so they never adopt or stop
  // an operator's development server in this checkout.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
