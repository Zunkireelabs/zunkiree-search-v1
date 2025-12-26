import React from 'react'
import ReactDOM from 'react-dom/client'
import { ZunkireeSearch } from './components/ZunkireeSearch'
import { EmbedMode, BorderRadiusStyle } from './types'

const WIDGET_ROOT_ID = 'zunkiree-search'

function initWidget() {
  // Get configuration from script tag
  const scriptTag = document.querySelector('script[data-site-id]')
  const siteId = scriptTag?.getAttribute('data-site-id') || 'test'
  const apiUrl = scriptTag?.getAttribute('data-api-url') || 'http://localhost:8000'
  const mode = (scriptTag?.getAttribute('data-mode') || 'hero') as EmbedMode
  const borderRadius = (scriptTag?.getAttribute('data-border-radius') || 'rounded') as BorderRadiusStyle

  // Find or create root element
  let rootElement = document.getElementById(WIDGET_ROOT_ID)

  // For floating mode, always create in body
  if (mode === 'floating') {
    if (!rootElement) {
      rootElement = document.createElement('div')
      rootElement.id = WIDGET_ROOT_ID
      document.body.appendChild(rootElement)
    }
  } else {
    // For hero/inline mode, use existing element or create one
    if (!rootElement) {
      rootElement = document.createElement('div')
      rootElement.id = WIDGET_ROOT_ID
      // Insert after the script tag or at end of body
      if (scriptTag && scriptTag.parentNode) {
        scriptTag.parentNode.insertBefore(rootElement, scriptTag.nextSibling)
      } else {
        document.body.appendChild(rootElement)
      }
    }
  }

  // Render widget
  const root = ReactDOM.createRoot(rootElement)
  root.render(
    <React.StrictMode>
      <ZunkireeSearch
        siteId={siteId}
        apiUrl={apiUrl}
        mode={mode}
        borderRadius={borderRadius}
      />
    </React.StrictMode>
  )
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initWidget)
} else {
  initWidget()
}
