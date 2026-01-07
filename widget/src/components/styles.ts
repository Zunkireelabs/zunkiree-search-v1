export const styles = (primaryColor: string) => `
  /* Widget Container */
  .zk-widget {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 9999;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    pointer-events: none;
  }

  .zk-widget > * {
    pointer-events: auto;
  }

  /* Messages Panel */
  .zk-messages-panel {
    width: 100%;
    max-width: 800px;
    max-height: 400px;
    background: white;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: zk-slide-up 0.25s ease-out;
    margin: 0 16px;
  }

  @keyframes zk-slide-up {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .zk-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid #e5e7eb;
    background: #fafafa;
  }

  .zk-panel-title {
    font-weight: 600;
    font-size: 14px;
    color: #374151;
  }

  .zk-close {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    transition: background 0.15s, color 0.15s;
  }

  .zk-close:hover {
    background: #f3f4f6;
    color: #374151;
  }

  .zk-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: 320px;
  }

  .zk-message {
    max-width: 85%;
    animation: zk-fade-in 0.2s ease;
  }

  @keyframes zk-fade-in {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .zk-message-user {
    align-self: flex-end;
  }

  .zk-message-assistant {
    align-self: flex-start;
  }

  .zk-message-content {
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.5;
  }

  .zk-message-user .zk-message-content {
    background: ${primaryColor};
    color: white;
    border-bottom-right-radius: 4px;
  }

  .zk-message-assistant .zk-message-content {
    background: #f3f4f6;
    color: #1f2937;
    border-bottom-left-radius: 4px;
  }

  .zk-typing {
    display: flex;
    gap: 4px;
    padding: 12px 14px;
  }

  .zk-typing span {
    width: 8px;
    height: 8px;
    background: #9ca3af;
    border-radius: 50%;
    animation: zk-bounce 1.4s infinite ease-in-out both;
  }

  .zk-typing span:nth-child(1) { animation-delay: -0.32s; }
  .zk-typing span:nth-child(2) { animation-delay: -0.16s; }

  @keyframes zk-bounce {
    0%, 80%, 100% { transform: scale(0); }
    40% { transform: scale(1); }
  }

  .zk-suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  .zk-suggestion {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 6px 12px;
    font-size: 12px;
    color: #4b5563;
    cursor: pointer;
    transition: all 0.15s;
  }

  .zk-suggestion:hover {
    background: #f9fafb;
    border-color: ${primaryColor};
    color: ${primaryColor};
  }

  /* Bottom Input Bar */
  .zk-input-bar {
    width: 100%;
    max-width: 800px;
    padding: 12px 16px 16px;
    background: white;
    box-shadow: 0 -2px 16px rgba(0, 0, 0, 0.08);
    margin: 0 16px;
  }

  .zk-widget:not(.zk-expanded) .zk-input-bar {
    border-radius: 24px 24px 0 0;
    margin-bottom: 0;
  }

  .zk-widget.zk-expanded .zk-input-bar {
    border-radius: 0;
    box-shadow: none;
    border-top: 1px solid #e5e7eb;
  }

  .zk-input-wrapper {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .zk-input {
    flex: 1;
    padding: 12px 16px;
    border: 1px solid #e5e7eb;
    border-radius: 24px;
    font-size: 14px;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    background: #fafafa;
  }

  .zk-input:focus {
    border-color: ${primaryColor};
    box-shadow: 0 0 0 3px ${primaryColor}20;
    background: white;
  }

  .zk-input:disabled {
    background: #f3f4f6;
    cursor: not-allowed;
  }

  .zk-input::placeholder {
    color: #9ca3af;
  }

  .zk-send {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: ${primaryColor};
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.15s, transform 0.15s;
    flex-shrink: 0;
  }

  .zk-send:hover:not(:disabled) {
    transform: scale(1.05);
  }

  .zk-send:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .zk-powered-by {
    text-align: center;
    font-size: 11px;
    color: #9ca3af;
    margin-top: 8px;
  }

  .zk-powered-by a {
    color: ${primaryColor};
    text-decoration: none;
  }

  .zk-powered-by a:hover {
    text-decoration: underline;
  }

  /* Mobile Responsive */
  @media (max-width: 640px) {
    .zk-messages-panel {
      margin: 0;
      border-radius: 0;
      max-height: 60vh;
    }

    .zk-input-bar {
      margin: 0;
      padding: 12px 12px 16px;
    }

    .zk-widget:not(.zk-expanded) .zk-input-bar {
      border-radius: 0;
    }

    .zk-messages {
      max-height: calc(60vh - 60px);
    }
  }
`
