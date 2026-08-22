import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    // Sections used to be standalone routes; keep old links working.
    return [
      { source: "/schedule", destination: "/#schedule", permanent: false },
      { source: "/data", destination: "/#data", permanent: false },
      { source: "/method", destination: "/#method", permanent: false },
    ];
  },
};

export default nextConfig;
