/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // On Railway, set NEXT_PUBLIC_API_URL to your backend service URL
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
