import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(async ({ mode }) => {
  const isDev = mode === 'development'
  
  // Try to import frappe-ui plugin
  let frappeui = null
  try {
    const module = await import('frappe-ui/vite')
    frappeui = module.default
  } catch (e) {
    console.warn('frappe-ui not found, using basic config')
  }

  const plugins = [vue()]
  
  if (frappeui) {
    plugins.unshift(
      frappeui({
        frappeProxy: true,
        lucideIcons: true,
        jinjaBootData: true,
        buildConfig: {
          indexHtmlPath: '../construction_management/www/construction.html',
          emptyOutDir: true,
          sourcemap: true,
        },
      })
    )
  }

  return {
    plugins,
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 8080,
      proxy: {
        '^/(api|app|assets|files)': {
          target: 'http://skada.localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    build: {
      outDir: '../construction_management/public/frontend',
      emptyOutDir: true,
      sourcemap: true,
      rollupOptions: {
        input: {
          main: path.resolve(__dirname, 'index.html'),
        },
      },
    },
    optimizeDeps: {
      include: ['feather-icons', 'showdown'],
    },
  }
})
