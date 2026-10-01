/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy the API through Next so the backend's SameSite=Lax session cookie stays
  // same-origin. Google's redirect URI is therefore http://localhost:3000/api/auth/google/callback.
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};
export default nextConfig;
