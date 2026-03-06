export const DOCK_MIN_WIDTH = 1200

const LAYOUT_ROOT_ID = 'zk-layout-root'
const HOST_CONTENT_ID = 'zk-host-content'
const DOCK_ACTIVE_CLASS = 'zk-dock-active'

let resizeCleanup: (() => void) | null = null

export function enterDock(onForceExit: () => void): void {
  const root = document.getElementById(LAYOUT_ROOT_ID)
  if (!root) return

  root.classList.add(DOCK_ACTIVE_CLASS)

  // Remove any html/body width overrides from previous approach
  document.documentElement.style.width = ''
  document.documentElement.style.overflowX = ''
  document.body.style.width = ''

  const handleResize = () => {
    if (window.innerWidth < DOCK_MIN_WIDTH) {
      exitDock()
      onForceExit()
    }
  }

  window.addEventListener('resize', handleResize)
  resizeCleanup = () => window.removeEventListener('resize', handleResize)
}

export function exitDock(): void {
  const root = document.getElementById(LAYOUT_ROOT_ID)
  root?.classList.remove(DOCK_ACTIVE_CLASS)

  if (resizeCleanup) {
    resizeCleanup()
    resizeCleanup = null
  }
}
