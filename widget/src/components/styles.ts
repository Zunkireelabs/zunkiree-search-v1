export const styles = (primaryColor: string) => `
  /* ===== Reset ===== */
  .zk-collapsed-bar *,
  .zk-expanded-panel *,
  .zk-docked * {
    box-sizing: border-box !important;
    margin: 0;
    padding: 0;
  }

  /* ===== Collapsed Bar ===== */
  .zk-collapsed-bar {
    position: fixed !important;
    bottom: 24px !important;
    left: 50% !important;
    right: auto !important;
    transform: translateX(-50%) translateY(20px) !important;
    opacity: 0;
    width: 720px !important;
    max-width: 720px !important;
    min-width: 0 !important;
    z-index: 9999 !important;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    transition: transform 180ms ease-out, opacity 180ms ease-out;
    box-sizing: border-box !important;
    float: none !important;
    display: block !important;
  }

  .zk-collapsed-bar--visible {
    transform: translateX(-50%) translateY(0) !important;
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

  /* Language Toggle */
  .zk-lang-toggle {
    display: flex;
    align-items: center;
    background: #f3f4f6;
    border-radius: 8px;
    padding: 2px;
    gap: 2px;
    margin-right: 4px;
  }

  .zk-lang-btn {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    transition: background 150ms, color 150ms;
    line-height: 1.2;
  }

  .zk-lang-btn:hover {
    color: #374151;
  }

  .zk-lang-btn--active {
    background: white;
    color: #111827;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
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

  /* ===== Mobile FAB ===== */
  .zk-fab {
    display: none; /* hidden on desktop */
  }

  /* ===== Mobile (JS-detected via .zk-mobile class) ===== */
  /* Using a class instead of @media query because host sites may lack
     a proper viewport meta tag, making CSS media queries unreliable. */

  /* --- FAB: circle button, bottom-right --- */
  .zk-mobile .zk-fab {
    display: flex !important;
    align-items: center;
    justify-content: center;
    position: fixed;
    bottom: 16px;
    right: 16px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: none;
    background: linear-gradient(135deg, #2067fb 0%, #000b22 100%);
    color: white;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    z-index: 9999;
    cursor: pointer;
    opacity: 0;
    transform: scale(0.8);
    transition: opacity 180ms ease-out, transform 180ms ease-out;
  }

  .zk-mobile .zk-fab--visible {
    opacity: 1;
    transform: scale(1);
  }

  /* Kill the desktop collapsed bar — it causes page overflow */
  .zk-mobile .zk-collapsed-bar,
  .zk-mobile .zk-collapsed-bar--visible {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
    position: absolute !important;
    pointer-events: none !important;
  }

  /* --- Backdrop --- */
  .zk-mobile .zk-backdrop {
    background: rgba(0, 0, 0, 0.3) !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
  }

  /* --- Expanded panel --- */
  .zk-mobile .zk-expanded-panel {
    position: fixed !important;
    bottom: 8px !important;
    left: 8px !important;
    right: 8px !important;
    top: auto !important;
    width: auto !important;
    height: 60vh !important;
    max-height: none !important;
    transform: translateY(0) !important;
    border-radius: 20px !important;
    background: #fff !important;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.18) !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
    animation: zk-mob-up 200ms ease-out both !important;
  }

  @keyframes zk-mob-up {
    from { opacity: 0; transform: translateY(40px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* --- Header: 48px, solid white, always visible --- */
  .zk-mobile .zk-expanded-panel__header {
    display: flex !important;
    align-items: center !important;
    height: 48px !important;
    min-height: 48px !important;
    flex-shrink: 0 !important;
    padding: 0 10px !important;
    background: #fff !important;
    border-bottom: 1px solid #e5e7eb !important;
    border-radius: 20px 20px 0 0 !important;
  }

  .zk-mobile .zk-expanded-panel__title {
    font-size: 15px !important;
    font-weight: 600 !important;
    color: #111827 !important;
    flex: 1 !important;
  }

  .zk-mobile .zk-expanded-panel__controls {
    display: flex !important;
    align-items: center !important;
    gap: 2px !important;
    flex-shrink: 0 !important;
  }

  .zk-mobile .zk-header-btn {
    width: 32px !important;
    height: 32px !important;
    color: #6b7280 !important;
  }

  .zk-mobile .zk-dock-btn {
    display: none !important;
  }

  /* --- Language toggle --- */
  .zk-mobile .zk-lang-toggle {
    display: flex !important;
    padding: 2px !important;
    gap: 1px !important;
    margin-right: 4px !important;
    background: #f3f4f6 !important;
    border-radius: 6px !important;
  }

  .zk-mobile .zk-lang-btn {
    font-size: 11px !important;
    padding: 3px 8px !important;
    border-radius: 4px !important;
  }

  .zk-mobile .zk-lang-btn--active {
    background: #fff !important;
    color: #111827 !important;
  }

  /* --- Hero --- */
  .zk-mobile .zk-expanded-panel__hero {
    padding: 16px 14px !important;
    flex-shrink: 0 !important;
  }

  .zk-mobile .zk-expanded-panel__hero-title {
    font-size: 18px !important;
    margin-bottom: 12px !important;
  }

  .zk-mobile .zk-expanded-panel__hero-chips {
    gap: 6px !important;
  }

  .zk-mobile .zk-expanded-panel__hero-chips .zk-chip {
    font-size: 12px !important;
    padding: 5px 10px !important;
  }

  /* --- Messages area --- */
  .zk-mobile .zk-expanded-panel__messages {
    flex: 1 1 0% !important;
    min-height: 0 !important;
    padding: 12px 10px !important;
    overflow-y: auto !important;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-y: contain;
  }

  .zk-mobile .zk-expanded-panel__messages-inner {
    gap: 8px !important;
  }

  .zk-mobile .zk-message {
    max-width: 92% !important;
  }

  .zk-mobile .zk-message-content {
    padding: 10px 12px !important;
    font-size: 14px !important;
    line-height: 1.45 !important;
    border-radius: 14px !important;
  }

  .zk-mobile .zk-message-assistant .zk-message-content {
    background: #f9fafb !important;
    border: 1px solid #e5e7eb !important;
    border-bottom-left-radius: 4px !important;
  }

  .zk-mobile .zk-message-user .zk-message-content {
    background: #eff6ff !important;
    border: 1px solid #dbeafe !important;
    border-bottom-right-radius: 4px !important;
  }

  .zk-mobile .zk-message__suggestions {
    gap: 5px !important;
    margin-top: 6px !important;
  }

  .zk-mobile .zk-message__suggestions .zk-chip {
    font-size: 12px !important;
    padding: 5px 10px !important;
  }

  /* --- Input area --- */
  .zk-mobile .zk-expanded-panel__input {
    flex-shrink: 0 !important;
    padding: 8px 10px !important;
    padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px)) !important;
    background: #fff !important;
    border-top: 1px solid #e5e7eb !important;
  }

  .zk-mobile .zk-input-container {
    border-radius: 18px !important;
    background: transparent !important;
    padding: 0 !important;
  }

  .zk-mobile .zk-input-container::before {
    display: none !important;
  }

  .zk-mobile .zk-input-container::after {
    display: none !important;
  }

  .zk-mobile .zk-input-inner {
    border-radius: 16px !important;
    padding: 6px 10px !important;
    min-height: 38px !important;
    background: #f9fafb !important;
    border: 1.5px solid #d1d5db !important;
  }

  .zk-mobile .zk-input {
    font-size: 16px !important;
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    margin-right: 34px !important;
    background: transparent !important;
    opacity: 1 !important;
  }

  .zk-mobile .zk-input::placeholder {
    color: #6b7280 !important;
    -webkit-text-fill-color: #6b7280 !important;
    opacity: 1 !important;
  }

  .zk-mobile .zk-input::-webkit-input-placeholder {
    color: #6b7280 !important;
    -webkit-text-fill-color: #6b7280 !important;
    opacity: 1 !important;
  }

  .zk-mobile .zk-send {
    width: 28px !important;
    height: 28px !important;
    bottom: 5px !important;
    right: 6px !important;
  }

  .zk-mobile .zk-send svg {
    width: 14px !important;
    height: 14px !important;
  }

  .zk-mobile .zk-powered-by {
    margin-top: 4px !important;
    font-size: 10px !important;
  }

  /* --- Autocomplete --- */
  .zk-mobile .zk-autocomplete {
    border-radius: 12px !important;
    margin-bottom: 4px !important;
    background: #fff !important;
    border: 1px solid #e5e7eb !important;
    box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.08) !important;
  }

  .zk-mobile .zk-autocomplete__item {
    padding: 10px 12px !important;
    font-size: 13px !important;
    min-height: 44px !important;
  }

  .zk-mobile .zk-autocomplete__item:hover,
  .zk-mobile .zk-autocomplete__item--active {
    background: #f3f4f6 !important;
  }

  .zk-mobile .zk-message-assistant .zk-typing {
    background: #f9fafb !important;
  }

  /* --- Markdown --- */
  .zk-mobile .zk-md .zk-table { font-size: 12px !important; }
  .zk-mobile .zk-md .zk-table th,
  .zk-mobile .zk-md .zk-table td { padding: 6px 8px !important; }
  .zk-mobile .zk-md .zk-table-wrap { background: #fff !important; border-color: #e5e7eb !important; }
  .zk-mobile .zk-md .zk-table th { background: #f9fafb !important; }
  .zk-mobile .zk-md .zk-list { padding-left: 16px !important; }

  /* ===== iOS height ===== */
  @supports (-webkit-touch-callout: none) {
    .zk-mobile .zk-expanded-panel {
      height: 60dvh !important;
    }
  }

  /* ===== Product Grid ===== */
  .zk-product-grid {
    margin-top: 8px;
  }

  .zk-product-grid__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .zk-product-grid__count {
    font-size: 12px;
    color: #6b7280;
  }

  .zk-product-grid__arrows {
    display: flex;
    gap: 4px;
  }

  .zk-product-grid__arrow {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #f3f4f6;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    transition: background 150ms;
  }

  .zk-product-grid__arrow:hover {
    background: #e5e7eb;
    color: #374151;
  }

  .zk-product-grid__scroll {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 4px;
    scrollbar-width: none;
  }

  .zk-product-grid__scroll::-webkit-scrollbar {
    display: none;
  }

  /* ===== Product Card ===== */
  .zk-product-card {
    flex-shrink: 0;
    width: 220px;
    scroll-snap-align: start;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
    transition: box-shadow 150ms;
  }

  .zk-product-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  .zk-product-card__image {
    position: relative;
    width: 100%;
    height: 160px;
    background: #f9fafb;
    overflow: hidden;
  }

  .zk-product-card__image img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .zk-product-card__image--placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .zk-product-card__badge {
    position: absolute;
    top: 8px;
    right: 8px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
  }

  .zk-product-card__badge--in {
    background: #dcfce7;
    color: #166534;
  }

  .zk-product-card__badge--out {
    background: #f3f4f6;
    color: #6b7280;
  }

  .zk-product-card__info {
    padding: 10px 12px;
  }

  .zk-product-card__name {
    font-size: 13px;
    font-weight: 500;
    color: #111827;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-bottom: 4px;
  }

  .zk-product-card__price-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 6px;
  }

  .zk-product-card__price {
    font-size: 15px;
    font-weight: 600;
    color: #111827;
  }

  .zk-product-card__original-price {
    font-size: 12px;
    color: #9ca3af;
    text-decoration: line-through;
  }

  .zk-product-card__sizes {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 6px;
  }

  .zk-size-pill {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    color: #374151;
    cursor: pointer;
    transition: all 100ms;
  }

  .zk-size-pill--active {
    background: ${primaryColor}15;
    border-color: ${primaryColor};
    color: ${primaryColor};
  }

  .zk-product-card__colors {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 6px;
  }

  .zk-color-swatch {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    cursor: pointer;
    transition: all 100ms;
  }

  .zk-color-swatch--active {
    background: ${primaryColor}15;
    border-color: ${primaryColor};
    color: ${primaryColor};
  }

  .zk-product-card__actions {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }

  .zk-product-card__add-btn {
    flex: 1;
    padding: 6px 0;
    background: ${primaryColor};
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 150ms;
    font-family: inherit;
  }

  .zk-product-card__add-btn:hover:not(:disabled) {
    opacity: 0.9;
  }

  .zk-product-card__add-btn:disabled {
    background: #d1d5db;
    cursor: not-allowed;
  }

  .zk-product-card__view-link {
    padding: 6px 12px;
    background: #f3f4f6;
    color: #374151;
    border-radius: 6px;
    font-size: 12px;
    text-decoration: none;
    display: flex;
    align-items: center;
    transition: background 150ms;
  }

  .zk-product-card__view-link:hover {
    background: #e5e7eb;
  }

  /* ===== Cart View ===== */
  .zk-cart-view {
    margin-top: 8px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
  }

  .zk-cart-view--empty {
    padding: 16px;
    text-align: center;
    color: #6b7280;
    font-size: 13px;
  }

  .zk-cart-view__items {
    max-height: 200px;
    overflow-y: auto;
  }

  .zk-cart-view__item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid #f3f4f6;
  }

  .zk-cart-view__item:last-child {
    border-bottom: none;
  }

  .zk-cart-view__thumb {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
  }

  .zk-cart-view__item-info {
    flex: 1;
    min-width: 0;
  }

  .zk-cart-view__item-name {
    font-size: 13px;
    font-weight: 500;
    color: #111827;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .zk-cart-view__item-details {
    display: flex;
    gap: 8px;
    font-size: 11px;
    color: #6b7280;
    margin-top: 2px;
  }

  .zk-cart-view__item-price {
    font-size: 13px;
    font-weight: 600;
    color: #111827;
    margin-top: 2px;
  }

  .zk-cart-view__remove {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #f3f4f6;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #9ca3af;
    flex-shrink: 0;
    transition: background 150ms, color 150ms;
  }

  .zk-cart-view__remove:hover {
    background: #fee2e2;
    color: #ef4444;
  }

  .zk-cart-view__footer {
    padding: 10px 12px;
    border-top: 1px solid #e5e7eb;
    background: #f9fafb;
  }

  .zk-cart-view__subtotal {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: #374151;
    margin-bottom: 8px;
  }

  .zk-cart-view__subtotal-price {
    font-weight: 600;
  }

  .zk-cart-view__checkout-btn {
    width: 100%;
    padding: 8px;
    background: ${primaryColor};
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 150ms;
    font-family: inherit;
  }

  .zk-cart-view__checkout-btn:hover {
    opacity: 0.9;
  }

  /* ===== Checkout View ===== */
  .zk-checkout-view {
    margin-top: 8px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
  }

  .zk-checkout-view__header {
    padding: 10px 12px;
    background: #f0fdf4;
    border-bottom: 1px solid #dcfce7;
  }

  .zk-checkout-view__note {
    font-size: 12px;
    color: #166534;
    margin: 0;
  }

  .zk-checkout-view__items {
    max-height: 240px;
    overflow-y: auto;
  }

  .zk-checkout-view__item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid #f3f4f6;
  }

  .zk-checkout-view__item:last-child {
    border-bottom: none;
  }

  .zk-checkout-view__item-info {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 0;
  }

  .zk-checkout-view__thumb {
    width: 36px;
    height: 36px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
  }

  .zk-checkout-view__item-name {
    font-size: 13px;
    font-weight: 500;
    color: #111827;
  }

  .zk-checkout-view__item-details {
    display: flex;
    gap: 8px;
    font-size: 11px;
    color: #6b7280;
    margin-top: 2px;
  }

  .zk-checkout-view__buy-btn {
    padding: 6px 12px;
    background: ${primaryColor};
    color: white;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
    transition: opacity 150ms;
  }

  .zk-checkout-view__buy-btn:hover {
    opacity: 0.9;
  }

  .zk-checkout-view__total {
    display: flex;
    justify-content: space-between;
    padding: 10px 12px;
    border-top: 1px solid #e5e7eb;
    background: #f9fafb;
    font-size: 14px;
    font-weight: 600;
    color: #111827;
  }

  /* ===== Tool Loading ===== */
  .zk-tool-loading {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
  }

  .zk-tool-loading__dot {
    width: 8px;
    height: 8px;
    background: ${primaryColor};
    border-radius: 50%;
    animation: zk-tool-pulse 1s ease-in-out infinite;
  }

  @keyframes zk-tool-pulse {
    0%, 100% { opacity: 0.3; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1); }
  }

  .zk-tool-loading__text {
    font-size: 12px;
    color: #6b7280;
    font-style: italic;
  }

  /* ===== Mobile: Product/Cart/Checkout ===== */
  .zk-mobile .zk-product-card {
    width: 180px;
  }

  .zk-mobile .zk-product-card__image {
    height: 120px;
  }

  .zk-mobile .zk-product-card__name {
    font-size: 12px;
  }

  .zk-mobile .zk-product-card__price {
    font-size: 13px;
  }

  .zk-mobile .zk-product-card__add-btn {
    font-size: 11px;
    padding: 5px 0;
  }

  .zk-mobile .zk-cart-view__item {
    padding: 8px 10px;
  }

  .zk-mobile .zk-checkout-view__item {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .zk-mobile .zk-checkout-view__buy-btn {
    width: 100%;
    text-align: center;
    display: block;
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

    .zk-expanded-panel {
      transform: translateX(-50%) translateY(0);
    }

    /* Mobile uses left: 8px, no horizontal transform needed */
    .zk-mobile .zk-expanded-panel {
      transform: translateY(0);
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
