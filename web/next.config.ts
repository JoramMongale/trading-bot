import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @duckdb/node-api is a native addon — never bundle it into the server.
  serverExternalPackages: ["@duckdb/node-api"],
};

export default nextConfig;
