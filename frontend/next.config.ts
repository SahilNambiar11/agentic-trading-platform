import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin Turbopack's root to the frontend directory so Next does not accidentally
  // treat the whole monorepo as the app root.
  turbopack: {
    root: projectRoot,
  },
};

export default nextConfig;
