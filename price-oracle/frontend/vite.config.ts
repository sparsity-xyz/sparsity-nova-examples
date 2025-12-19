import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Define environment variables
  define: {
    'import.meta.env.VITE_CONTRACT_ADDRESS': JSON.stringify(
      process.env.VITE_CONTRACT_ADDRESS || '0x00061d46a5d05f1abdec7ea05894e602083682e9'
    ),
    'import.meta.env.VITE_CHAIN_ID': JSON.stringify(
      process.env.VITE_CHAIN_ID || '84532'
    ),
    'import.meta.env.VITE_CHAIN_NAME': JSON.stringify(
      process.env.VITE_CHAIN_NAME || 'Base Sepolia'
    ),
    'import.meta.env.VITE_RPC_URL': JSON.stringify(
      process.env.VITE_RPC_URL || 'https://sepolia.base.org'
    ),
    'import.meta.env.VITE_EXPLORER_URL': JSON.stringify(
      process.env.VITE_EXPLORER_URL || 'https://sepolia.basescan.org'
    ),
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      }
    }
  }
})
