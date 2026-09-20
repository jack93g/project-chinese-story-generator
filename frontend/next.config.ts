import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a fully static site to out/ so it can be hosted on GitHub Pages.
  output: "export",
};

export default nextConfig;
