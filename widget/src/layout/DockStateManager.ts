export const DOCK_MIN_WIDTH = 1200

const LAYOUT_ROOT_ID = 'zk-layout-root'
const DOCK_ACTIVE_CLASS = 'zk-dock-active'

let resizeCleanup: (() => void) | null = null

export function enterDock(onForceExit: () => void): void {
  const root = document.getElementById(LAYOUT_ROOT_ID)
  if (!root) return

  // 1. Save current scroll position
  const scrollY = window.scrollY

  // 2. Toggle dock class (applies transform)
  root.classList.add(DOCK_ACTIVE_CLASS)

  // 3. Force reflow so transform is applied
  void root.offsetHeight

  // 4. Restore scroll immediately (prevents jump)
  window.scrollTo(0, scrollY)

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

  // 1. Save current scroll position
  const scrollY = window.scrollY

  // 2. Remove dock class (removes transform)
  root?.classList.remove(DOCK_ACTIVE_CLASS)

  // 3. Force reflow so transform is removed
  if (root) void root.offsetHeight

  // 4. Restore scroll immediately (prevents jump)
  window.scrollTo(0, scrollY)

  if (resizeCleanup) {
    resizeCleanup()
    resizeCleanup = null
  }
}
