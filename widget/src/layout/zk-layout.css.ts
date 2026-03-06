/**
 * Layout CSS for the dock architecture.
 * Injected once at bootstrap, removed on destroy.
 */
export const ZK_LAYOUT_CSS = `
  #zk-layout-root {
    width: 100%;
    min-height: 100vh;
  }

  #zk-host-content {
    transition: width 300ms ease, margin-right 300ms ease;
  }

  #zk-dock-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 0;
    overflow: hidden;
    z-index: 99999;
    transition: width 300ms ease;
  }

  /* When docked: squeeze entire page to 70%, dock panel takes 30% on right */
  #zk-layout-root.zk-dock-active #zk-host-content {
    width: 70% !important;
    max-width: 70% !important;
  }

  #zk-layout-root.zk-dock-active #zk-dock-panel {
    width: 30%;
    border-left: 1px solid rgba(0, 0, 0, 0.08);
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.06);
  }
`
