import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { MOCK } from './lib/api'

// See MockBanner.tsx: same VITE_MOCK/mode build-time flag, so this prefix (like the banner) is
// gone entirely from a real `npm run build`.
if (MOCK) document.title = `[MOCK] ${document.title}`

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
