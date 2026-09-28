import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { FileText, Sparkles, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { CLASS_COLORS, titleCase } from '../lib/wow'
import { fmtDate } from '../lib/format'
import { ConfirmButton, PageTitle, Spinner } from '../components/ui'
import { EmptyState } from '../components/EmptyState'
import type { CharacterSummary, ReportListEntry } from '../lib/types'

export function ReportsPage() {
  const toast = useStore((s) => s.toast)
  const [characters, setCharacters] = useState<CharacterSummary[] | null>(null)
  const [reports, setReports] = useState<ReportListEntry[] | null>(null)

  useEffect(() => {
    Promise.all([api.characters(), api.reports()])
      .then(([c, r]) => { setCharacters(c); setReports(r) })
      .catch((e: Error) => { toast(e.message, 'error'); setCharacters([]); setReports([]) })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loading = characters === null || reports === null

  const removeReport = async (slug: string, name: string) => {
    try {
      await api.deleteCharacterReport(slug)
      setReports((r) => r?.filter((x) => x.slug !== slug) ?? null)
      toast(`Deleted the report for ${name}`, 'success')
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  return (
    <div>
      <PageTitle
        title="Reports"
        subtitle="Per-character upgrade reports maintained by the Claude Code obvious-upgrades skill — see the Advisor panel on each character's page for the live equivalent."
      />
      {loading ? (
        <div className="flex items-center gap-2 text-muted"><Spinner /> Loading…</div>
      ) : characters!.length === 0 ? (
        <EmptyState icon={<FileText size={32} strokeWidth={1.5} />} title="No characters yet" body="Import a character first — every import is saved and shows up here." />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {characters!.map((c) => {
            const report = reports!.find((r) => r.slug === c.slug)
            const color = CLASS_COLORS[c.klass] ?? '#fff'
            if (!report) {
              return (
                <div key={c.slug} className="card p-4 opacity-60">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 h-8 w-1 shrink-0 rounded-full bg-border-strong" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">{c.name} <span className="font-normal text-faint">- {c.realm}</span></div>
                      <div className="text-xs text-muted">{titleCase(c.spec)} {titleCase(c.klass)} · ilvl {c.ilevel_equipped.toFixed(1)}</div>
                      <div className="mt-2 text-xs text-faint">No report yet. Run the obvious-upgrades skill from Claude Code.</div>
                    </div>
                  </div>
                </div>
              )
            }
            return (
              <div key={c.slug} className="relative">
                <Link to={`/reports/${report.slug}`} className="card block h-full p-4 transition-colors hover:border-border-strong" style={{ borderLeft: `3px solid ${color}` }}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold" style={{ color }}>{report.character}</div>
                      <div className="text-xs text-muted">{titleCase(report.spec)} {titleCase(report.klass)} · ilvl {c.ilevel_equipped.toFixed(1)}</div>
                    </div>
                    <Sparkles size={14} className="mt-0.5 shrink-0 text-accent" />
                  </div>
                  <p className="mt-2 line-clamp-3 pr-16 text-xs text-muted">{report.summary}</p>
                  <div className="mt-2 text-[11px] text-faint">Updated {fmtDate(report.updated_at)}</div>
                </Link>
                <div className="absolute bottom-3 right-3" onClick={(e) => { e.preventDefault(); e.stopPropagation() }}>
                  <ConfirmButton
                    label={<Trash2 size={12} />}
                    confirmLabel="Confirm"
                    size="sm"
                    title="Delete report"
                    onConfirm={() => removeReport(report.slug, report.character)}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
