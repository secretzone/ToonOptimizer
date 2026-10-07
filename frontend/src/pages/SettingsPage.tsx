import { useEffect, useState } from 'react'
import { AlertTriangle, Cpu, Database, Download, Image, RefreshCw, Save, Check, X, FlaskConical, Play } from 'lucide-react'
import { api, isTerminal } from '../lib/api'
import { runJob, useStore } from '../store'
import { fmtDate } from '../lib/format'
import { titleCase } from '../lib/wow'
import { JobProgress } from '../components/JobProgress'
import { Card, Field, Input, PageTitle, Select, Spinner, Toggle } from '../components/ui'
import type { Settings, Status, SurrogateStatus, WowDirInfo } from '../lib/types'

function YesNo({ ok, yes = 'yes', no = 'no' }: { ok: boolean; yes?: string; no?: string }) {
  return <span className={`inline-flex items-center gap-1 ${ok ? 'text-good' : 'text-bad'}`}>{ok ? <Check size={13} /> : <X size={13} />}{ok ? yes : no}</span>
}

export function SettingsPage() {
  const toast = useStore((s) => s.toast)
  const wowheadTooltips = useStore((s) => s.wowheadTooltips)
  const setWowheadTooltips = useStore((s) => s.setWowheadTooltips)
  const installJob = useStore((s) => s.pages.simc_install.job)
  const refreshJob = useStore((s) => s.pages.data_refresh.job)
  const trainJob = useStore((s) => s.pages.surrogate_train.job)
  const profile = useStore((s) => s.profile)
  const [status, setStatus] = useState<Status | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [surrogate, setSurrogate] = useState<SurrogateStatus | null>(null)
  const [draft, setDraft] = useState<Partial<Settings>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wowDirInfo, setWowDirInfo] = useState<WowDirInfo | null>(null)
  const [wowDirError, setWowDirError] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)

  const load = () =>
    Promise.all([api.status(), api.settings()])
      .then(([st, se]) => { setStatus(st); setSettings(se); setDraft({}); setError(null) })
      .catch((e: Error) => setError(e.message))
  const loadSurrogate = () => api.surrogateStatus().then(setSurrogate).catch(() => undefined)
  useEffect(() => { void load() }, [])
  useEffect(() => { void loadSurrogate() }, [])
  useEffect(() => { void api.wowDir().then(setWowDirInfo).catch(() => undefined) }, [])
  // Reload status when an install/refresh/train job finishes.
  const installDone = !!installJob && isTerminal(installJob)
  const refreshDone = !!refreshJob && isTerminal(refreshJob)
  const trainDone = !!trainJob && isTerminal(trainJob)
  useEffect(() => { if (installDone) void load() }, [installDone])
  useEffect(() => { if (refreshDone) void load() }, [refreshDone])
  useEffect(() => { if (trainDone) void loadSurrogate() }, [trainDone])

  const cur = { ...settings, ...draft } as Settings
  const dirty = Object.keys(draft).length > 0
  const save = async () => {
    setSaving(true)
    setWowDirError(null)
    try {
      const s = await api.putSettings(draft)
      setSettings(s)
      setDraft({})
      toast('Settings saved', 'success')
      if (draft.wow_dir !== undefined) void api.wowDir().then(setWowDirInfo).catch(() => undefined)
    } catch (e) {
      if (draft.wow_dir !== undefined) setWowDirError((e as Error).message)
      else toast((e as Error).message, 'error')
    } finally {
      setSaving(false)
    }
  }
  const detect = async () => {
    setDetecting(true)
    try {
      const info = await api.wowDir()
      setWowDirInfo(info)
      setWowDirError(null)
      if (info.candidates.length) setDraft((d) => ({ ...d, wow_dir: info.candidates[0].path }))
      else toast('No WoW installation found. Enter the folder manually.', 'error')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setDetecting(false)
    }
  }
  const installing = !!installJob && !isTerminal(installJob)
  const refreshing = !!refreshJob && !isTerminal(refreshJob)
  const training = !!trainJob && !isTerminal(trainJob)

  if (error && !status) {
    return (
      <div>
        <PageTitle title="Settings" />
        <Card><div className="text-sm text-bad">Backend unavailable: {error}</div><button type="button" className="btn mt-3" onClick={load}><RefreshCw size={14} /> Retry</button></Card>
      </div>
    )
  }
  if (!status || !settings) return <div><PageTitle title="Settings" /><div className="flex items-center gap-2 text-muted"><Spinner /> Loading…</div></div>

  return (
    <div>
      <PageTitle
        title="Settings"
        subtitle={`WoW build ${status.wow_build || 'unknown'}`}
        actions={
          <>
            <button type="button" className="btn" onClick={load}><RefreshCw size={14} /> Reload</button>
            <button type="button" className="btn btn-primary" disabled={!dirty || saving} onClick={save}>{saving ? <Spinner /> : <Save size={14} />} Save</button>
          </>
        }
      />
      {(status.mismatch.simc || status.mismatch.data) && (
        <div className="mb-4 flex flex-col gap-2 rounded-md border border-amber-600/50 bg-amber-500/10 p-3 text-sm text-amber-200">
          {status.mismatch.simc && (
            <div className="flex flex-wrap items-center gap-2">
              <AlertTriangle size={14} className="shrink-0 text-amber-400" />
              <span>
                WoW is on <span className="mono">{status.mismatch.game_build}</span>, SimC targets{' '}
                <span className="mono">{status.mismatch.simc_wow_version}</span>
              </span>
              <button
                type="button"
                className="btn btn-sm ml-auto border-amber-600/50 text-amber-200 hover:bg-amber-500/20"
                disabled={installing}
                onClick={() => runJob('simc_install', () => api.installSimc(), { fetchResult: false })}
              >
                <Download size={13} /> Update SimC
              </button>
            </div>
          )}
          {status.mismatch.data && (
            <div className="flex flex-wrap items-center gap-2">
              <AlertTriangle size={14} className="shrink-0 text-amber-400" />
              <span>
                data cache is for <span className="mono">{status.mismatch.data_build}</span>
              </span>
              <button
                type="button"
                className="btn btn-sm ml-auto border-amber-600/50 text-amber-200 hover:bg-amber-500/20"
                disabled={refreshing}
                onClick={() => runJob('data_refresh', () => api.refreshData(), { fetchResult: false })}
              >
                <RefreshCw size={13} /> Refresh data
              </button>
            </div>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title={<span className="flex items-center gap-2"><Cpu size={15} /> SimulationCraft</span>} actions={<YesNo ok={status.simc.installed} yes="installed" no="not installed" />}>
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-sm">
            <dt className="text-muted">Installed tag</dt><dd className="mono">{status.simc.tag || '—'}</dd>
            <dt className="text-muted">Version</dt><dd className="truncate" title={status.simc.version_string}>{status.simc.version_string || '—'}</dd>
            <dt className="text-muted">WoW version</dt><dd className="mono">{status.simc.wow_version || '—'}</dd>
            <dt className="text-muted">Latest tag</dt><dd className="mono">{status.simc.latest_tag || '—'} {status.simc.update_available && <span className="chip ml-1 text-accent">update available</span>}</dd>
            <dt className="text-muted">Path</dt><dd className="mono truncate text-xs text-faint" title={status.simc.path}>{status.simc.path || '—'}</dd>
          </dl>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              className={`btn ${status.simc.update_available || !status.simc.installed ? 'btn-primary' : ''}`}
              disabled={installing}
              onClick={() => runJob('simc_install', () => api.installSimc(), { fetchResult: false })}
            >
              <Download size={14} /> {!status.simc.installed ? 'Install SimC' : status.simc.update_available ? `Update to ${status.simc.latest_tag}` : 'Reinstall latest'}
            </button>
            <span className="text-xs text-faint">sortbek/simc-builds weekly</span>
          </div>
          {installJob && <div className="mt-3"><JobProgress job={installJob} compact onCancel={() => api.cancel(installJob.id).then((j) => useStore.getState().setPage('simc_install', { job: j })).catch(() => undefined)} /></div>}
        </Card>

        <Card title={<span className="flex items-center gap-2"><Database size={15} /> Game data cache</span>} actions={<YesNo ok={status.data.ready} yes="ready" no="missing" />}>
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-sm">
            <dt className="text-muted">Build</dt><dd className="mono">{status.data.build || '—'}</dd>
            <dt className="text-muted">Refreshed</dt><dd>{status.data.refreshed_at ? fmtDate(status.data.refreshed_at) : 'never'}</dd>
            <dt className="text-muted">Tables</dt>
            <dd className="flex flex-wrap gap-1">{status.data.cached_tables.length ? status.data.cached_tables.map((t) => <span key={t} className="chip">{t}</span>) : <span className="text-faint">none</span>}</dd>
          </dl>
          <div className="mt-3 flex items-center gap-2">
            <button type="button" className={`btn ${status.data.ready ? '' : 'btn-primary'}`} disabled={refreshing} onClick={() => runJob('data_refresh', () => api.refreshData(), { fetchResult: false })}>
              <RefreshCw size={14} /> Refresh from wago.tools
            </button>
          </div>
          {refreshJob && <div className="mt-3"><JobProgress job={refreshJob} compact /></div>}
        </Card>

        <Card title="Simulation defaults">
          <div className="flex flex-col gap-4">
            <Field label={`Threads: ${cur.threads}`} hint={`Backend reports ${status.threads} available`}>
              <input type="range" min={1} max={32} value={cur.threads} onChange={(e) => setDraft({ ...draft, threads: Number(e.target.value) })} className="w-full" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Default iterations">
                <Input type="number" min={100} step={1000} value={cur.default_iterations} onChange={(e) => setDraft({ ...draft, default_iterations: Number(e.target.value) })} />
              </Field>
              <Field label="Default target error (%)">
                <Input type="number" min={0.01} step={0.05} value={cur.default_target_error} onChange={(e) => setDraft({ ...draft, default_target_error: Number(e.target.value) })} />
              </Field>
              <Field label="Profileset target error (%)" hint="Top Gear / Droptimizer">
                <Input type="number" min={0.01} step={0.05} value={cur.profileset_target_error} onChange={(e) => setDraft({ ...draft, profileset_target_error: Number(e.target.value) })} />
              </Field>
              <Field label="Profileset work threads">
                <Input type="number" min={1} max={32} value={cur.profileset_work_threads} onChange={(e) => setDraft({ ...draft, profileset_work_threads: Number(e.target.value) })} />
              </Field>
              <Field label="Region">
                <Select value={cur.region} onChange={(e) => setDraft({ ...draft, region: e.target.value })}>
                  {['us', 'eu', 'kr', 'tw', 'cn'].map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
                </Select>
              </Field>
              <div className="pt-5"><Toggle checked={cur.ptr} onChange={(v) => setDraft({ ...draft, ptr: v })} label="PTR" description="Use PTR SimC data by default" /></div>
            </div>
            <Field label="WoW directory" hint="The folder that contains _retail_ (auto-detected)">
              <div className="flex items-center gap-2">
                <Input value={cur.wow_dir} onChange={(e) => { setWowDirError(null); setDraft({ ...draft, wow_dir: e.target.value }) }} className="mono text-xs" />
                <button type="button" className="btn btn-sm shrink-0" disabled={detecting} onClick={() => void detect()}>
                  {detecting ? <Spinner /> : <RefreshCw size={13} />} Auto-detect
                </button>
              </div>
              {wowDirInfo && draft.wow_dir === undefined && (
                <div className="mt-1.5 text-xs"><YesNo ok={wowDirInfo.valid} yes="WoW folder found" no="Not a WoW folder" /></div>
              )}
              {wowDirInfo && wowDirInfo.candidates.length > 1 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-faint">Detected:</span>
                  {wowDirInfo.candidates.map((c) => (
                    <button key={c.path} type="button" className="chip hover:border-accent" onClick={() => { setWowDirError(null); setDraft({ ...draft, wow_dir: c.path }) }}>
                      <span className="mono">{c.path}</span> <span className="text-faint">({c.source})</span>
                    </button>
                  ))}
                </div>
              )}
              {wowDirError && <div className="mt-1.5 text-xs text-bad">{wowDirError}</div>}
            </Field>
          </div>
        </Card>

        <Card title="System">
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-sm">
            <dt className="text-muted">GPU</dt><dd><YesNo ok={status.gpu.available} yes={status.gpu.name || 'available'} no="not available" /> <span className="text-xs text-faint">(surrogate model only; SimC is CPU-bound)</span></dd>
            <dt className="text-muted">Backend port</dt><dd className="mono">{settings.port}</dd>
            <dt className="text-muted">WoW build</dt><dd className="mono">{settings.wow_build || status.wow_build || '—'}</dd>
          </dl>
        </Card>

        <Card title={<span className="flex items-center gap-2"><Image size={15} /> Display</span>}>
          <Toggle
            checked={wowheadTooltips}
            onChange={setWowheadTooltips}
            label="Wowhead tooltips (loads wow.zamimg.com script)"
            description="Real in-game item tooltips from Wowhead on hover. When off, a simpler built-in tooltip is used instead and no data is sent to wow.zamimg.com."
          />
        </Card>

        <Card
          title={<span className="flex items-center gap-2"><FlaskConical size={15} /> Surrogate model (experimental)</span>}
          className="lg:col-span-2"
          actions={
            surrogate && (
              <span className={surrogate.device === 'unavailable' ? 'text-bad' : 'text-good'}>
                {surrogate.device === 'cuda' ? 'GPU' : surrogate.device === 'cpu' ? 'CPU' : 'unavailable'}
              </span>
            )
          }
        >
          {!surrogate ? (
            <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Loading…</div>
          ) : (
            <>
              <p className="text-xs text-faint">
                Experimental: this model is only used to pick which gear combinations Top Gear's &quot;Smart&quot; mode
                bothers to simulate. Every DPS value shown anywhere in the app is still an exact SimulationCraft result.
              </p>
              {surrogate.device === 'unavailable' && (
                <div className="mt-3 rounded-md border border-border bg-bg-soft p-2.5 text-xs text-muted">
                  torch is not installed, so the surrogate is unavailable (SimC itself never needs a GPU). Install it with{' '}
                  <code className="mono text-text">cd backend; uv sync --extra gpu</code> — about a 3 GB download.
                </div>
              )}
              <div className="mt-3">
                <div className="label mb-1">Trained models</div>
                {surrogate.models.length ? (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-faint">
                        <th className="py-1 font-medium">Class / spec</th>
                        <th className="py-1 text-right font-medium">Samples</th>
                        <th className="py-1 text-right font-medium">Val MAE</th>
                        <th className="py-1 text-right font-medium">Trained</th>
                      </tr>
                    </thead>
                    <tbody>
                      {surrogate.models.map((m) => (
                        <tr key={`${m.klass}:${m.spec}`} className="border-t border-border">
                          <td className="py-1">{titleCase(m.klass)} · {titleCase(m.spec)}</td>
                          <td className="py-1 text-right tabular-nums">{m.samples.toLocaleString()}</td>
                          <td className="py-1 text-right tabular-nums">{m.val_mae_pct.toFixed(2)}%</td>
                          <td className="py-1 text-right text-faint">{fmtDate(m.trained_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="text-xs text-faint">No models trained yet.</div>
                )}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  className="btn"
                  disabled={!profile || training || surrogate.device === 'unavailable'}
                  title={!profile ? 'Import a character first' : surrogate.device === 'unavailable' ? 'torch is not installed' : undefined}
                  onClick={() =>
                    profile &&
                    void runJob('surrogate_train', () => api.surrogateTrain(profile.klass, profile.spec), { fetchResult: false })
                  }
                >
                  <Play size={14} /> {profile ? `Train for ${titleCase(profile.klass)} ${titleCase(profile.spec)}` : 'Train (import a character first)'}
                </button>
              </div>
              {trainJob && <div className="mt-3"><JobProgress job={trainJob} compact /></div>}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
