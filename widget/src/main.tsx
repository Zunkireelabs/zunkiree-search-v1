import React from 'react'
import ReactDOM from 'react-dom/client'
import { Widget } from './components/Widget'

function initWidget() {
  // Get configuration from script tag
  const scriptTag = document.querySelector('script[data-site-id]')
  const siteId = scriptTag?.getAttribute('data-site-id') || 'test'
  const apiUrl = scriptTag?.getAttribute('data-api-url') || 'http://localhost:8000'

  // Create root element for widget (always append to body for floating)
  let rootElement = document.getElementById('zunkiree-widget-root')
  if (!rootElement) {
    rootElement = document.createElement('div')
    rootElement.id = 'zunkiree-widget-root'
    document.body.appendChild(rootElement)
  }

  // Render widget
  const root = ReactDOM.createRoot(rootElement)
  root.render(
    <React.StrictMode>
      <Widget siteId={siteId} apiUrl={apiUrl} />
    </React.StrictMode>
  )
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initWidget)
} else {
  initWidget()
}
