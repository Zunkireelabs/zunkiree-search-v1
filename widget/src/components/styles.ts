export const styles = (primaryColor: string) => `
  /* ===== Reset ===== */
  .zk-collapsed-bar *,
  .zk-expanded-panel * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  /* ===== Collapsed Bar ===== */
  .zk-collapsed-bar {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    opacity: 0;
    width: 720px;
    z-index: 9999;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    transition: transform 180ms ease-out, opacity 180ms ease-out;
  }

  .zk-collapsed-bar--visible {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }

  /* Card container - glassmorphic */
  .zk-collapsed-bar__card {
    position: relative;
    background: rgba(255, 255, 255, 0.12);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1), 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  /* Minimize button - top right */
  .zk-collapsed-bar__minimize {
    position: absolute;
    top: -10px;
    right: -10px;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: white;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transition: background 150ms, color 150ms, transform 150ms;
    z-index: 1;
  }

  .zk-collapsed-bar__minimize:hover {
    background: #f3f4f6;
    color: #374151;
    transform: scale(1.05);
  }

  /* Input wrapper */
  .zk-collapsed-bar__input-wrap {
    cursor: pointer;
  }

  .zk-collapsed-bar__input-inner {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 48px;
    padding: 0 8px 0 14px;
    cursor: pointer;
  }

  .zk-collapsed-bar__input-wrap:hover .zk-input-inner {
    background: #fafafa;
  }

  .zk-collapsed-bar__icon {
    color: #9ca3af;
    flex-shrink: 0;
  }

  .zk-collapsed-bar__placeholder {
    flex: 1;
    font-size: 14px;
    color: #9ca3af;
    user-select: none;
  }

  .zk-collapsed-bar__send {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #eb1600;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  /* Chips inside card */
  .zk-collapsed-bar__chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  /* Card-variant chips (on glass background) */
  .zk-chip--card {
    background: rgba(255, 255, 255, 0.85);
    border-color: rgba(0, 0, 0, 0.08);
    color: #374151;
  }

  .zk-chip--card:hover {
    background: white;
    border-color: #eb1600;
    color: #eb1600;
  }

  /* ===== Expanded Panel ===== */
  .zk-expanded-panel {
    position: fixed;
    bottom: 24px;
    left: 50%;
    width: 720px;
    max-height: 75vh;
    background: white;
    border-radius: 20px;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
    z-index: 9999;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    animation: zk-panel-slide-up 200ms ease both;
    overflow: hidden;
  }

  @keyframes zk-panel-slide-up {
    from {
      transform: translateX(-50%) translateY(100%);
      opacity: 0;
    }
    to {
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }
  }

  /* Header */
  .zk-expanded-panel__header {
    display: flex;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid #f3f4f6;
    flex-shrink: 0;
  }

  .zk-expanded-panel__title {
    flex: 1;
    font-weight: 600;
    font-size: 15px;
    color: #111827;
  }

  .zk-expanded-panel__close {
    background: none;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    transition: background 150ms, color 150ms;
  }

  .zk-expanded-panel__close:hover {
    background: #f3f4f6;
    color: #374151;
  }

  /* Suggestion Chips Section */
  .zk-expanded-panel__chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 14px 20px;
    border-bottom: 1px solid #f3f4f6;
    flex-shrink: 0;
  }

  /* Conversation Area */
  .zk-expanded-panel__messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 80px;
  }

  .zk-expanded-panel__messages::-webkit-scrollbar {
    width: 5px;
  }

  .zk-expanded-panel__messages::-webkit-scrollbar-track {
    background: transparent;
  }

  .zk-expanded-panel__messages::-webkit-scrollbar-thumb {
    background: #e5e7eb;
    border-radius: 3px;
  }

  .zk-expanded-panel__messages::-webkit-scrollbar-thumb:hover {
    background: #d1d5db;
  }

  .zk-expanded-panel__messages {
    scrollbar-width: thin;
    scrollbar-color: #e5e7eb transparent;
  }

  /* Input Section */
  .zk-expanded-panel__input {
    padding: 12px 16px 14px;
    border-top: 1px solid #f3f4f6;
    flex-shrink: 0;
  }

  /* ===== Shared: Chip ===== */
  .zk-chip {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 13px;
    color: #4b5563;
    cursor: pointer;
    transition: all 150ms;
    font-family: inherit;
    white-space: nowrap;
    line-height: 1.4;
  }

  .zk-chip:hover {
    background: #f9fafb;
    border-color: ${primaryColor};
    color: ${primaryColor};
  }

  /* ===== Messages ===== */
  .zk-message {
    max-width: 85%;
    animation: zk-fade-in 200ms ease;
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

  .zk-message__suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  /* ===== Typing Indicator ===== */
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

  /* ===== Input Container with Animated Border ===== */
  @property --border-angle {
    syntax: '<angle>';
    initial-value: 0deg;
    inherits: false;
  }

  .zk-input-container {
    position: relative;
    background: #e5e7eb;
    border-radius: 24px;
    padding: 1.5px;
    isolation: isolate;
  }

  .zk-input-container::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 24px;
    padding: 1.5px;
    background: conic-gradient(
      from var(--border-angle),
      transparent 0%,
      transparent 6%,
      #3b82f6 8%,
      #06b6d4 10%,
      #84cc16 12%,
      #eab308 14%,
      transparent 16%,
      transparent 100%
    );
    -webkit-mask:
      linear-gradient(#fff 0 0) content-box,
      linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask:
      linear-gradient(#fff 0 0) content-box,
      linear-gradient(#fff 0 0);
    mask-composite: exclude;
    animation: rotate-border 4s linear infinite;
  }

  .zk-input-container::after {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: 26px;
    background: conic-gradient(
      from var(--border-angle),
      transparent 0%,
      transparent 6%,
      #3b82f6 8%,
      #06b6d4 10%,
      #84cc16 12%,
      #eab308 14%,
      transparent 16%,
      transparent 100%
    );
    filter: blur(6px);
    opacity: 0.4;
    z-index: -1;
    animation: rotate-border 4s linear infinite;
  }

  @keyframes rotate-border {
    0% { --border-angle: 0deg; }
    100% { --border-angle: 360deg; }
  }

  .zk-input-inner {
    position: relative;
    background: white;
    border-radius: 22px;
    padding: 10px 16px;
    min-height: 44px;
    display: flex;
    align-items: flex-end;
  }

  .zk-input {
    flex: 1;
    border: none;
    font-size: 14px;
    outline: none;
    background: transparent;
    resize: none;
    line-height: 22px;
    color: #1f2937;
    min-height: 22px;
    max-height: 120px;
    overflow-y: auto;
    font-family: inherit;
    padding: 0;
    padding-right: 8px;
    margin: 0;
    margin-right: 40px;
  }

  .zk-input::-webkit-scrollbar {
    width: 4px;
  }

  .zk-input::-webkit-scrollbar-track {
    background: transparent;
  }

  .zk-input::-webkit-scrollbar-thumb {
    background: #d1d5db;
    border-radius: 2px;
  }

  .zk-input {
    scrollbar-width: thin;
    scrollbar-color: #d1d5db transparent;
  }

  .zk-input::placeholder {
    color: #9ca3af;
  }

  .zk-input:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .zk-send {
    position: absolute;
    bottom: 6px;
    right: 10px;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #f3f4f6;
    color: #374151;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 150ms, transform 150ms, color 150ms;
    flex-shrink: 0;
  }

  .zk-send:hover:not(:disabled) {
    background: #e5e7eb;
    transform: scale(1.05);
  }

  .zk-send:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* ===== Powered By ===== */
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

  /* ===== Responsive: Tablet ===== */
  @media (max-width: 768px) and (min-width: 641px) {
    .zk-collapsed-bar {
      width: 90%;
    }

    .zk-expanded-panel {
      width: 90%;
    }
  }

  /* ===== Responsive: Mobile ===== */
  @media (max-width: 640px) {
    .zk-collapsed-bar {
      width: calc(100% - 32px);
      bottom: 16px;
    }

    .zk-expanded-panel {
      width: calc(100% - 32px);
      bottom: 16px;
      max-height: 80vh;
      border-radius: 16px;
    }

    .zk-expanded-panel__header {
      padding: 14px 16px;
    }

    .zk-expanded-panel__chips {
      padding: 12px 16px;
    }

    .zk-expanded-panel__messages {
      padding: 12px 16px;
    }

    .zk-expanded-panel__input {
      padding: 10px 12px 12px;
    }
  }

  /* ===== Reduced Motion ===== */
  @media (prefers-reduced-motion: reduce) {
    .zk-collapsed-bar {
      transition: none;
    }

    .zk-collapsed-bar--visible {
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }

    .zk-expanded-panel {
      animation: none;
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }

    .zk-message {
      animation: none;
    }

    .zk-input-container::before,
    .zk-input-container::after {
      animation: none;
    }
  }
`
