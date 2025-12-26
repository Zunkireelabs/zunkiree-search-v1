// Combined CSS Styles for Zunkiree Search Widget v2
import { generateCSSVariables } from './tokens';

export const getStyles = (primaryColor: string): string => `
  /* CSS Custom Properties */
  :root {
    ${generateCSSVariables(primaryColor)}
  }

  /* Reset & Base */
  .zk-widget * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  .zk-widget {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 15px;
    line-height: 1.5;
    color: #111827;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  /* Container Modes */
  .zk-container {
    width: 100%;
  }

  .zk-container--hero {
    max-width: 640px;
    margin: 0 auto;
    padding: 24px;
  }

  .zk-container--inline {
    max-width: 100%;
    padding: 16px;
  }

  .zk-container--floating {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 360px;
    z-index: 9999;
  }

  /* ==================== SEARCH BAR ==================== */
  .zk-search-bar {
    display: flex;
    align-items: center;
    width: 100%;
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    transition: all 150ms ease-in-out;
  }

  .zk-search-bar--hero {
    height: 56px;
    padding: 0 8px 0 16px;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
  }

  .zk-search-bar--inline {
    height: 48px;
    padding: 0 6px 0 14px;
    border-radius: 8px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .zk-search-bar--floating {
    height: 44px;
    padding: 0 6px 0 14px;
    border-radius: 9999px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  }

  .zk-search-bar--pill {
    border-radius: 9999px !important;
  }

  .zk-search-bar:hover {
    border-color: #D1D5DB;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.04);
  }

  .zk-search-bar:focus-within {
    border-color: var(--zk-primary);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1), 0 0 0 3px var(--zk-primary-light);
  }

  .zk-search-icon {
    width: 20px;
    height: 20px;
    color: #9CA3AF;
    flex-shrink: 0;
    margin-right: 12px;
  }

  .zk-search-input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 16px;
    font-family: inherit;
    color: #111827;
    background: transparent;
    min-width: 0;
  }

  .zk-search-input::placeholder {
    color: #9CA3AF;
  }

  .zk-search-clear {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    margin-right: 8px;
    border: none;
    background: #F3F4F6;
    border-radius: 50%;
    color: #6B7280;
    cursor: pointer;
    transition: all 150ms ease-in-out;
  }

  .zk-search-clear:hover {
    background: #E5E7EB;
    color: #111827;
  }

  .zk-search-button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 10px 20px;
    background: var(--zk-primary);
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background 150ms ease-in-out;
  }

  .zk-search-button:hover {
    background: var(--zk-primary-hover);
  }

  .zk-search-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .zk-search-button--icon-only {
    padding: 10px;
    border-radius: 8px;
  }

  .zk-search-button--pill {
    border-radius: 9999px;
  }

  /* ==================== POWERED BY ==================== */
  .zk-powered-by {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    margin-top: 12px;
    font-size: 12px;
    color: #9CA3AF;
  }

  .zk-powered-by__icon {
    font-size: 14px;
  }

  .zk-powered-by__link {
    color: var(--zk-primary);
    text-decoration: none;
    font-weight: 500;
  }

  .zk-powered-by__link:hover {
    text-decoration: underline;
  }

  /* ==================== QUICK ACTIONS ==================== */
  .zk-quick-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 16px;
  }

  .zk-chip {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    background: transparent;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    font-family: inherit;
    color: #6B7280;
    cursor: pointer;
    transition: all 150ms ease-in-out;
  }

  .zk-chip:hover {
    background: #F9FAFB;
    border-color: #D1D5DB;
    color: #111827;
  }

  .zk-chip:active {
    background: #F3F4F6;
  }

  /* ==================== RESULTS PANEL ==================== */
  .zk-results-panel {
    margin-top: 8px;
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.05);
    overflow: hidden;
    animation: zk-fade-in 200ms ease-out;
  }

  .zk-result-card {
    padding: 20px;
  }

  .zk-result-content {
    font-size: 15px;
    line-height: 1.625;
    color: #111827;
    white-space: pre-wrap;
  }

  .zk-result-content p {
    margin-bottom: 12px;
  }

  .zk-result-content p:last-child {
    margin-bottom: 0;
  }

  /* ==================== SOURCES ==================== */
  .zk-sources {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #E5E7EB;
  }

  .zk-sources__label {
    font-size: 12px;
    font-weight: 500;
    color: #6B7280;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .zk-source-link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #F9FAFB;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    color: #6B7280;
    text-decoration: none;
    transition: all 150ms ease-in-out;
    margin-right: 8px;
    margin-bottom: 8px;
  }

  .zk-source-link:hover {
    background: #F3F4F6;
    color: #111827;
  }

  .zk-source-link__icon {
    width: 14px;
    height: 14px;
  }

  /* ==================== FOLLOW UP SUGGESTIONS ==================== */
  .zk-follow-up {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #E5E7EB;
  }

  .zk-follow-up__label {
    width: 100%;
    font-size: 12px;
    font-weight: 500;
    color: #6B7280;
    margin-bottom: 4px;
  }

  /* ==================== LOADING STATE ==================== */
  .zk-loading {
    padding: 20px;
  }

  .zk-skeleton {
    background: linear-gradient(90deg, #F3F4F6 25%, #E5E7EB 50%, #F3F4F6 75%);
    background-size: 200% 100%;
    animation: zk-shimmer 1.5s infinite;
    border-radius: 4px;
  }

  .zk-skeleton--line {
    height: 16px;
    margin-bottom: 12px;
  }

  .zk-skeleton--line:nth-child(1) { width: 90%; }
  .zk-skeleton--line:nth-child(2) { width: 75%; }
  .zk-skeleton--line:nth-child(3) { width: 60%; }
  .zk-skeleton--line:last-child { margin-bottom: 0; }

  /* ==================== ERROR STATE ==================== */
  .zk-error {
    padding: 20px;
    text-align: center;
  }

  .zk-error__icon {
    width: 48px;
    height: 48px;
    margin: 0 auto 12px;
    color: #EF4444;
  }

  .zk-error__title {
    font-size: 16px;
    font-weight: 600;
    color: #111827;
    margin-bottom: 4px;
  }

  .zk-error__message {
    font-size: 14px;
    color: #6B7280;
    margin-bottom: 16px;
  }

  .zk-error__retry {
    padding: 8px 16px;
    background: var(--zk-primary);
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background 150ms ease-in-out;
  }

  .zk-error__retry:hover {
    background: var(--zk-primary-hover);
  }

  /* ==================== SPINNER ==================== */
  .zk-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid #FFFFFF;
    border-top-color: transparent;
    border-radius: 50%;
    animation: zk-spin 0.8s linear infinite;
  }

  /* ==================== ANIMATIONS ==================== */
  @keyframes zk-fade-in {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes zk-shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }

  @keyframes zk-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* ==================== ACCESSIBILITY ==================== */
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .zk-chip:focus-visible,
  .zk-search-button:focus-visible,
  .zk-source-link:focus-visible {
    outline: 2px solid var(--zk-primary);
    outline-offset: 2px;
  }

  /* ==================== RESPONSIVE ==================== */
  @media (max-width: 639px) {
    .zk-container--hero {
      padding: 16px;
    }

    .zk-search-bar--hero {
      height: 48px;
    }

    .zk-search-button__text {
      display: none;
    }

    .zk-search-button {
      padding: 10px;
    }

    .zk-quick-actions {
      justify-content: flex-start;
      overflow-x: auto;
      flex-wrap: nowrap;
      padding-bottom: 8px;
      -webkit-overflow-scrolling: touch;
    }

    .zk-chip {
      flex-shrink: 0;
    }

    .zk-container--floating {
      width: calc(100% - 32px);
      left: 16px;
      right: 16px;
    }
  }

  /* ==================== REDUCED MOTION ==================== */
  @media (prefers-reduced-motion: reduce) {
    .zk-results-panel {
      animation: none;
    }

    .zk-skeleton {
      animation: none;
      background: #F3F4F6;
    }

    .zk-spinner {
      animation: none;
    }
  }
`;

export default getStyles;
