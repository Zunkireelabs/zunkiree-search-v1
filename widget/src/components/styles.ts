export const styles = (primaryColor: string) => `
  /* ===== Zunkiree brand orb =====
     Green gradient sphere with a fine noise grain. Shared by the launcher
     pill, the launcher bar and the mobile FAB so the brand reads the same
     in every collapsed state, independent of the tenant's primary_color
     (which still drives chips/focus accents). */
  .zk-orb {
    position: relative;
    flex-shrink: 0;
    border-radius: 50%;
    background: radial-gradient(circle at 32% 26%,
      #a8f8cb 0%, #4ade80 22%, #1aa95f 54%, #0a7f47 80%, #05532f 100%);
    box-shadow:
      inset 0 -3px 8px rgba(2, 52, 29, 0.38),
      inset 0 2px 6px rgba(255, 255, 255, 0.5),
      0 2px 10px rgba(10, 127, 71, 0.35);
    overflow: hidden;
  }

  .zk-orb::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Cfilter id='zkn'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100' height='100' filter='url(%23zkn)'/%3E%3C/svg%3E");
    background-size: 72px 72px;
    opacity: 0.42;
    mix-blend-mode: overlay;
    pointer-events: none;
  }

  .zk-orb--lg { width: 38px; height: 38px; }
  .zk-orb--md { width: 28px; height: 28px; }
  .zk-orb--sm { width: 20px; height: 20px; }

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
    width: 640px !important;
    max-width: calc(100vw - 48px) !important;
    min-width: 0 !important;
    z-index: 9999 !important;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    transition: transform 250ms ease, opacity 250ms ease;
    box-sizing: border-box !important;
    float: none !important;
    display: block !important;
  }

  .zk-collapsed-bar--visible {
    transform: translateX(-50%) translateY(0) !important;
    opacity: 1;
  }

  .zk-collapsed-bar--hidden {
    transform: translateX(-50%) translateY(20px) !important;
    opacity: 0 !important;
    pointer-events: none !important;
  }

  /* Card container - light surface, brand lives in the orb */
  .zk-collapsed-bar__card {
    position: relative;
    background: #ffffff;
    border: 1px solid rgba(16, 24, 40, 0.07);
    border-radius: 26px;
    padding: 10px;
    box-shadow:
      0 14px 44px rgba(16, 24, 40, 0.12),
      0 2px 6px rgba(16, 24, 40, 0.05);
  }

  /* Minimize button - top right */
  .zk-collapsed-bar__minimize {
    position: absolute;
    top: -9px;
    right: -9px;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: white;
    border: 1px solid rgba(16, 24, 40, 0.08);
    color: #9ca3af;
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

  /* Shape, fill, padding and gap all come from the shared .zk-input-inner
     so the launcher bar and the panel composer stay identical. The only
     difference is this one is a fixed-height, non-growing row. */
  .zk-collapsed-bar__input-inner {
    height: 48px;
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
    font-size: 15px;
    color: #9ca3af;
    letter-spacing: -0.01em;
    user-select: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .zk-collapsed-bar__send {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: radial-gradient(circle at 32% 26%,
      #4ade80 0%, #1aa95f 52%, #0a7f47 100%);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(10, 127, 71, 0.32);
    transition: transform 150ms ease;
  }

  .zk-collapsed-bar__input-wrap:hover .zk-collapsed-bar__send {
    transform: scale(1.06);
  }

  /* Chips inside card */
  .zk-collapsed-bar__chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 4px 2px;
  }

  /* Card-variant chips (light surface) */
  .zk-chip--card {
    background: #f6f7f9;
    border-color: rgba(16, 24, 40, 0.07);
    color: #4b5563;
  }

  .zk-chip--card:hover {
    background: #eef0f3;
    border-color: rgba(16, 24, 40, 0.14);
    color: #16181d;
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
    width: min(640px, calc(100vw - 48px));
    /* Hug the content: the card is only as tall as the conversation needs,
       up to the cap. Replaces the old fixed 80vh box that left a large
       empty area on the welcome screen. */
    height: auto;
    max-height: min(74vh, 660px);
    background: #ffffff;
    border: 1px solid rgba(16, 24, 40, 0.06);
    border-radius: 26px;
    box-shadow:
      0 28px 70px rgba(16, 24, 40, 0.18),
      0 2px 8px rgba(16, 24, 40, 0.06);
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

  /* Header - slim 44px strip */
  .zk-expanded-panel__header {
    display: flex;
    align-items: center;
    height: 44px;
    padding: 0 10px 0 18px;
    background: transparent;
    border-bottom: 1px solid rgba(16, 24, 40, 0.06);
    flex-shrink: 0;
    border-radius: 26px 26px 0 0;
  }

  .zk-expanded-panel__title {
    flex: 1;
    font-weight: 600;
    font-size: 13px;
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

  /* Cart Badge in Header */
  .zk-header-cart {
    position: relative;
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    transition: background 150ms, color 150ms;
  }
  .zk-header-cart:hover {
    background: #f3f4f6;
    color: #374151;
  }
  .zk-header-cart__badge {
    position: absolute;
    top: 4px;
    right: 2px;
    min-width: 16px;
    height: 16px;
    background: #ef4444;
    color: white;
    font-size: 10px;
    font-weight: 700;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
    line-height: 1;
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
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 28px 24px 100px;
  }

  .zk-expanded-panel__hero-title {
    font-size: 19px;
    font-weight: 600;
    color: #16181d;
    text-align: center;
    margin-bottom: 16px;
    line-height: 1.3;
    letter-spacing: -0.01em;
  }

  .zk-expanded-panel__hero-chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 12px;
  }

  /* Conversation Area */
  .zk-expanded-panel__messages {
    /* flex: 0 1 auto so an empty/short conversation does not stretch the
       card — it only takes the height it needs, then scrolls at the cap. */
    flex: 0 1 auto;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-y: contain;
    touch-action: pan-y;
    /* Bottom padding clears the composer, which now floats over this
       area rather than sitting below it in flow. */
    padding: 16px 18px 96px;
    will-change: scroll-position;
    contain: layout style;
    min-height: 0;
  }

  .zk-expanded-panel__messages:empty {
    padding: 0;
  }

  .zk-expanded-panel__messages-inner {
    max-width: 100%;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
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
  /* Floating composer — messages scroll underneath it and dissolve into
     the frosted gradient instead of being cut off by a hard divider. */
  .zk-expanded-panel__input {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 2;
    padding: 24px 10px 8px;
    /* The gradient block ignores pointer events so the conversation stays
       scrollable through it; the controls themselves opt back in below. */
    pointer-events: none;
  }

  .zk-expanded-panel__input > * {
    pointer-events: auto;
  }

  /* The frost lives on its own layer behind the controls. Masking the form
     itself would fade the input pill along with the background, so the
     gradient, the blur and the mask all sit here instead. */
  .zk-expanded-panel__input::before {
    content: '';
    position: absolute;
    inset: 0;
    z-index: -1;
    background: linear-gradient(
      to bottom,
      rgba(255, 255, 255, 0) 0%,
      rgba(255, 255, 255, 0.6) 26%,
      rgba(255, 255, 255, 0.92) 52%,
      #ffffff 78%
    );
    -webkit-backdrop-filter: blur(9px);
    backdrop-filter: blur(9px);
    /* Fade the blur in too, so the frost has no visible top seam. */
    -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 42%, #000 100%);
    mask-image: linear-gradient(to bottom, transparent 0%, #000 42%, #000 100%);
    border-radius: 0 0 26px 26px;
    pointer-events: none;
  }

  /* ===== Docked Panel (inside #zk-right-dock) ===== */
  .zk-docked {
    position: relative;
    width: 100%;
    height: 100%;
    background: #ffffff;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
  }

  /* Docked Header */
  .zk-docked__header {
    display: flex;
    align-items: center;
    height: 44px;
    padding: 0 10px 0 18px;
    background: transparent;
    border-bottom: 1px solid rgba(16, 24, 40, 0.06);
    flex-shrink: 0;
  }

  .zk-docked__title {
    flex: 1;
    font-weight: 600;
    font-size: 13px;
    color: #16181d;
  }

  /* Docked Hero */
  .zk-docked__hero {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 28px 20px 100px;
  }

  .zk-docked__hero-title {
    font-size: 19px;
    font-weight: 600;
    color: #16181d;
    text-align: center;
    margin-bottom: 16px;
    line-height: 1.3;
    letter-spacing: -0.01em;
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
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-y: contain;
    touch-action: pan-y;
    /* Bottom padding clears the floating composer, as in the bottom card. */
    padding: 16px 16px 96px;
    min-height: 0;
  }

  .zk-docked__messages-inner {
    display: flex;
    flex-direction: column;
    gap: 10px;
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

  /* Docked composer — same floating frosted treatment as the bottom card,
     minus the rounded bottom corners (the dock has square edges). */
  .zk-docked__input {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 2;
    padding: 24px 16px 8px;
    pointer-events: none;
  }

  .zk-docked__input > * {
    pointer-events: auto;
  }

  .zk-docked__input::before {
    content: '';
    position: absolute;
    inset: 0;
    z-index: -1;
    background: linear-gradient(
      to bottom,
      rgba(255, 255, 255, 0) 0%,
      rgba(255, 255, 255, 0.6) 26%,
      rgba(255, 255, 255, 0.92) 52%,
      #ffffff 78%
    );
    -webkit-backdrop-filter: blur(9px);
    backdrop-filter: blur(9px);
    -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 42%, #000 100%);
    mask-image: linear-gradient(to bottom, transparent 0%, #000 42%, #000 100%);
    pointer-events: none;
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
    max-width: 88%;
    animation: zk-fade-in 150ms ease;
    /* contain:content implies paint containment, which clips a hovered
       card's lift shadow at the message's edge. Layout+style keeps the
       isolation benefit without the clipping. */
    contain: layout style;
  }

  @keyframes zk-fade-in {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .zk-message-user {
    align-self: flex-end;
  }

  /* The 88% cap above is a chat-bubble width — right for the user's grey
     bubble, wrong for assistant turns, whose text has no bubble and whose
     carousels need the full column. Capping them left a dead gutter to the
     right of every product/service/room grid. */
  .zk-message-assistant {
    align-self: flex-start;
    max-width: 100%;
    width: 100%;
  }

  .zk-message-content {
    padding: 10px 14px;
    border-radius: 18px;
    font-size: 14px;
    line-height: 1.45;
  }

  .zk-message-user .zk-message-content {
    background: #f0f0f0;
    color: #1f2937;
    border-bottom-right-radius: 4px;
  }

  .zk-message-assistant .zk-message-content {
    background: transparent;
    color: #1f2937;
    padding-left: 0;
    padding-right: 0;
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
    /* SBAL-Z6: 20px only reserves room for a single-digit marker box —
       a 2-digit "10." etc. overflowed it and got clipped against the
       <li> content edge, rendering as "I0.", "I1." (the right stroke of
       a clipped "1"). list-style-position makes the reservation explicit
       instead of relying on the marker fitting in whatever padding is left. */
    padding-left: 28px;
    list-style-position: outside;
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

  /* Registering the angle lets it interpolate smoothly — an unregistered
     custom property animates in discrete jumps. */
  @property --border-angle {
    syntax: '<angle>';
    inherits: false;
    initial-value: 0deg;
  }

  .zk-input-container {
    position: relative;
    background: rgba(16, 24, 40, 0.07);
    border-radius: 999px;
    padding: 1px;
    isolation: isolate;
  }

  /* Animated brand sweep — a thin, low-contrast green arc travelling the
     border. Kept faint on purpose: it should register as a glint, not a
     glowing outline. */
  .zk-input-container::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 1px;
    background: conic-gradient(
      from var(--border-angle),
      transparent 0%,
      transparent 14%,
      rgba(168, 248, 203, 0.55) 18%,
      rgba(74, 222, 128, 0.75) 21%,
      rgba(26, 169, 95, 0.55) 24%,
      transparent 28%,
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
    animation: rotate-border 7s linear infinite;
    pointer-events: none;
  }

  /* Matching bloom behind the sweep, barely there. */
  .zk-input-container::after {
    content: '';
    position: absolute;
    inset: -1px;
    border-radius: inherit;
    background: conic-gradient(
      from var(--border-angle),
      transparent 0%,
      transparent 14%,
      rgba(74, 222, 128, 0.7) 21%,
      transparent 28%,
      transparent 100%
    );
    filter: blur(7px);
    opacity: 0.22;
    z-index: -1;
    animation: rotate-border 7s linear infinite;
    pointer-events: none;
  }

  @keyframes rotate-border {
    0%   { --border-angle: 0deg; }
    100% { --border-angle: 360deg; }
  }

  @media (prefers-reduced-motion: reduce) {
    .zk-input-container::before,
    .zk-input-container::after {
      animation: none;
    }
  }

  .zk-input-inner {
    position: relative;
    background: #f4f4f5;
    border-radius: 999px;
    padding: 6px 6px 6px 10px;
    min-height: 48px;
    display: flex;
    align-items: center;
    gap: 12px;
    transition: background 150ms ease;
  }

  .zk-input-inner:focus-within {
    background: #f0f1f3;
  }

  .zk-input-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: none;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #9ca3af;
    flex-shrink: 0;
    transition: color 150ms, background 150ms;
  }

  .zk-input-icon:hover {
    color: #6b7280;
    background: #f3f4f6;
  }

  .zk-input-icon--left {
    margin-left: 2px;
  }

  .zk-input-icon--right {
    margin-right: 2px;
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
    margin: 0;
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
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: radial-gradient(circle at 32% 26%,
      #4ade80 0%, #1aa95f 52%, #0a7f47 100%);
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: filter 150ms, transform 150ms;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(10, 127, 71, 0.32);
  }

  .zk-send:hover:not(:disabled) {
    filter: brightness(1.08);
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
    display: none; /* hidden on desktop by default */
  }

  /* Desktop FAB pill — shown on scroll down or after minimize */
  .zk-fab--desktop {
    display: flex !important;
    align-items: center;
    gap: 12px;
    position: fixed;
    bottom: 24px;
    right: 24px;
    height: 56px;
    padding: 0 24px 0 9px;
    border-radius: 999px;
    border: 1px solid rgba(16, 24, 40, 0.06);
    background: #ffffff;
    color: #16181d;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 16px;
    font-weight: 500;
    letter-spacing: -0.01em;
    box-shadow:
      0 10px 32px rgba(16, 24, 40, 0.12),
      0 2px 6px rgba(16, 24, 40, 0.06);
    z-index: 9999;
    cursor: pointer;
    opacity: 0;
    transform: scale(0.94);
    transition: opacity 250ms ease, transform 250ms ease, box-shadow 180ms ease;
  }

  .zk-fab--desktop.zk-fab--visible {
    opacity: 1;
    transform: scale(1);
  }

  .zk-fab--desktop:hover {
    box-shadow:
      0 14px 40px rgba(16, 24, 40, 0.16),
      0 2px 6px rgba(16, 24, 40, 0.06);
    transform: translateY(-1px) scale(1.01);
  }

  .zk-fab--desktop .zk-fab__label {
    display: inline;
  }

  .zk-fab__label {
    display: none; /* hidden on mobile FAB */
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
    padding: 0 !important;
    border-radius: 50%;
    border: none;
    background: #ffffff;
    color: #16181d;
    box-shadow:
      0 8px 24px rgba(16, 24, 40, 0.16),
      0 2px 6px rgba(16, 24, 40, 0.06);
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

  .zk-mobile .zk-fab__label {
    display: none !important;
  }

  /* Mobile FAB is the orb itself */
  .zk-mobile .zk-fab .zk-orb {
    width: 40px !important;
    height: 40px !important;
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

  /* The desktop card hugs its content (flex 0), but the mobile sheet has a
     fixed 60vh height — restore flex growth there so the input stays
     pinned to the bottom of the sheet instead of floating mid-panel. */
  .zk-mobile .zk-expanded-panel__hero {
    flex: 1 1 auto !important;
  }

  .zk-mobile .zk-expanded-panel__messages {
    flex: 1 1 auto !important;
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
  /* Mobile keeps the composer in flow as a solid bar — the floating
     frosted treatment is desktop-only. */
  .zk-mobile .zk-expanded-panel__input {
    position: static !important;
    flex-shrink: 0 !important;
    padding: 8px 10px !important;
    padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px)) !important;
    background: #fff !important;
    border-top: 1px solid #e5e7eb !important;
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
    -webkit-mask-image: none !important;
    mask-image: none !important;
    pointer-events: auto !important;
  }

  .zk-mobile .zk-input-container {
    border-radius: 16px !important;
    background: transparent !important;
    padding: 0 !important;
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
  .zk-mobile .zk-md .zk-list { padding-left: 24px !important; }

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
    gap: 8px;
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
    width: 160px;
    scroll-snap-align: start;
    background: white;
    border-radius: 10px;
    overflow: hidden;
    cursor: pointer;
    transition: transform 150ms, box-shadow 150ms;
  }

  .zk-product-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  }

  .zk-product-card__image {
    position: relative;
    width: 100%;
    height: 200px;
    background: #f5f5f5;
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
    bottom: 6px;
    left: 6px;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 9px;
    font-weight: 600;
    background: rgba(0, 0, 0, 0.6);
    color: white;
    backdrop-filter: blur(4px);
  }

  .zk-product-card__badge--in {
    display: none;
  }

  .zk-product-card__badge--out {
    background: rgba(0, 0, 0, 0.6);
    color: white;
  }

  .zk-product-card__info {
    padding: 8px 8px 10px;
  }

  .zk-product-card__name {
    font-size: 12px;
    font-weight: 500;
    color: #111827;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-bottom: 4px;
  }

  .zk-product-card__price-row {
    display: flex;
    align-items: baseline;
    gap: 4px;
    margin-bottom: 0;
  }

  .zk-product-card__price {
    font-size: 13px;
    font-weight: 600;
    color: #111827;
  }

  .zk-product-card__original-price {
    font-size: 10px;
    color: #9ca3af;
    text-decoration: line-through;
  }

  .zk-room-card__amenities {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }

  .zk-room-card__amenity {
    font-size: 10px;
    padding: 1px 6px;
    background: #f0f4ff;
    color: #4b5563;
    border-radius: 4px;
  }

  .zk-room-card__per-night {
    font-size: 10px;
    color: #9ca3af;
    font-weight: 400;
  }

  /* SBAL-Z6: service cards reuse .zk-product-card entirely; a service
     card's actions row has TWO buttons (Book + Details) instead of
     ProductCard/RoomCard's one, so .zk-product-card__actions needs a row
     layout only when it holds more than one button — the single-button
     cases above stay width:100% untouched. */
  .zk-product-card__actions--row {
    display: flex;
    gap: 6px;
  }

  .zk-product-card__actions--row .zk-product-card__add-btn {
    flex: 1;
  }

  .zk-service-card__details-btn {
    flex: 1;
    padding: 5px 0;
    background: white;
    color: #111827;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    transition: border-color 150ms;
    font-family: inherit;
  }

  .zk-service-card__details-btn:hover {
    border-color: #9ca3af;
  }

  .zk-service-card__description {
    font-size: 11px;
    color: #6b7280;
    margin-top: 2px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .zk-feedback {
    display: flex;
    gap: 4px;
    margin-top: 6px;
    justify-content: flex-end;
  }

  .zk-feedback-btn {
    background: none;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 3px 6px;
    cursor: pointer;
    color: #9ca3af;
    display: flex;
    align-items: center;
    transition: color 150ms, border-color 150ms;
  }

  .zk-feedback-btn:hover {
    color: #374151;
    border-color: #9ca3af;
  }

  .zk-feedback-thanks {
    font-size: 11px;
    color: #9ca3af;
    margin-top: 6px;
    display: block;
    text-align: right;
  }

  .zk-product-card__actions {
    margin-top: 6px;
  }

  .zk-product-card__add-btn {
    width: 100%;
    padding: 5px 0;
    background: #111827;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 150ms;
    font-family: inherit;
  }

  .zk-product-card__add-btn:hover:not(:disabled) {
    opacity: 0.85;
  }

  .zk-product-card__add-btn:disabled {
    background: #d1d5db;
    cursor: not-allowed;
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

  /* ===== Wishlist Bookmark Button (on product card) ===== */
  .zk-product-card__wishlist-btn {
    position: absolute;
    top: 6px;
    right: 6px;
    width: 26px;
    height: 26px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(4px);
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    transition: color 150ms, background 150ms;
    z-index: 1;
  }

  .zk-product-card__wishlist-btn:hover {
    color: #111827;
    background: white;
  }

  /* ===== Wishlist View ===== */
  .zk-wishlist-view {
    margin-top: 8px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
  }

  .zk-wishlist-view--empty {
    padding: 16px;
    text-align: center;
    color: #6b7280;
    font-size: 13px;
  }

  .zk-wishlist-view__header {
    padding: 10px 12px;
    background: #fef3c7;
    border-bottom: 1px solid #fde68a;
  }

  .zk-wishlist-view__title {
    font-size: 13px;
    font-weight: 600;
    color: #92400e;
  }

  .zk-wishlist-view__items {
    max-height: 240px;
    overflow-y: auto;
  }

  .zk-wishlist-view__item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid #f3f4f6;
  }

  .zk-wishlist-view__item:last-child {
    border-bottom: none;
  }

  .zk-wishlist-view__thumb {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
  }

  .zk-wishlist-view__item-info {
    flex: 1;
    min-width: 0;
  }

  .zk-wishlist-view__item-name {
    font-size: 13px;
    font-weight: 500;
    color: #111827;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .zk-wishlist-view__item-price {
    font-size: 13px;
    font-weight: 600;
    color: #111827;
    margin-top: 2px;
    display: flex;
    align-items: baseline;
    gap: 6px;
  }

  .zk-wishlist-view__original-price {
    font-size: 11px;
    color: #9ca3af;
    text-decoration: line-through;
    font-weight: 400;
  }

  .zk-wishlist-view__actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }

  .zk-wishlist-view__cart-btn {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: ${primaryColor}15;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: ${primaryColor};
    transition: background 150ms;
  }

  .zk-wishlist-view__cart-btn:hover {
    background: ${primaryColor}25;
  }

  .zk-wishlist-view__remove-btn {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #f3f4f6;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #9ca3af;
    transition: background 150ms, color 150ms;
  }

  .zk-wishlist-view__remove-btn:hover {
    background: #fee2e2;
    color: #ef4444;
  }

  /* ===== Address Form ===== */
  .zk-address-form {
    margin-top: 8px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
  }

  .zk-address-form__header {
    padding: 10px 12px;
    background: #eff6ff;
    border-bottom: 1px solid #dbeafe;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .zk-address-form__title {
    font-size: 14px;
    font-weight: 600;
    color: #1e40af;
  }

  .zk-address-form__summary {
    font-size: 12px;
    color: #3b82f6;
    font-weight: 500;
  }

  .zk-address-form__section {
    padding: 10px 12px;
  }

  .zk-address-form__section-title {
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }

  .zk-address-form__field {
    margin-bottom: 8px;
  }

  .zk-address-form__field--half {
    flex: 1;
    min-width: 0;
  }

  .zk-address-form__row {
    display: flex;
    gap: 8px;
  }

  .zk-address-form__label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: #374151;
    margin-bottom: 3px;
  }

  .zk-address-form__required {
    color: #ef4444;
    margin-left: 2px;
  }

  .zk-address-form__input {
    width: 100%;
    padding: 7px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    color: #111827;
    background: white;
    font-family: inherit;
    transition: border-color 150ms;
    box-sizing: border-box;
  }

  .zk-address-form__input:focus {
    border-color: ${primaryColor};
    outline: none;
    box-shadow: 0 0 0 2px ${primaryColor}20;
  }

  .zk-address-form__input--error {
    border-color: #ef4444;
  }

  .zk-address-form__error {
    font-size: 11px;
    color: #ef4444;
    margin-top: 2px;
    display: block;
  }

  .zk-address-form__checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: #374151;
    cursor: pointer;
  }

  .zk-address-form__checkbox input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: ${primaryColor};
  }

  /* Payment method options */
  .zk-address-form__payment-options {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .zk-address-form__payment-option {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 150ms, background 150ms;
  }

  .zk-address-form__payment-option:hover {
    border-color: #d1d5db;
    background: #f9fafb;
  }

  .zk-address-form__payment-option--active {
    border-color: ${primaryColor};
    background: ${primaryColor}08;
  }

  .zk-address-form__payment-option input[type="radio"] {
    display: none;
  }

  .zk-address-form__payment-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background: #f3f4f6;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    flex-shrink: 0;
  }

  .zk-address-form__payment-option--active .zk-address-form__payment-icon {
    background: ${primaryColor}15;
    color: ${primaryColor};
  }

  .zk-address-form__payment-label {
    font-size: 13px;
    font-weight: 600;
    color: #111827;
  }

  .zk-address-form__payment-desc {
    font-size: 11px;
    color: #6b7280;
    margin-top: 1px;
  }

  .zk-address-form__submit {
    width: calc(100% - 24px);
    margin: 4px 12px 12px;
    padding: 10px;
    background: ${primaryColor};
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 150ms;
    font-family: inherit;
  }

  .zk-address-form__submit:hover:not(:disabled) {
    opacity: 0.9;
  }

  .zk-address-form__submit:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* ===== Payment Pending ===== */
  .zk-payment-pending {
    margin-top: 8px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
  }

  .zk-payment-pending__spinner {
    display: flex;
    justify-content: center;
    margin-bottom: 12px;
    color: ${primaryColor};
    animation: zk-spin 1.5s linear infinite;
  }

  @keyframes zk-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .zk-payment-pending__text {
    font-size: 14px;
    font-weight: 500;
    color: #374151;
    margin-bottom: 8px;
  }

  .zk-payment-pending__link {
    font-size: 12px;
    color: ${primaryColor};
    text-decoration: none;
  }

  .zk-payment-pending__link:hover {
    text-decoration: underline;
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
