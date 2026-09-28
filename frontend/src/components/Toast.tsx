import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react'
import { useStore } from '../store'

export function ToastHost() {
  const toasts = useStore((s) => s.toasts)
  const dismiss = useStore((s) => s.dismissToast)
  if (!toasts.length) return null
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm shadow-lg backdrop-blur ${
            t.kind === 'error' ? 'border-red-900/60 bg-red-950/80 text-red-100' : t.kind === 'success' ? 'border-emerald-900/60 bg-emerald-950/80 text-emerald-100' : 'border-border bg-surface-2/95 text-text'
          }`}
        >
          <span className="mt-0.5 shrink-0">
            {t.kind === 'error' ? <AlertCircle size={15} /> : t.kind === 'success' ? <CheckCircle2 size={15} /> : <Info size={15} />}
          </span>
          <span className="flex-1 break-words">{t.text}</span>
          <button type="button" onClick={() => dismiss(t.id)} className="shrink-0 opacity-60 hover:opacity-100" aria-label="Dismiss">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}
