import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react'
import { useEffect, useState, type ReactNode, type SelectHTMLAttributes, type InputHTMLAttributes } from 'react'
import { copyText } from '../lib/format'
import { useStore } from '../store'

export function Card({ children, className = '', title, actions }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Field({ label, hint, children, className = '' }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 ${className}`}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </label>
  )
}

export function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`input appearance-none ${className}`} {...rest}>
      {children}
    </select>
  )
}

export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`input ${className}`} {...rest} />
}

export function Toggle({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; description?: ReactNode; disabled?: boolean }) {
  return (
    <label className={`flex cursor-pointer items-start gap-2.5 ${disabled ? 'opacity-50' : ''}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full border transition-colors ${checked ? 'border-accent-dim bg-accent' : 'border-border-strong bg-surface-3'}`}
      >
        <span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-all ${checked ? 'left-[18px]' : 'left-0.5'}`} />
      </button>
      <span className="flex flex-col">
        <span className="text-sm">{label}</span>
        {description && <span className="text-xs text-muted">{description}</span>}
      </span>
    </label>
  )
}

export function Checkbox({ checked, onChange, label, disabled, className = '' }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; disabled?: boolean; className?: string }) {
  return (
    <label className={`flex cursor-pointer items-center gap-2 text-sm ${disabled ? 'opacity-50' : ''} ${className}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 rounded" />
      <span>{label}</span>
    </label>
  )
}

export function Collapsible({ title, children, defaultOpen = false, right }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean; right?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-border">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center justify-between py-2.5 text-left text-sm font-medium hover:text-accent" aria-expanded={open}>
        <span className="flex items-center gap-1.5">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {title}
        </span>
        {right && <span className="text-xs text-muted">{right}</span>}
      </button>
      {open && <div className="pb-3">{children}</div>}
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, tabs, className = '' }: { value: T; onChange: (v: T) => void; tabs: { value: T; label: ReactNode }[]; className?: string }) {
  return (
    <div className={`inline-flex gap-0.5 rounded-lg border border-border bg-bg-soft p-0.5 ${className}`} role="tablist">
      {tabs.map((t) => (
        <button key={t.value} type="button" role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)} className={`tab ${value === t.value ? 'tab-active' : ''}`}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function CopyButton({ text, label = 'Copy', className = '' }: { text: string | (() => Promise<string> | string); label?: string; className?: string }) {
  const [done, setDone] = useState(false)
  const toast = useStore((s) => s.toast)
  return (
    <button
      type="button"
      className={`btn btn-sm ${className}`}
      onClick={async () => {
        const t = typeof text === 'function' ? await text() : text
        const ok = await copyText(t)
        if (ok) {
          setDone(true)
          setTimeout(() => setDone(false), 1500)
        } else toast('Copy failed', 'error')
      }}
    >
      {done ? <Check size={13} className="text-good" /> : <Copy size={13} />}
      {done ? 'Copied' : label}
    </button>
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return <span className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-border-strong border-t-accent ${className}`} />
}

/**
 * Inline two-click delete confirmation: first click swaps the label for a "Confirm" state (auto
 * reverts after a few seconds), second click runs `onConfirm`. Deliberately doesn't rely on
 * `window.confirm()` — several automation tools (incl. the browser tools used to test this app)
 * auto-dismiss native confirm dialogs, which would silently no-op a real delete button.
 */
export function ConfirmButton({
  onConfirm, label = 'Delete', confirmLabel = 'Confirm', icon, className = 'btn-ghost text-muted hover:text-bad', size = 'sm', disabled, title,
}: {
  onConfirm: () => void | Promise<void>
  label?: ReactNode
  confirmLabel?: ReactNode
  icon?: ReactNode
  className?: string
  size?: 'sm' | 'md'
  disabled?: boolean
  title?: string
}) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!confirming) return
    const t = setTimeout(() => setConfirming(false), 4000)
    return () => clearTimeout(t)
  }, [confirming])

  const sizeClass = size === 'sm' ? 'btn-sm' : ''
  return (
    <button
      type="button"
      className={`btn ${sizeClass} ${confirming ? 'btn-danger' : className}`}
      disabled={disabled || busy}
      title={confirming ? undefined : title}
      onClick={async () => {
        if (!confirming) {
          setConfirming(true)
          return
        }
        setBusy(true)
        try {
          await onConfirm()
        } finally {
          setBusy(false)
          setConfirming(false)
        }
      }}
    >
      {busy ? <Spinner /> : icon}
      {busy ? 'Working…' : confirming ? confirmLabel : label}
    </button>
  )
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Stat({ label, value, sub, className = '' }: { label: ReactNode; value: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col ${className}`}>
      <span className="label">{label}</span>
      <span className="text-lg font-semibold tabular-nums">{value}</span>
      {sub && <span className="text-xs text-muted">{sub}</span>}
    </div>
  )
}
