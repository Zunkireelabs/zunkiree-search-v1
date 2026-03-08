export const styles = (primaryColor: string) => `
  /* ===== Reset ===== */
  .zk-collapsed-bar *,
  .zk-expanded-panel *,
  .zk-docked * {
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
    overflow: clip;
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
    overflow-y: scroll;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-y: contain;
    touch-action: pan-y;
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

  /* ===== Docked Panel (inside #zk-right-dock) ===== */
  .zk-docked {
    width: 100%;
    height: 100%;
    background: linear-gradient(248.35deg, #86cdff -11.3%, #f4f4fe 16.44%, #fff 28.3%, #fff 72.47%, #ebeafe 89.69%, #bec6f7 101.94%);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
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
    overflow-y: scroll;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-y: contain;
    touch-action: pan-y;
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

  /* ===== Markdown Content ===== */
  .zk-md {
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  .zk-md p {
    margin: 0 0 8px 0;
  }

  .zk-md p:last-child {
    margin-bottom: 0;
  }

  .zk-md strong {
    font-weight: 600;
    color: #111827;
  }

  .zk-md em {
    font-style: italic;
  }

  .zk-md a {
    color: ${primaryColor};
    text-decoration: none;
  }

  .zk-md a:hover {
    text-decoration: underline;
  }

  .zk-md .zk-heading {
    font-weight: 600;
    color: #111827;
    margin: 12px 0 6px 0;
    line-height: 1.3;
  }

  .zk-md h3.zk-heading {
    font-size: 15px;
  }

  .zk-md h4.zk-heading {
    font-size: 14px;
  }

  .zk-md .zk-list {
    margin: 6px 0 10px 0;
    padding-left: 20px;
  }

  .zk-md .zk-list li {
    margin-bottom: 4px;
    line-height: 1.5;
    padding-left: 4px;
  }

  .zk-md ol.zk-list {
    list-style-type: decimal;
  }

  .zk-md ul.zk-list {
    list-style-type: disc;
  }

  .zk-md .zk-inline-code {
    background: rgba(0, 0, 0, 0.06);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }

  /* Tables */
  .zk-md .zk-table-wrap {
    overflow-x: auto;
    margin: 8px 0;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
  }

  .zk-md .zk-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    line-height: 1.4;
  }

  .zk-md .zk-table th {
    background: #f9fafb;
    font-weight: 600;
    color: #374151;
    text-align: left;
    padding: 8px 12px;
    border-bottom: 2px solid #e5e7eb;
    white-space: nowrap;
  }

  .zk-md .zk-table td {
    padding: 7px 12px;
    border-bottom: 1px solid #f3f4f6;
    color: #1f2937;
  }

  .zk-md .zk-table tr:last-child td {
    border-bottom: none;
  }

  .zk-md .zk-table tr:hover td {
    background: #f9fafb;
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

  /* ===== Autocomplete Dropdown ===== */
  .zk-autocomplete {
    position: absolute;
    bottom: 100%;
    left: 0;
    right: 0;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.08);
    margin-bottom: 6px;
    overflow: hidden;
    z-index: 10;
    animation: zk-fade-in 120ms ease-out;
  }

  .zk-autocomplete__item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 14px;
    background: none;
    border: none;
    font-size: 14px;
    color: #374151;
    cursor: pointer;
    text-align: left;
    font-family: inherit;
    line-height: 1.4;
    transition: background 100ms;
  }

  .zk-autocomplete__item:hover,
  .zk-autocomplete__item--active {
    background: #f3f4f6;
  }

  .zk-autocomplete__item + .zk-autocomplete__item {
    border-top: 1px solid #f3f4f6;
  }

  .zk-autocomplete__icon {
    flex-shrink: 0;
    color: #9ca3af;
  }

  .zk-autocomplete__text {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
  @media (max-width: 768px) and (min-width: 481px) {
    .zk-collapsed-bar {
      width: 90%;
    }

    .zk-expanded-panel {
      width: 95%;
      height: min(85vh, 760px);
    }
  }

  /* ===== Responsive: Mobile ===== */
  @media (max-width: 480px) {
    /* Collapsed bar — compact, edge-to-edge */
    .zk-collapsed-bar {
      width: calc(100% - 24px);
      bottom: 12px;
    }

    .zk-collapsed-bar__card {
      border-radius: 16px;
      padding: 14px;
    }

    .zk-collapsed-bar__input-inner {
      height: 44px;
      padding: 0 6px 0 12px;
    }

    .zk-collapsed-bar__placeholder {
      font-size: 13px;
    }

    .zk-collapsed-bar__chips {
      gap: 6px;
      margin-top: 10px;
    }

    .zk-chip--card {
      font-size: 12px;
      padding: 5px 10px;
    }

    /* Expanded panel — bottom sheet (not full-screen) */
    .zk-expanded-panel {
      width: calc(100% - 16px);
      height: 70vh;
      bottom: 8px;
      left: 8px;
      transform: none;
      border-radius: 20px;
      box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.15);
      animation: zk-panel-mobile-up 200ms ease-out both;
    }

    @keyframes zk-panel-mobile-up {
      from {
        transform: translateY(100%);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }

    .zk-expanded-panel__header {
      height: 48px;
      padding: 0 12px;
      border-radius: 20px 20px 0 0;
    }

    .zk-expanded-panel__title {
      font-size: 15px;
    }

    .zk-expanded-panel__hero {
      padding: 20px 16px;
    }

    .zk-expanded-panel__hero-title {
      font-size: 22px;
      margin-bottom: 16px;
    }

    .zk-expanded-panel__hero-chips {
      gap: 8px;
    }

    .zk-expanded-panel__hero-chips .zk-chip {
      font-size: 12px;
      padding: 6px 12px;
    }

    .zk-expanded-panel__messages {
      padding: 16px 12px;
    }

    .zk-expanded-panel__messages-inner {
      gap: 12px;
    }

    .zk-message {
      max-width: 92%;
    }

    .zk-message-content {
      padding: 12px 14px;
      font-size: 14px;
      line-height: 1.55;
    }

    .zk-message__suggestions {
      gap: 5px;
      margin-top: 6px;
    }

    .zk-message__suggestions .zk-chip {
      font-size: 12px;
      padding: 5px 10px;
    }

    .zk-expanded-panel__input {
      padding: 10px 12px;
      padding-bottom: calc(10px + env(safe-area-inset-bottom, 0px));
    }

    .zk-input-container {
      border-radius: 20px;
    }

    .zk-input-container::before {
      border-radius: 20px;
    }

    .zk-input-container::after {
      border-radius: 22px;
    }

    .zk-input-inner {
      border-radius: 18px;
      padding: 8px 12px;
      min-height: 42px;
    }

    .zk-input {
      font-size: 16px; /* Prevents iOS zoom on focus */
      margin-right: 36px;
    }

    .zk-send {
      width: 30px;
      height: 30px;
      bottom: 6px;
      right: 8px;
    }

    .zk-send svg {
      width: 16px;
      height: 16px;
    }

    .zk-powered-by {
      margin-top: 6px;
      font-size: 10px;
    }

    /* Autocomplete */
    .zk-autocomplete {
      border-radius: 10px;
      margin-bottom: 4px;
    }

    .zk-autocomplete__item {
      padding: 10px 12px;
      font-size: 13px;
      min-height: 44px; /* Touch target */
    }

    /* Header buttons — 44px tap target */
    .zk-header-btn {
      width: 44px;
      height: 44px;
    }

    /* Markdown content */
    .zk-md .zk-table {
      font-size: 12px;
    }

    .zk-md .zk-table th,
    .zk-md .zk-table td {
      padding: 6px 8px;
    }

    .zk-md .zk-list {
      padding-left: 16px;
    }
  }

  /* ===== iOS Virtual Keyboard Fix ===== */
  @supports (-webkit-touch-callout: none) {
    @media (max-width: 480px) {
      .zk-expanded-panel {
        height: 70dvh;
      }
    }
  }

  /* ===== Desktop-only dock button (>= 1200px) ===== */
  @media (max-width: 1199px) {
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
      opacity: 1;
    }

    /* Desktop needs translateX(-50%) since it uses left: 50% */
    @media (min-width: 481px) {
      .zk-expanded-panel {
        transform: translateX(-50%) translateY(0);
      }
    }

    /* Mobile uses left: 8px, no horizontal transform needed */
    @media (max-width: 480px) {
      .zk-expanded-panel {
        transform: translateY(0);
      }
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
