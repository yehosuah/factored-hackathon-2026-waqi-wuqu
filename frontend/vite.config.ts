import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
const apiTarget = process.env.FACTORED_API_TARGET || 'http://127.0.0.1:8000'
const target = new URL(apiTarget)
if (
  target.protocol !== 'http:' ||
  !['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname) ||
  target.username ||
  target.password ||
  target.pathname !== '/' ||
  target.search ||
  target.hash
) {
  throw new Error('FACTORED_API_TARGET must be a plain HTTP loopback origin')
}
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: apiTarget,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
