/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // In production (Railway), set NEXT_PUBLIC_API_URL to your backend Railway service URL.
    // e.g. https://dataforge-backend.up.railway.app
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`
      }
    ]
  }
};

export default nextConfig;
