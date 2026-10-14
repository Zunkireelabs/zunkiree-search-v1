import { Component } from 'react'
import type { ReactNode } from 'react'

interface Props {
  fallbackText: string
  resetKey: string      // a different block gets a fresh chance
  children: ReactNode
}

// One block that fails to render must never take the widget down: it shows its plain-text version instead.
export class BlockErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown) {
    console.error('[zunkiree] a block failed to render; showing its text instead', error)
  }

  componentDidUpdate(prev: Props) {
    if (shouldReset(prev.resetKey, this.props.resetKey, this.state.failed)) this.setState({ failed: false })
  }

  render() {
    if (this.state.failed) return <div className="zk-block__fallback">{this.props.fallbackText}</div>
    return this.props.children
  }
}

export function shouldReset(prevKey: string, nextKey: string, failed: boolean): boolean {
  return failed && prevKey !== nextKey
}
