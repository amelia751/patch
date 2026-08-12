import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cloud Run serves the traced server output, not `next start` over the
  // full `node_modules` tree. Without this the image has no `server.js`.
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
    ],
  },
};

export default nextConfig;
