// The only module that talks to the backend. Set VITE_MOCK=1 to swap in lib/mock.ts.
import type {
  AddonImportResult, AddonStatus, AdvancedBody, AdvisorBody, AdvisorResult, CharacterProfile, CharacterReport, CharacterSummary, ConsumableOption,
  Consumables, ConsumableOptions, ConsumablesBody, DecodedTalents, DropSource, DroptimizerBody, GearCompareBody,
  GemsBody, HistoryEntry, Item, ItemSearchResult, Job, LootSources, OmniumBody, QuickBody, RawUpgradeTrack,
  Recommendations, ReportListEntry, SeasonData, Settings, SimResult, StatWeightsBody, Status, SurrogateStatus,
  TalentCompareBody, TalentTrees, TopGearBody, UpgradeTrackDef, UpgradesBody,
} from './types'
import { prettifySimcName } from './wow'

export const MOCK = import.meta.env.VITE_MOCK === '1' || import.meta.env.MODE === 'mock'

/** `season.consumables.options` before normalization — same categories as `ConsumableOptions` but
 * each entry may still be a bare SimC name string (an older/mismatched payload shape); see
 * `normalizeConsumableOptions`. */
type RawConsumableOptions = { [K in keyof ConsumableOptions]?: (ConsumableOption | string)[] }

/** GET /api/data/season before normalization: `upgrade_tracks` on the wire is an object keyed by
 * track name (`Record<string, RawUpgradeTrack>`), not an array — see `normalizeUpgradeTracks`.
 * `consumables.options` categories are also normalized defensively — see `normalizeConsumableOptions`.
 * Both fields are re-declared here (rather than left to `Omit<SeasonData, ...>`) because
 * `SeasonData`'s `[k: string]: unknown` index signature otherwise widens every omitted-and-re-added
 * key's sibling properties to `unknown` through `Omit`/`Pick`. */
type RawSeasonData = Omit<SeasonData, 'upgrade_tracks' | 'consumables'> & {
  upgrade_tracks?: UpgradeTrackDef[] | Record<string, RawUpgradeTrack> | null
  consumables?: (Consumables & { options?: RawConsumableOptions }) | null
}

/** The only place `upgrade_tracks` is normalized from the backend's object-keyed-by-track-name
 * shape into the `UpgradeTrackDef[]` every page expects (e.g. TopGearPage's Add Item track/rank
 * selects). Arrays (older/already-normalized payloads) pass through unchanged. Both the real
 * backend and lib/mock.ts's fixtures send the object shape, so this always runs. */
function normalizeUpgradeTracks(raw: UpgradeTrackDef[] | Record<string, RawUpgradeTrack> | null | undefined): UpgradeTrackDef[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return Object.entries(raw).map(([key, track]) => {
    const name = track?.name ?? key
    const crestName = track?.crest?.name
    const crestCost = track?.crest?.cost
    const ranks = (track?.steps ?? []).map((s) => ({ rank: s.rank, ilevel: s.ilevel, crest: crestName, cost: crestCost }))
    return { name, ranks }
  })
}

/** Defensive normalization for `season.consumables.options`: the real backend
 * (`data/season.py::consumable_options`) always sends `{value, label}[]` per category, but coerce
 * plain strings (an older/mismatched payload shape) into that same shape so a slip here can never
 * crash OptionsPanel/ConsumablesPage — see also `prettifySimcName`'s own non-string guard. */
