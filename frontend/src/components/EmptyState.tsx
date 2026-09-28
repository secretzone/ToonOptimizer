import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { PackageOpen } from 'lucide-react'

export function EmptyState({ icon, title, body, action, className = '' }: { icon?: ReactNode; title: string; body?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border px-6 py-12 text-center ${className}`}>
      <div className="text-faint">{icon ?? <PackageOpen size={32} strokeWidth={1.5} />}</div>
      <div className="text-sm font-medium">{title}</div>
      {body && <div className="max-w-md text-sm text-muted">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function NeedProfile() {
  return (
    <EmptyState
      title="No character imported"
      body="Import a /simc export or look up a character from the Armory to get started."
      action={<Link to="/" className="btn btn-primary">Go to Import</Link>}
    />
  )
}
