export const DOCK_MIN_WIDTH = 1200

const LAYOUT_ROOT_ID = 'zk-layout-root'
const HOST_CONTENT_ID = 'zk-host-content'
const DOCK_ACTIVE_CLASS = 'zk-dock-active'

let resizeCleanup: (() => void) | null = null

export function enterDock(onForceExit: () => void): void {
  const root = document.getElementById(LAYOUT_ROOT_ID)
  if (!root) return

  // Save scroll position before layout change
  const scrollY = window.scrollY
  const hostContent = document.getElementById(HOST_CONTENT_ID)

  root.classList.add(DOCK_ACTIVE_CLASS)

  // Restore scroll position after layout reflow
  // The transform on host-content changes the scroll context,
  // so we restore on the host-content element itself
  requestAnimationFrame(() => {
    if (hostContent) {
      hostContent.scrollTop = scrollY
    }
    window.scrollTo(0, 0)
  })

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

  // Save host-content scroll position before undocking
  const hostScrollY = hostContent ? hostContent.scrollTop : 0

  root?.classList.remove(DOCK_ACTIVE_CLASS)

  // Restore scroll position on window after transform is removed
  requestAnimationFrame(() => {
    window.scrollTo(0, hostScrollY)
  })

  if (resizeCleanup) {
    resizeCleanup()
    resizeCleanup = null
  }
}