function normalizeConsumableOptions(raw: RawConsumableOptions | null | undefined): ConsumableOptions | null {
  if (!raw) return raw ?? null
  const toOption = (o: ConsumableOption | string): ConsumableOption =>
    typeof o === 'string' ? { value: o, label: prettifySimcName(o) } : o
  const entries = Object.entries(raw).map(([cat, opts]) => [cat, (opts ?? []).map(toOption)])
  return Object.fromEntries(entries) as ConsumableOptions
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export type JobListener = (job: Job) => void
export type Unsubscribe = () => void

export interface ApiClient {
  health(): Promise<{ ok: boolean; version: string }>
  status(): Promise<Status>
  installSimc(tag?: string): Promise<Job>
  refreshData(build?: string): Promise<Job>
  season(): Promise<SeasonData>
  lootSources(klass?: string, spec?: string): Promise<LootSources>
  item(id: number, bonusIds?: number[], ilevel?: number): Promise<Item>
  /** GET /api/data/items/search — item name substring search, filtered to what the spec can equip. */
  itemSearch(q: string, klass?: string, spec?: string, slot?: string, limit?: number): Promise<{ items: ItemSearchResult[] }>
  /** GET /api/data/items/{id}?track=&rank= — resolves bonus ids/ilevel via the season's upgrade
   * tracks. Returned Item key is "search:<id>:<bonus>". */
  itemByTrack(id: number, track: string, rank: number): Promise<Item>
  recommendations(klass: string, spec: string): Promise<Recommendations>
  talents(klass: string, spec: string): Promise<TalentTrees>
  decodeTalents(klass: string, spec: string, loadout: string): Promise<DecodedTalents>
  importSimc(text: string): Promise<CharacterProfile>
  importArmory(region: string, realm: string, name: string): Promise<CharacterProfile>
  /** GET /api/import/addon — characters captured by the ToonOptimizer addon, newest first. */
  addonCaptures(): Promise<AddonStatus>
  /** POST /api/import/addon — import one capture (newest when key omitted); 404 no data, 422 parse error. */
  importAddon(key?: string): Promise<CharacterProfile>
  /** POST /api/import/addon {all:true} — per-capture results; captures not newer than saved are skipped. */
  importAddonAll(): Promise<AddonImportResult[]>
  quick(body: QuickBody): Promise<Job>
  topgear(body: TopGearBody): Promise<Job>
  droptimizer(body: DroptimizerBody): Promise<Job>
  statweights(body: StatWeightsBody): Promise<Job>
  gearcompare(body: GearCompareBody): Promise<Job>
  talentcompare(body: TalentCompareBody): Promise<Job>
  advanced(body: AdvancedBody): Promise<Job>
  runUpgrades(body: UpgradesBody): Promise<Job>
  runGems(body: GemsBody): Promise<Job>
  runConsumables(body: ConsumablesBody): Promise<Job>
  runOmnium(body: OmniumBody): Promise<Job>
  jobs(): Promise<Job[]>
  job(id: string): Promise<Job>
  cancel(id: string): Promise<Job>
  result(id: string): Promise<SimResult>
  input(id: string): Promise<string>
  reportUrl(id: string): string
  /** GET /api/jobs/{id}/simc.html — SimC's own HTML report (jobs pass html + report_details=1). */
  simcReportUrl(id: string): string
  report(id: string): Promise<string>
  history(): Promise<HistoryEntry[]>
  deleteHistory(id: string): Promise<{ ok: boolean }>
  /** GET /api/characters — every profile the backend has saved from a successful import. */
  characters(): Promise<CharacterSummary[]>
  /** GET /api/characters/{slug} — the latest saved CharacterProfile for that character. */
  character(slug: string): Promise<CharacterProfile>
  deleteCharacter(slug: string): Promise<{ ok: boolean }>
  /** POST /api/advisor/obvious-upgrades — synchronous (no SimC), one of body.slug/body.profile required. */
  advisor(body: AdvisorBody): Promise<AdvisorResult>
  /** GET /api/reports — every character with a saved report (see the "Reports" nav page). */
  reports(): Promise<ReportListEntry[]>
  /** GET /api/reports/{slug}. Named distinctly from `report()` above (that one fetches a sim job's
   * rendered HTML report; this fetches the per-character advisor report — same word, two different
   * API.md resources). */
  characterReport(slug: string): Promise<CharacterReport>
  putCharacterReport(slug: string, report: CharacterReport): Promise<CharacterReport>
  deleteCharacterReport(slug: string): Promise<{ ok: boolean }>
  settings(): Promise<Settings>
  putSettings(patch: Partial<Settings>): Promise<Settings>
  /** Experimental GPU surrogate (see toonopt.surrogate). */
  surrogateStatus(): Promise<SurrogateStatus>
  surrogateTrain(klass: string, spec: string, opts?: { min_samples?: number; epochs?: number }): Promise<Job>
  /** Subscribe to job events (SSE with polling fallback). Listener is called on every update, incl. terminal. */
  subscribeJob(id: string, listener: JobListener): Unsubscribe
}

const TERMINAL = new Set(['done', 'failed', 'cancelled'])
export const isTerminal = (job: Job | null | undefined): boolean => !!job && TERMINAL.has(job.status)

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
    })
  } catch (e) {
    throw new ApiError(0, `Backend unreachable (${(e as Error).message})`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`)
  }
  const ct = res.headers.get('content-type') ?? ''
  if (ct.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const put = <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })
const q = (params: Record<string, string | number | undefined>) => {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') sp.set(k, String(v))
  const s = sp.toString()
  return s ? `?${s}` : ''
}

function subscribeJobHttp(id: string, listener: JobListener): Unsubscribe {
  let closed = false
  let es: EventSource | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  const finish = () => {
    closed = true
    es?.close()
    es = null
    if (pollTimer) clearTimeout(pollTimer)
  }
  const handle = (job: Job) => {
    if (closed) return
    listener(job)
    if (isTerminal(job)) finish()
  }
  const poll = async () => {
    if (closed) return
    try {
      handle(await get<Job>(`/api/jobs/${id}`))
    } catch {
      /* keep polling */
    }
    if (!closed) pollTimer = setTimeout(poll, 1000)
  }
  const startPolling = () => {
    if (closed || pollTimer) return
    es?.close()
    es = null
    void poll()
  }

  if (typeof EventSource !== 'undefined') {
    try {
      es = new EventSource(`/api/jobs/${id}/events`)
      const onEvent = (ev: MessageEvent) => {
        try {
          handle(JSON.parse(ev.data) as Job)
        } catch {
          /* ignore malformed */
        }
      }
      es.addEventListener('progress', onEvent)
      es.addEventListener('done', onEvent)
      es.addEventListener('failed', onEvent)
      es.addEventListener('cancelled', onEvent)
      es.onmessage = onEvent
      es.onerror = () => {
        // The stream closes after the terminal event; if we haven't seen it, fall back to polling.
        if (!closed) startPolling()
      }
    } catch {
      startPolling()
    }
  } else {
    startPolling()
  }
  // Fetch once immediately so the UI has the current state even if SSE is slow to connect.
  void get<Job>(`/api/jobs/${id}`).then(handle).catch(() => undefined)
  return finish
}

const http: ApiClient = {
  health: () => get('/api/health'),
  status: () => get('/api/status'),
  installSimc: (tag) => post('/api/simc/install', tag ? { tag } : {}),
  refreshData: (build) => post('/api/data/refresh', build ? { build } : {}),
  season: () => get<RawSeasonData>('/api/data/season') as unknown as Promise<SeasonData>,
  lootSources: (klass, spec) => get(`/api/data/loot/sources${q({ klass, spec })}`),
  item: (id, bonusIds, ilevel) => get(`/api/data/items/${id}${q({ bonus_ids: bonusIds?.join('/'), ilevel })}`),
  itemSearch: (qStr, klass, spec, slot, limit) => get(`/api/data/items/search${q({ q: qStr, klass, spec, slot, limit })}`),
  itemByTrack: (id, track, rank) => get(`/api/data/items/${id}${q({ track, rank })}`),
  recommendations: (klass, spec) => get(`/api/data/recommendations${q({ klass, spec })}`),
  talents: (klass, spec) => get(`/api/data/talents/${klass}/${spec}`),
  decodeTalents: (klass, spec, loadout) => post('/api/data/talents/decode', { klass, spec, loadout }),
  importSimc: (text) => post('/api/import/simc', { text }),
  addonCaptures: () => get('/api/import/addon'),
  importAddon: (key) => post('/api/import/addon', { key: key ?? null }),
  importAddonAll: () => post('/api/import/addon', { all: true }),
  importArmory: (region, realm, name) => get(`/api/import/armory${q({ region, realm, name })}`),
  quick: (body) => post('/api/sims/quick', body),
  topgear: (body) => post('/api/sims/topgear', body),
  droptimizer: (body) => post('/api/sims/droptimizer', body),
  statweights: (body) => post('/api/sims/statweights', body),
  gearcompare: (body) => post('/api/sims/gearcompare', body),
  talentcompare: (body) => post('/api/sims/talentcompare', body),
  advanced: (body) => post('/api/sims/advanced', body),
  runUpgrades: (body) => post('/api/sims/upgrades', body),
  runGems: (body) => post('/api/sims/gems', body),
  runConsumables: (body) => post('/api/sims/consumables', body),
  runOmnium: (body) => post('/api/sims/omnium', body),
  jobs: () => get('/api/jobs'),
  job: (id) => get(`/api/jobs/${id}`),
  cancel: (id) => post(`/api/jobs/${id}/cancel`),
  result: (id) => get(`/api/jobs/${id}/result`),
  input: (id) => request<string>(`/api/jobs/${id}/input`, { headers: { Accept: 'text/plain' } }),
  reportUrl: (id) => `/api/jobs/${id}/report.html`,
  simcReportUrl: (id) => `/api/jobs/${id}/simc.html`,
  report: (id) => request<string>(`/api/jobs/${id}/report.html`, { headers: { Accept: 'text/html' } }),
  history: () => get('/api/history'),
  deleteHistory: (id) => del(`/api/history/${id}`),
  characters: () => get('/api/characters'),
  character: (slug) => get(`/api/characters/${slug}`),
  deleteCharacter: (slug) => del(`/api/characters/${slug}`),
  advisor: (body) => post('/api/advisor/obvious-upgrades', body),
  reports: () => get('/api/reports'),
  characterReport: (slug) => get(`/api/reports/${slug}`),
  putCharacterReport: (slug, report) => put(`/api/reports/${slug}`, report),
  deleteCharacterReport: (slug) => del(`/api/reports/${slug}`),
  settings: () => get('/api/settings'),
  putSettings: (patch) => put('/api/settings', patch),
  surrogateStatus: () => get('/api/surrogate/status'),
  surrogateTrain: (klass, spec, opts) => post('/api/surrogate/train', { klass, spec, ...opts }),
  subscribeJob: subscribeJobHttp,
}

let client: ApiClient = http
let ready: Promise<void> | null = null

/** Resolves once the client is chosen (mock module is loaded lazily so it stays out of the real bundle). */
export function apiReady(): Promise<void> {
  if (!ready) {
    ready = MOCK
      ? import('./mock').then((m) => {
          client = m.mock
        })
      : Promise.resolve()
  }
  return ready
}

// Proxy so pages can just call api.xyz(); every method awaits apiReady() first.
export const api: ApiClient = new Proxy({} as ApiClient, {
  get(_t, prop: keyof ApiClient) {
    if (prop === 'reportUrl') return (id: string) => client.reportUrl(id)
    if (prop === 'simcReportUrl') return (id: string) => client.simcReportUrl(id)
    if (prop === 'season') {
      return async (): Promise<SeasonData> => {
        await apiReady()
        const raw = (await client.season()) as unknown as RawSeasonData
        return {
          ...raw,
          upgrade_tracks: normalizeUpgradeTracks(raw.upgrade_tracks),
          consumables: raw.consumables
            ? { ...raw.consumables, options: normalizeConsumableOptions(raw.consumables.options) ?? undefined }
            : undefined,
        }
      }
    }
    if (prop === 'subscribeJob') {
      return (id: string, listener: JobListener): Unsubscribe => {
        let unsub: Unsubscribe | null = null
        let cancelled = false
        void apiReady().then(() => {
          if (!cancelled) unsub = client.subscribeJob(id, listener)
        })
        return () => {
          cancelled = true
          unsub?.()
        }
      }
    }
    return async (...args: unknown[]) => {
      await apiReady()
      const fn = client[prop] as (...a: unknown[]) => unknown
      return fn.apply(client, args)
    }
  },
})

export type { DropSource }
