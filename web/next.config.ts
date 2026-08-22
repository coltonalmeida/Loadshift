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
  // /api/* is proxied to loadshift-api by app/api/[...path]/route.ts, not by a
  // rewrite: rewrites bake into the build, and the API's private hostname must
  // be read at request time so the two services can deploy in any order.
};

export default nextConfig;
