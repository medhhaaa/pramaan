import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// No <StrictMode>: in dev it runs every effect twice, so every page view would call the
// API twice and show up twice in the audit log during the demo.
createRoot(document.getElementById('root')).render(<App />)
