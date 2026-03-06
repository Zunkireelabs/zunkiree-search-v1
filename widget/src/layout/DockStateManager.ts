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

  // Save the current page scroll position
  savedScrollY = window.scrollY

  root.classList.add(DOCK_ACTIVE_CLASS)

  // After layout reflow: move host-content to the saved scroll position
  // and reset the window scroll (transform changes scroll context)
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.scrollTo(0, 0)
      if (hostContent) {
        hostContent.scrollTop = savedScrollY
      }
    })
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

  // Read current scroll from host-content before removing transform
  if (hostContent) {
    savedScrollY = hostContent.scrollTop
    hostContent.scrollTop = 0
  }

  root?.classList.remove(DOCK_ACTIVE_CLASS)

  // After layout reflow: restore window scroll to the saved position
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.scrollTo(0, savedScrollY)
    })
  })

  if (resizeCleanup) {
    resizeCleanup()
    resizeCleanup = null
  }
}
