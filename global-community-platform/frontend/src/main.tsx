import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import App from './App'
import { installAudioUnlock } from './context/notificationAlerts'
import { registerServiceWorker } from './services/push'
import './styles.css'

installAudioUnlock()
// Makes the app installable and receives push notifications. Production builds only,
// so the dev server's hot reload is never served by a stale worker.
if (import.meta.env.PROD) window.addEventListener('load', () => { void registerServiceWorker() })
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false } } })
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
