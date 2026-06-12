import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './app'

const container = document.getElementById('root')
if (!container) throw new Error('[channel-builder] mount node #root not found')

createRoot(container).render(<App />)
