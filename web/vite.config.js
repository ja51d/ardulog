import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// GitHub Pages serves the site from /uav-log-viewer/ (the repo name), so
// asset URLs need that prefix in the build. Locally (npm run dev) we keep
// the default "/" base.
const isBuild = process.env.NODE_ENV === 'production' || process.argv.includes('build')

export default defineConfig({
  plugins: [vue()],
  base: isBuild ? '/uav-log-viewer/' : '/',
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
