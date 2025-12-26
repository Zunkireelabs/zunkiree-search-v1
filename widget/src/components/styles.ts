export const styles = (primaryColor: string) => `
  .zk-trigger {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: ${primaryColor};
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    transition: transform 0.2s, box-shadow 0.2s;
    z-index: 9999;
  }

  .zk-trigger:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
  }

  .zk-container {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 380px;
    height: 520px;
    background: white;
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 9999;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  @media (max-width: 480px) {
    .zk-container {
      width: 100%;
      height: 100%;
      bottom: 0;
      right: 0;
      border-radius: 0;
    }
  }

  .zk-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: ${primaryColor};
    color: white;
  }

  .zk-header-title {
    font-weight: 600;
    font-size: 16px;
  }

  .zk-close {
    background: none;
    border: none;
    color: white;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.8;
    transition: opacity 0.2s;
  }

  .zk-close:hover {
    opacity: 1;
  }

  .zk-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
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
    padding: 12px 16px;
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
    padding: 16px;
  }

  .zk-typing span {
    width: 8px;
    height: 8px;
    background: #9ca3af;
    border-radius: 50%;
    animation: zk-bounce 1.4s infinite ease-in-out both;
  }

  .zk-typing span:nth-child(1) {
    animation-delay: -0.32s;
  }

  .zk-typing span:nth-child(2) {
    animation-delay: -0.16s;
  }

  @keyframes zk-bounce {
    0%, 80%, 100% {
      transform: scale(0);
    }
    40% {
      transform: scale(1);
    }
  }

  .zk-suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
  }

  .zk-suggestion {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 6px 12px;
    font-size: 13px;
    color: #4b5563;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
  }

  .zk-suggestion:hover {
    background: #f9fafb;
    border-color: ${primaryColor};
    color: ${primaryColor};
  }

  .zk-input-area {
    display: flex;
    gap: 8px;
    padding: 16px;
    border-top: 1px solid #e5e7eb;
    background: white;
  }

  .zk-input {
    flex: 1;
    padding: 12px 16px;
    border: 1px solid #e5e7eb;
    border-radius: 24px;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  }

  .zk-input:focus {
    border-color: ${primaryColor};
  }

  .zk-input:disabled {
    background: #f9fafb;
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
    transition: opacity 0.2s, transform 0.2s;
  }

  .zk-send:hover:not(:disabled) {
    transform: scale(1.05);
  }

  .zk-send:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`
