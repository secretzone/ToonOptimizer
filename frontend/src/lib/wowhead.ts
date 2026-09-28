// Glue for Wowhead's tooltip script (see index.html: wow.zamimg.com/js/tooltips.js).
// The script only scans the DOM for [data-wowhead] elements once, on load, so anything we
// render afterwards (job results, list re-renders) needs an explicit refreshLinks() call.
import { useEffect, useState } from 'react'
import { useStore } from '../store'
import type { Item } from './types'

declare global {
  interface Window {
    $WowheadPower?: { refreshLinks?: () => void }
  }
}

let refreshTimer: ReturnType<typeof setTimeout> | null = null

/** Debounced call to window.$WowheadPower.refreshLinks(). Safe to call many times per render tick. */
function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    refreshTimer = null
    window.$WowheadPower?.refreshLinks?.()
  }, 200)
}

/** Call after a list of items renders or changes, so Wowhead picks up new [data-wowhead] anchors.
 * No-op when the Wowhead tooltips setting is off. */
export function useWowheadRefresh(deps: unknown[]): void {
  const enabled = useStore((s) => s.wowheadTooltips)
  useEffect(() => {
    if (enabled) scheduleRefresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])
}

// ---------- shared "did the script actually load" detection ----------
// A single timer/poll shared by every mounted component, so we don't start dozens of 2s
// timeouts when a page renders many ItemCards.
type ReadyState = 'pending' | 'ready' | 'failed'
let state: ReadyState = 'pending'
let started = false
const listeners = new Set<(s: ReadyState) => void>()

function setState(next: ReadyState) {
  state = next
  listeners.forEach((l) => l(next))
}

function startDetection() {
  if (started) return
  started = true
  if (window.$WowheadPower) {
    setState('ready')
    return
  }
  // Poll briefly (the script can finish loading/initializing a moment after DOMContentLoaded),
  // then give up after ~2s and fall back to our own tooltip.
  const start = Date.now()
  const poll = () => {
    if (window.$WowheadPower) {
      setState('ready')
      return
    }
    if (Date.now() - start >= 2000) {
      setState('failed')
      return
    }
    setTimeout(poll, 150)
  }
  poll()
}

/** True once wow.zamimg.com/js/tooltips.js has loaded and initialized, false if it appears to
 * have failed after a ~2s grace period, null while still waiting. Returns false immediately
 * (without starting detection) when the Wowhead tooltips setting is off. */
export function useWowheadReady(): boolean | null {
  const enabled = useStore((s) => s.wowheadTooltips)
  const [s, setS] = useState<ReadyState>(state)
  useEffect(() => {
    if (!enabled) return
    startDetection()
    listeners.add(setS)
    return () => { listeners.delete(setS) }
  }, [enabled])
  if (!enabled) return false
  if (s === 'pending') return null
  return s === 'ready'
}

/** True whenever Wowhead's tooltip script is turned on and (as far as we can tell) actually
 * loaded and running — used both for the icon's question-mark fallback and for deciding whether
 * to hand an item off to Wowhead's own tooltip vs. our fallback ItemTooltip. */
export function useWowheadActive(item: Pick<Item, 'resolved'> | null | undefined): boolean {
  const enabled = useStore((s) => s.wowheadTooltips)
  const ready = useWowheadReady()
  return !!item && enabled && ready !== false && item.resolved !== false
}
