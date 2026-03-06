export const DOCK_MIN_WIDTH = 1200

const LAYOUT_ROOT_ID = 'zk-layout-root'
const HOST_CONTENT_ID = 'zk-host-content'
const DOCK_ACTIVE_CLASS = 'zk-dock-active'

let resizeCleanup: (() => void) | null = null
let savedScrollY = 0

export function enterDock(onForceExit: () => void): void {
  const root = document.getElementById(LAYOUT_ROOT_ID)
  const hostContent = document.getElementById(HOST_CONTENT_ID)
  if (!root) return

  // Save window scroll before switching to host-content scroll
  savedScrollY = window.scrollY

  root.classList.add(DOCK_ACTIVE_CLASS)

  // Transfer scroll from window to host-content container
  window.scrollTo(0, 0)
  if (hostContent) {
    hostContent.scrollTop = savedScrollY
  }

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
  const hostContent = document.getElementById(HOST_CONTENT_ID)

  // Save host-content scroll before switching back to window scroll
  if (hostContent) {
    savedScrollY = hostContent.scrollTop
    hostContent.scrollTop = 0
  }

  root?.classList.remove(DOCK_ACTIVE_CLASS)

  // Transfer scroll from host-content back to window
  window.scrollTo(0, savedScrollY)

  if (resizeCleanup) {
    resizeCleanup()
    resizeCleanup = null
  }
}
