export const DOCK_MIN_WIDTH = 1200

const LAYOUT_ROOT_ID = 'zk-layout-root'
const DOCK_ACTIVE_CLASS = 'zk-dock-active'

let resizeCleanup: (() => void) | null = null

export function enterDock(onForceExit: () => void): void {
  const root = document.getElementById(LAYOUT_ROOT_ID)
  if (!root) return

  root.classList.add(DOCK_ACTIVE_CLASS)

  // Force body and html to 70% width so position:fixed elements shrink too
  document.documentElement.style.width = '70%'
  document.documentElement.style.overflowX = 'hidden'
  document.body.style.width = '100%'

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

  // Restore body and html to full width
  document.documentElement.style.width = ''
  document.documentElement.style.overflowX = ''
  document.body.style.width = ''

  if (resizeCleanup) {
    resizeCleanup()
    resizeCleanup = null
  }
}
