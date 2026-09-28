import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { CheckCircle2, ExternalLink, RefreshCw, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import { ensureProfileLoaded, loadCharacterIntoStore, openHistoryJob, useStore, type PageKey } from '../store'
import { CLASS_COLORS, JOB_TYPE_LABELS, JOB_TYPE_ROUTES, SLOT_LABELS, titleCase } from '../lib/wow'
import { fmtDate, fmtPct } from '../lib/format'
import { Card, Collapsible, CopyButton, Spinner } from '../components/ui'
import { MarkdownView } from '../components/MarkdownView'
import { ItemCard } from '../components/ItemCard'
import { AdvisorPanel, VerdictChip } from '../components/AdvisorPanel'
import { EmptyState } from '../components/EmptyState'
import type { AdvisorResult, CharacterReport } from '../lib/types'

function verdictFromLabel(label: string): Parameters<typeof VerdictChip>[0]['verdict'] {
  const v = label.trim().toLowerCase().replace(/\s+/g, '_')
  if (v === 'obvious' || v === 'likely' || v === 'sim_to_confirm' || v === 'sidegrade' || v === 'downgrade') return v
  return 'sim_to_confirm'
}

export function ReportDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const toast = useStore((s) => s.toast)
  const [report, setReport] = useState<CharacterReport | null | undefined>(undefined)
  const [loadingChar, setLoadingChar] = useState(false)
  const [advisor, setAdvisor] = useState<AdvisorResult | null>(null)
  const [advisorBusy, setAdvisorBusy] = useState(false)
  const [advisorOpen, setAdvisorOpen] = useState(false)

  useEffect(() => {
    if (!slug) return
    setReport(undefined)
    api.characterReport(slug).then(setReport).catch((e: Error) => { toast(e.message, 'error'); setReport(null) })
  }, [slug]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!slug) return null
  if (report === undefined) return <div className="flex items-center gap-2 text-muted"><Spinner /> Loading…</div>
  if (report === null) {
    return <EmptyState title="Report not found" body={`No report is saved for "${slug}".`} action={<button type="button" className="btn" onClick={() => navigate('/reports')}>Back to Reports</button>} />
  }

  const color = CLASS_COLORS[report.klass] ?? '#fff'

  const loadCharacter = async () => {
    setLoadingChar(true)
    try {
      const p = await loadCharacterIntoStore(slug)
      toast(`Loaded ${p.name}`, 'success')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setLoadingChar(false)
    }
  }

  const openSimRef = async (jobId: string) => {
    const ref = report.sim_refs.find((r) => r.job_id === jobId)
    const type = (ref?.type ?? 'droptimizer') as PageKey
    try {
      await ensureProfileLoaded(slug)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
    try {
      await openHistoryJob(type, jobId)
      navigate(JOB_TYPE_ROUTES[type] ?? '/history')
    } catch {
      navigate('/history')
    }
  }

  const refreshAdvisor = async () => {
    setAdvisorBusy(true)
    setAdvisorOpen(true)
    try {
      const r = await api.advisor({ slug })
      setAdvisor(r)
      toast('Advisor refreshed (report on disk unchanged).', 'success')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setAdvisorBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap items-center justify-between gap-3 p-4" style={{ borderLeft: `4px solid ${color}` }}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h1 className="text-xl font-semibold" style={{ color }}>{report.character}</h1>
            <span className="text-sm text-muted">{report.realm}</span>
            <span className="text-sm" style={{ color }}>{titleCase(report.spec)} {titleCase(report.klass)}</span>
          </div>
          <div className="text-xs text-muted">
            ilvl {report.ilevel_equipped.toFixed(1)} · {report.season} · Updated {fmtDate(report.updated_at)}
          </div>
        </div>
        <button type="button" className="btn btn-primary" disabled={loadingChar} onClick={loadCharacter}>
          {loadingChar ? <Spinner /> : null} Load this character
        </button>
      </div>

      <Card title="Summary"><p className="text-sm text-muted">{report.summary}</p></Card>

      {report.sections.map((section, i) => {
        if (section.kind === 'markdown') {
          return (
            <Card key={i} title={section.title}>
              <MarkdownView body={section.body} />
            </Card>
          )
        }
        if (section.kind === 'upgrades') {
          return (
            <Card key={i} title={section.title}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted">
                      <th className="px-2 py-1.5">Slot</th>
                      <th className="px-2 py-1.5">Current</th>
                      <th className="px-2 py-1.5">Option</th>
                      <th className="px-2 py-1.5">Verdict</th>
                      <th className="px-2 py-1.5">Gain</th>
                      <th className="px-2 py-1.5">How</th>
                      <th className="px-2 py-1.5">Sim</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.rows.map((row, j) => (
                      <tr key={j} className="border-b border-border/50 align-top">
                        <td className="whitespace-nowrap px-2 py-2 font-medium">{SLOT_LABELS[row.slot] ?? row.slot}</td>
                        <td className="px-2 py-2 text-muted">{row.current}</td>
                        <td className="px-2 py-2">{row.option}</td>
                        <td className="px-2 py-2"><VerdictChip verdict={verdictFromLabel(row.verdict)} /></td>
                        <td className="px-2 py-2 text-muted">{row.gain}</td>
                        <td className="px-2 py-2">
                          <ol className="list-decimal pl-4 text-xs text-muted">
                            {row.how.map((s, k) => <li key={k}>{s}</li>)}
                          </ol>
                        </td>
                        <td className="px-2 py-2">
                          {row.sim ? (
                            <button type="button" className="chip cursor-pointer text-info hover:bg-surface-3" onClick={() => openSimRef(row.sim!.job_id)}>
                              {fmtPct(row.sim.delta_pct)} <ExternalLink size={11} />
                            </button>
                          ) : <span className="text-faint">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )
        }
        if (section.kind === 'bis') {
          return (
            <Card key={i} title={section.title}>
              <div className="flex flex-col gap-1.5">
                {section.rows.map((row, j) => (
                  <div key={j} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-2 py-1.5">
                    <ItemCard item={row.item} slotLabel={SLOT_LABELS[row.slot] ?? row.slot} className="min-w-0 flex-1" />
                    <span className="chip">{row.source}</span>
                    {row.you_have
                      ? <span className="flex items-center gap-1 text-xs text-good"><CheckCircle2 size={13} /> You have it</span>
                      : <span className="flex items-center gap-1 text-xs text-faint"><XCircle size={13} /> Not yet</span>}
                    {row.theorycraft_says && <div className="basis-full text-xs text-muted">{row.theorycraft_says}</div>}
                  </div>
                ))}
              </div>
            </Card>
          )
        }
        if (section.kind === 'talents') {
          return (
            <Card key={i} title={section.title}>
              <div className="flex flex-col gap-2">
                {section.entries.map((e, j) => (
                  <div key={j} className="rounded-md border border-border p-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium">{e.context}</span>
                      <CopyButton text={e.loadout} label="Copy loadout" />
                    </div>
                    <div className="mono mt-1 truncate text-xs text-faint" title={e.loadout}>{e.loadout}</div>
                    {e.notes && <div className="mt-1 text-xs text-muted">{e.notes}</div>}
                    {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-accent hover:underline">Source <ExternalLink size={11} /></a>}
                  </div>
                ))}
              </div>
            </Card>
          )
        }
        // kind === 'kv'
        return (
          <Card key={i} title={section.title}>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {section.items.map((kv, j) => (
                <div key={j} className="rounded-md border border-border px-2.5 py-2">
                  <dt className="label">{kv.label}</dt>
                  <dd className="text-sm">{kv.value}</dd>
                  {kv.note && <dd className="mt-0.5 text-xs text-faint">{kv.note}</dd>}
                </div>
              ))}
            </dl>
          </Card>
        )
      })}

      <Card title="Refresh advisor" actions={<button type="button" className="btn" disabled={advisorBusy} onClick={refreshAdvisor}>{advisorBusy ? <Spinner /> : <RefreshCw size={14} />} Refresh advisor</button>}>
        <p className="text-xs text-muted">
          Calls the live advisor endpoint for this character and shows the raw result below — it never overwrites the saved report above.
        </p>
        {advisorOpen && (
          <div className="mt-3 border-t border-border pt-3">
            {advisorBusy && !advisor ? (
              <div className="flex items-center gap-2 text-muted"><Spinner /> Running…</div>
            ) : advisor ? (
              <Collapsible title="Advisor result" defaultOpen right={<span>{advisor.slots.length} slots</span>}>
                <AdvisorPanel result={advisor} />
              </Collapsible>
            ) : null}
          </div>
        )}
      </Card>

      <Card title="Sim references & sources">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <div className="label mb-1.5">Sim references</div>
            {report.sim_refs.length === 0 ? <div className="text-xs text-faint">None yet.</div> : (
              <ul className="flex flex-col gap-1">
                {report.sim_refs.map((ref) => (
                  <li key={ref.job_id}>
                    <button type="button" className="flex items-center gap-1.5 text-sm text-info hover:underline" onClick={() => openSimRef(ref.job_id)}>
                      <ExternalLink size={12} /> {ref.label} <span className="text-faint">({JOB_TYPE_LABELS[ref.type] ?? ref.type})</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="label mb-1.5">Sources</div>
            {report.sources.length === 0 ? <div className="text-xs text-faint">None yet.</div> : (
              <ul className="flex flex-col gap-1">
                {report.sources.map((s) => (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm text-accent hover:underline">
                      <ExternalLink size={12} /> {s.title}
                    </a>
                    <span className="ml-[18px] text-[11px] text-faint">fetched {fmtDate(s.fetched_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}
