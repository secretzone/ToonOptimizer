import { MOCK } from '../lib/api'

/** Unmissable, non-dismissible warning shown on every page when `VITE_MOCK=1` (or `--mode mock`)
 * is active, so a mock-mode dev server is never mistaken for one talking to the real backend —
 * everything imported or simmed here only touches in-memory fixtures (lib/mock.ts), never the
 * real `characters/`/`reports/` on disk. `MOCK` is a build-time constant (`import.meta.env`), so
 * in a real `npm run build` (VITE_MOCK unset) this whole component is dead code and the banner
 * text is stripped from the bundle entirely, not just hidden at runtime. */
export function MockBanner() {
  if (!MOCK) return null
  return (
    <div className="w-full shrink-0 border-b border-amber-900/60 bg-amber-500 px-4 py-1.5 text-center text-xs font-semibold text-black sm:text-sm">
      MOCK DATA — this window is not connected to your backend. Nothing you import or sim here is real. Open{' '}
      <a
        href="http://localhost:5173"
        className="underline decoration-black/60 underline-offset-2 hover:decoration-black"
        target="_blank"
        rel="noreferrer"
      >
        http://localhost:5173
      </a>
    </div>
  )
}
