export const styles = (primaryColor: string) => `
  /* ===== Reset ===== */
  .zk-collapsed-bar *,
  .zk-expanded-panel *,
  .zk-docked * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  /* ===== Body Layout Shift (Docked Mode) ===== */
  body.zk-docked-active {
    display: flex !important;
  }

  body.zk-docked-active > *:not(#zunkiree-widget-root) {
    flex: 1 1 auto;
    min-width: 0;
    transition: flex 200ms ease;
  }

  #zunkiree-widget-root.zk-docked-mode {
    width: 460px;
    flex: 0 0 460px;
    height: 100vh;
    transition: width 200ms ease;
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
    background: linear-gradient(180deg, #2067fb 0%, #000b22 140.34%);
    border: 1px solid rgba(255, 255, 255, 0.08);
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

  /* Card-variant chips (on dark glass background) */
  .zk-chip--card {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.2);
    color: rgba(255, 255, 255, 0.85);
  }

  .zk-chip--card:hover {
    background: rgba(255, 255, 255, 0.18);
    border-color: rgba(255, 255, 255, 0.35);
    color: white;
  }

  /* ===== Backdrop ===== */
  .zk-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.04);
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
    z-index: 9998;
    animation: zk-backdrop-fade 200ms ease-out both;
  }

  @keyframes zk-backdrop-fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  /* ===== Expanded Panel ===== */
  .zk-expanded-panel {
    position: fixed;
    bottom: 24px;
    left: 50%;
    width: min(1000px, 90%);
    height: min(80vh, 760px);
    background: linear-gradient(248.35deg, #86cdff -11.3%, #f4f4fe 16.44%, #fff 28.3%, #fff 72.47%, #ebeafe 89.69%, #bec6f7 101.94%);
    border-radius: 24px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.18);
    z-index: 9999;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    animation: zk-panel-slide-up 200ms ease-out both;
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

  /* Header - 64px */
  .zk-expanded-panel__header {
    display: flex;
    align-items: center;
    height: 64px;
    padding: 0 24px;
    background: white;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    flex-shrink: 0;
    border-radius: 24px 24px 0 0;
  }

  .zk-expanded-panel__title {
    flex: 1;
    font-weight: 600;
    font-size: 16px;
    color: #111827;
  }

  /* ===== Shared Header Controls ===== */
  .zk-expanded-panel__controls,
  .zk-docked__controls {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .zk-header-btn {
    background: none;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    transition: background 150ms, color 150ms;
  }

  .zk-header-btn:hover {
    background: #f3f4f6;
    color: #374151;
  }

  /* Hero Section - only when no messages */
  .zk-expanded-panel__hero {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 32px;
  }

  .zk-expanded-panel__hero-title {
    font-size: 30px;
    font-weight: 600;
    color: #111827;
    text-align: center;
    margin-bottom: 24px;
    line-height: 1.2;
  }

  .zk-expanded-panel__hero-chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 12px;
  }

  /* Conversation Area */
  .zk-expanded-panel__messages {
    flex: 1;
    overflow-y: auto;
    padding: 32px;
    min-height: 0;
  }

  .zk-expanded-panel__messages-inner {
    max-width: 720px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
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

  /* Input Section - sticky bottom */
  .zk-expanded-panel__input {
    padding: 16px 24px;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
    flex-shrink: 0;
  }

  /* ===== Docked Panel ===== */
  .zk-docked {
    width: 100%;
    height: 100vh;
    background: linear-gradient(248.35deg, #86cdff -11.3%, #f4f4fe 16.44%, #fff 28.3%, #fff 72.47%, #ebeafe 89.69%, #bec6f7 101.94%);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    border-left: 1px solid rgba(0, 0, 0, 0.08);
    animation: zk-dock-slide-in 200ms ease-out both;
  }

  @keyframes zk-dock-slide-in {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  /* Docked Header */
  .zk-docked__header {
    display: flex;
    align-items: center;
    height: 64px;
    padding: 0 20px;
    background: white;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    flex-shrink: 0;
  }

  .zk-docked__title {
    flex: 1;
    font-weight: 600;
    font-size: 16px;
    color: #111827;
  }

  /* Docked Hero */
  .zk-docked__hero {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
  }

  .zk-docked__hero-title {
    font-size: 22px;
    font-weight: 600;
    color: #111827;
    text-align: center;
    margin-bottom: 20px;
    line-height: 1.2;
  }

  .zk-docked__hero-chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }

  /* Docked Messages */
  .zk-docked__messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px 16px;
    min-height: 0;
  }

  .zk-docked__messages-inner {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .zk-docked__messages::-webkit-scrollbar {
    width: 5px;
  }

  .zk-docked__messages::-webkit-scrollbar-track {
    background: transparent;
  }

  .zk-docked__messages::-webkit-scrollbar-thumb {
    background: #e5e7eb;
    border-radius: 3px;
  }

  .zk-docked__messages::-webkit-scrollbar-thumb:hover {
    background: #d1d5db;
  }

  .zk-docked__messages {
    scrollbar-width: thin;
    scrollbar-color: #e5e7eb transparent;
  }

  /* Docked Input */
  .zk-docked__input {
    padding: 16px;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
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
    padding: 16px 18px;
    border-radius: 16px;
    font-size: 15px;
    line-height: 1.6;
  }

  .zk-message-user .zk-message-content {
    background: ${primaryColor}12;
    color: #1f2937;
    border-bottom-right-radius: 4px;
  }

  .zk-message-assistant .zk-message-content {
    background: #f8f9fa;
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
    border: none !important;
    font-size: 14px;
    outline: none !important;
    box-shadow: none !important;
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
  }

  /* ===== Responsive: Mobile ===== */
  @media (max-width: 640px) {
    .zk-collapsed-bar {
      width: calc(100% - 32px);
      bottom: 16px;
    }

    .zk-expanded-panel {
      width: calc(100% - 16px);
      bottom: 8px;
      height: calc(100vh - 16px);
      border-radius: 16px;
    }

    .zk-expanded-panel__header {
      height: 56px;
      padding: 0 16px;
    }

    .zk-expanded-panel__hero {
      padding: 24px 20px;
    }

    .zk-expanded-panel__hero-title {
      font-size: 24px;
      margin-bottom: 20px;
    }

    .zk-expanded-panel__messages {
      padding: 20px 16px;
    }

    .zk-expanded-panel__input {
      padding: 12px 16px;
    }
  }

  /* ===== Mobile: Hide dock button ===== */
  @media (max-width: 767px) {
    .zk-dock-btn {
      display: none;
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

    .zk-backdrop {
      animation: none;
    }

    .zk-expanded-panel {
      animation: none;
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }

    .zk-docked {
      animation: none;
      transform: translateX(0);
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
