import { useCallback } from 'react'
import { cancelJob, runJob, useStore, type PageKey } from '../store'
import { isTerminal } from '../lib/api'
import type { Job } from '../lib/types'

/** Per-page job state + submit/cancel. Results survive navigation because they live in the store. */
export function usePageJob(page: PageKey) {
  const state = useStore((s) => s.pages[page])
  const clear = useStore((s) => s.clearPage)
  const run = useCallback((submit: () => Promise<Job>, opts?: { fetchResult?: boolean }) => runJob(page, submit, opts), [page])
  const cancel = useCallback(() => cancelJob(page), [page])
  const running = !!state.job && !isTerminal(state.job)
  return { ...state, running, run, cancel, clear: () => clear(page) }
}
