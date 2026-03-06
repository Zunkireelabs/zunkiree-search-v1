/**
 * Layout CSS for the dock architecture.
 * Injected once at bootstrap, removed on destroy.
 */
export const ZK_LAYOUT_CSS = `
  #zk-layout-root {
    display: flex;
    width: 100%;
    min-height: 100vh;
  }

  #zk-host-content {
    flex: 1;
    min-width: 0;
    transition: flex 300ms ease;
  }

  #zk-dock-panel {
    position: sticky;
    top: 0;
    height: 100vh;
    align-self: flex-start;
    width: 0;
    flex-shrink: 0;
    overflow: hidden;
    z-index: 99999;
    transition: width 300ms ease;
  }

  /* When docked: website takes 70% on left, Zunkiree takes 30% on right */
  #zk-layout-root.zk-dock-active #zk-host-content {
    flex: none;
    width: 70%;
    overflow-x: hidden;
  }

  #zk-layout-root.zk-dock-active #zk-dock-panel {
    width: 30%;
    border-left: 1px solid rgba(0, 0, 0, 0.08);
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.06);
  }
`
