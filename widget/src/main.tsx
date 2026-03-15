import React from 'react'
import ReactDOM from 'react-dom/client'
import { Widget } from './components/Widget'

function initWidget() {
  // Get configuration from script tag
  const scriptTag = document.querySelector('script[data-site-id]')
  const siteId = scriptTag?.getAttribute('data-site-id') || 'test'
  const apiUrl = scriptTag?.getAttribute('data-api-url') || 'http://localhost:8000'

  // Create host element
  let hostElement = document.getElementById('zunkiree-widget-root')
  if (!hostElement) {
    hostElement = document.createElement('div')
    hostElement.id = 'zunkiree-widget-root'
    document.body.appendChild(hostElement)
  }

  // Attach Shadow DOM for complete style isolation
  const shadow = hostElement.attachShadow({ mode: 'open' })

  // Create React mount point inside shadow
  const reactRoot = document.createElement('div')
  reactRoot.id = 'zk-shadow-root'
  shadow.appendChild(reactRoot)

  // Render widget inside shadow DOM
  const root = ReactDOM.createRoot(reactRoot)
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
