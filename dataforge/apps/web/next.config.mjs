/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const api = process.env.DATAFORGE_API_URL || "http://localhost:8000";
    return [{ source: "/v1/:path*", destination: `${api}/v1/:path*` }];
  },
};

export default nextConfig;
