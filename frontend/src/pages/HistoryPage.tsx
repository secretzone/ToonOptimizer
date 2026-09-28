import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { ExternalLink, RefreshCw, Trash2, History as HistoryIcon } from 'lucide-react'
import { api } from '../lib/api'
import { ensureProfileLoaded, openHistoryJob, useStore, type PageKey } from '../store'
import { fmtDate } from '../lib/format'
import { CLASS_COLORS, JOB_TYPE_LABELS, JOB_TYPE_ROUTES, titleCase } from '../lib/wow'
import { Card, PageTitle, Spinner } from '../components/ui'
import { EmptyState } from '../components/EmptyState'
import type { CharacterSummary, HistoryEntry } from '../lib/types'

export function HistoryPage() {
  const navigate = useNavigate()
  const toast = useStore((s) => s.toast)
  const profile = useStore((s) => s.profile)
  const [rows, setRows] = useState<HistoryEntry[] | null>(null)
  const [characters, setCharacters] = useState<CharacterSummary[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = () => api.history().then(setRows).catch((e: Error) => { toast(e.message, 'error'); setRows([]) })
  useEffect(() => {
    void load()
    api.characters().then(setCharacters).catch(() => setCharacters([]))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const open = async (h: HistoryEntry) => {
    const route = JOB_TYPE_ROUTES[h.type]
    if (!route) return
    setBusy(h.id)
    try {
      // Load the job's character into the store first (same path as Reports' "Load this
      // character") so the sim page it lands on doesn't render NeedProfile.
      const match = h.character ? characters?.find((c) => c.name.toLowerCase() === h.character!.toLowerCase()) : undefined
      if (match) {
        try {
          await ensureProfileLoaded(match.slug)
        } catch (e) {
          toast((e as Error).message, 'error')
        }
      }
      await openHistoryJob(h.type as PageKey, h.id)
      navigate(route)
    } catch {
      /* toast already shown */
    } finally {
      setBusy(null)
    }
  }
  const remove = async (h: HistoryEntry) => {
    if (!confirm(`Delete ${JOB_TYPE_LABELS[h.type] ?? h.type}${h.character ? ` for ${h.character}` : ''} from ${fmtDate(h.created) || 'an unknown date'}?`)) return
    setBusy(h.id)
    try {
      await api.deleteHistory(h.id)
      setRows((r) => r?.filter((x) => x.id !== h.id) ?? null)
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <PageTitle title="History" subtitle="Finished jobs kept on disk by the backend." actions={<button type="button" className="btn" onClick={load}><RefreshCw size={14} /> Refresh</button>} />
      {rows === null ? (
        <div className="flex items-center gap-2 text-muted"><Spinner /> Loading…</div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<HistoryIcon size={32} strokeWidth={1.5} />} title="No history yet" body="Every finished sim is recorded here so you can reopen it later." />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted">
                <th className="px-2 py-1.5">Type</th>
                <th className="px-2 py-1.5">Character</th>
                <th className="px-2 py-1.5">Spec</th>
                <th className="px-2 py-1.5">Date</th>
                <th className="px-2 py-1.5">Summary</th>
                <th className="px-2 py-1.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h) => {
                const color = profile && profile.name === h.character ? CLASS_COLORS[profile.klass] : undefined
                return (
                  <tr key={h.id} className="border-b border-border/50 hover:bg-surface-2">
                    <td className="px-2 py-2"><span className="chip">{JOB_TYPE_LABELS[h.type] ?? h.type}</span></td>
                    <td className="px-2 py-2 font-medium" style={{ color }}>{h.character || '—'}</td>
                    <td className="px-2 py-2 text-muted">{h.spec ? titleCase(h.spec) : '—'}</td>
                    <td className="px-2 py-2 whitespace-nowrap text-muted">{fmtDate(h.created) || '—'}</td>
                    <td className="max-w-md truncate px-2 py-2 text-muted" title={h.summary}>{h.summary}</td>
                    <td className="px-2 py-2">
                      <div className="flex justify-end gap-1">
                        <button type="button" className="btn btn-sm" disabled={busy === h.id || !JOB_TYPE_ROUTES[h.type]} onClick={() => open(h)}>
                          {busy === h.id ? <Spinner /> : <ExternalLink size={13} />} Open
                        </button>
                        <a className="btn btn-sm btn-ghost" href={api.reportUrl(h.id)} target="_blank" rel="noreferrer" title="Open HTML report">Report</a>
                        <button type="button" className="btn btn-sm btn-ghost text-muted hover:text-bad" disabled={busy === h.id} onClick={() => remove(h)} aria-label="Delete"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
