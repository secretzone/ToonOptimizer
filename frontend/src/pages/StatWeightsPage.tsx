import { useMemo, useState } from 'react'
import { Play, Scale } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, Cell, ErrorBar, CartesianGrid } from 'recharts'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { DpsHero, ResultActions } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Checkbox, CopyButton, PageTitle } from '../components/ui'
import { STAT_LABELS, primaryStatFor, SECONDARY_STATS } from '../lib/wow'

const STAT_COLORS: Record<string, string> = {
  strength: '#f0b429', agility: '#f0b429', intellect: '#f0b429', crit: '#f87171', haste: '#60a5fa', mastery: '#c084fc', versatility: '#4ade80', weapon_dps: '#fb923c', stamina: '#a3a3a3',
}

export function StatWeightsPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('statweights')
  const primary = profile ? primaryStatFor(profile.klass, profile.spec) : 'strength'
  const available = useMemo(() => [primary, ...SECONDARY_STATS, 'weapon_dps', 'stamina'], [primary])
  const [stats, setStats] = useState<string[]>([primary, ...SECONDARY_STATS])

  if (!profile) return <><PageTitle title="Stat Weights" /><NeedProfile /></>

  const sw = result?.stat_weights
  const data = sw
    ? Object.entries(sw.normalized).map(([k, v]) => ({ stat: k, label: STAT_LABELS[k] ?? k, weight: v, err: sw.error?.[k] ?? 0 })).sort((a, b) => b.weight - a.weight)
    : []

  return (
    <div>
      <PageTitle
        title="Stat Weights"
        subtitle="Scale factors: how much DPS each point of a stat is worth, relative to your primary stat."
        actions={
          <button type="button" className="btn btn-primary" disabled={running || !stats.length} onClick={() => run(() => api.statweights({ profile, options, stats }))}>
            <Play size={15} /> Calculate weights
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[340px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Stats to scale" actions={<span className="text-xs text-muted">{stats.length} × iterations</span>}>
            <div className="flex flex-col gap-1.5">
              {available.map((s) => (
                <Checkbox key={s} checked={stats.includes(s)} onChange={(v) => setStats(v ? [...stats, s] : stats.filter((x) => x !== s))} label={<span><span className="inline-block h-2 w-2 rounded-full mr-2" style={{ background: STAT_COLORS[s] ?? '#888' }} />{STAT_LABELS[s] ?? s}</span>} />
              ))}
            </div>
            <div className="mt-2 text-xs text-faint">Each stat adds a full sim run. Use a looser target error for speed.</div>
          </Card>
          <OptionsPanel options={options} onChange={setOptions} show={{ gear: false }} />
        </div>
        <div className="flex flex-col gap-4">
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result && sw ? (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <Card title="Weights (normalized)">
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 8, bottom: 8 }}>
                      <CartesianGrid horizontal={false} stroke="#2a303c" />
                      <XAxis type="number" domain={[0, (max: number) => Math.ceil(max * 1.1 * 10) / 10]} tick={{ fill: '#8d95a5', fontSize: 12 }} stroke="#2a303c" />
                      <YAxis type="category" dataKey="label" width={110} tick={{ fill: '#e6e9ef', fontSize: 12 }} stroke="#2a303c" />
                      <RTooltip
                        cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                        contentStyle={{ background: '#181c24', border: '1px solid #2a303c', borderRadius: 8, fontSize: 12 }}
                        formatter={((v: unknown, _n: unknown, p: { payload?: { err?: number } }) => [`${Number(v).toFixed(3)} ± ${Number(p?.payload?.err ?? 0).toFixed(3)}`, 'weight']) as never}
                      />
                      <Bar dataKey="weight" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                        {data.map((d) => <Cell key={d.stat} fill={STAT_COLORS[d.stat] ?? '#8d95a5'} />)}
                        <ErrorBar dataKey="err" width={4} stroke="#ffffffaa" direction="x" />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <table className="mt-3 w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted"><th className="px-2 py-1">Stat</th><th className="px-2 py-1 text-right">Weight</th><th className="px-2 py-1 text-right">Raw (DPS / point)</th><th className="px-2 py-1 text-right">Error</th></tr></thead>
                  <tbody>
                    {data.map((d) => (
                      <tr key={d.stat} className="border-b border-border/50">
                        <td className="px-2 py-1 font-medium"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: STAT_COLORS[d.stat] ?? '#888' }} />{d.label}</td>
                        <td className="px-2 py-1 text-right tabular-nums">{d.weight.toFixed(3)}</td>
                        <td className="px-2 py-1 text-right tabular-nums text-muted">{(sw.weights[d.stat] ?? 0).toFixed(2)}</td>
                        <td className="px-2 py-1 text-right tabular-nums text-faint">± {d.err.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <Card title="Pawn string" actions={<CopyButton text={sw.pawn} label="Copy Pawn" />}>
                <pre className="mono whitespace-pre-wrap break-all rounded bg-bg-soft p-3 text-xs text-muted">{sw.pawn}</pre>
              </Card>
            </>
          ) : result && !sw ? (
            <EmptyState title="No stat weights in result" body="The job finished but returned no scale factors." />
          ) : !job && (
            <EmptyState icon={<Scale size={32} strokeWidth={1.5} />} title="Pick stats and calculate" body="Weights are normalized so your primary stat equals 1.0." />
          )}
        </div>
      </div>
    </div>
  )
}
