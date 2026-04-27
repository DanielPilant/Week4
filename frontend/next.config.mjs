/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_BRIDGE_WS: process.env.NEXT_PUBLIC_BRIDGE_WS ?? "ws://127.0.0.1:8765/ws",
  },
};

export default nextConfig;
