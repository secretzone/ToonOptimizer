import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, isTerminal, type Unsubscribe } from './lib/api'
import type { CharacterProfile, ConsumableOptions, Job, Recommendations, SimOptions, SimResult } from './lib/types'
import { characterSlug, CONSUMABLE_CATEGORY_LABELS, defaultOptions, EMPTY_CONSUMABLES, invalidConsumableCategory } from './lib/wow'

export type PageKey =
  | 'quick' | 'topgear' | 'droptimizer' | 'statweights' | 'gearcompare' | 'talentcompare' | 'advanced'
  | 'upgrades' | 'gems' | 'consumables' | 'omnium'
  | 'simc_install' | 'data_refresh' | 'surrogate_train'

export type PageJob = { job: Job | null; result: SimResult | null; error: string | null }
export type Toast = { id: number; kind: 'info' | 'success' | 'error'; text: string }

const emptyPage = (): PageJob => ({ job: null, result: null, error: null })

/** Stable key for a character profile, used to remember per-profile UI preferences (e.g. the
 * Top Gear min item level filter) across imports of the same character. */
export function profileKey(p: Pick<CharacterProfile, 'name' | 'realm' | 'region'>): string {
  return `${p.name}:${p.realm}:${p.region}`
}

type State = {
  profile: CharacterProfile | null
  options: SimOptions
  candidateKeys: string[]
  minIlevelByProfile: Record<string, number>
  pages: Record<PageKey, PageJob>
  toasts: Toast[]
  /** Loads Wowhead's tooltip script's data-wowhead attributes (see lib/wowhead.ts). The
   * <script src="wow.zamimg.com/js/tooltips.js"> tag itself always loads (index.html); this
   * only controls whether we feed it item data. Default on. */
  wowheadTooltips: boolean
  /** GET /api/data/recommendations, cached per "klass:spec" so OptionsPanel and the Gems page
   * only fetch it once per profile spec. */
  recommendations: Record<string, Recommendations>
  /** `season.consumables.options` — the SimC names this installed binary accepts per consumable
   * category (not spec-specific). Populated once by OptionsPanel's `GET /api/data/season` fetch;
   * used by `runJob` below to reject a bad consumable client-side before submitting a sim. */
  consumableOptions: ConsumableOptions | null
  /** True once the user has explicitly changed a consumable value (or hit "None") for the current
   * profile — while set, `seedConsumablesForProfile` won't clobber it with season recommendations.
   * Reset to false on every new import (`setProfile`). */
  consumablesCustomized: boolean
  setProfile: (p: CharacterProfile | null) => void
  setOptions: (patch: Partial<SimOptions> | ((o: SimOptions) => SimOptions)) => void
  setCandidateKeys: (keys: string[]) => void
  setMinIlevel: (key: string, value: number) => void
  setPage: (page: PageKey, patch: Partial<PageJob>) => void
  clearPage: (page: PageKey) => void
  toast: (text: string, kind?: Toast['kind']) => void
  dismissToast: (id: number) => void
  setWowheadTooltips: (on: boolean) => void
  setRecommendations: (key: string, data: Recommendations) => void
  setConsumableOptions: (opts: ConsumableOptions) => void
  setConsumablesCustomized: (v: boolean) => void
}

let toastSeq = 1

export const useStore = create<State>()(
  persist(
    (set) => ({
      profile: null,
      options: defaultOptions(),
      candidateKeys: [],
      minIlevelByProfile: {},
      pages: {
        quick: emptyPage(), topgear: emptyPage(), droptimizer: emptyPage(), statweights: emptyPage(),
        gearcompare: emptyPage(), talentcompare: emptyPage(), advanced: emptyPage(),
        upgrades: emptyPage(), gems: emptyPage(), consumables: emptyPage(), omnium: emptyPage(),
        simc_install: emptyPage(), data_refresh: emptyPage(), surrogate_train: emptyPage(),
      },
      toasts: [],
      wowheadTooltips: true,
      recommendations: {},
      consumableOptions: null,
      consumablesCustomized: false,
      setProfile: (profile) =>
        set({
          profile,
          candidateKeys: profile ? [...profile.bags, ...profile.vault].map((i) => i.key) : [],
          consumablesCustomized: false,
        }),
      setOptions: (patch) =>
        set((s) => ({ options: typeof patch === 'function' ? patch(s.options) : { ...s.options, ...patch } })),
      setCandidateKeys: (candidateKeys) => set({ candidateKeys }),
      setMinIlevel: (key, value) => set((s) => ({ minIlevelByProfile: { ...s.minIlevelByProfile, [key]: value } })),
      setPage: (page, patch) => set((s) => ({ pages: { ...s.pages, [page]: { ...s.pages[page], ...patch } } })),
      clearPage: (page) => set((s) => ({ pages: { ...s.pages, [page]: emptyPage() } })),
      toast: (text, kind = 'info') =>
        set((s) => {
          const id = toastSeq++
          setTimeout(() => useStore.getState().dismissToast(id), kind === 'error' ? 8000 : 4000)
          return { toasts: [...s.toasts, { id, kind, text }] }
        }),
      dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
      setWowheadTooltips: (on) => set({ wowheadTooltips: on }),
      setRecommendations: (key, data) => set((s) => ({ recommendations: { ...s.recommendations, [key]: data } })),
      setConsumableOptions: (opts) => set({ consumableOptions: opts }),
      setConsumablesCustomized: (v) => set({ consumablesCustomized: v }),
    }),
    {
      name: 'toonopt',
      version: 1,
      partialize: (s) => ({
        profile: s.profile, options: s.options, candidateKeys: s.candidateKeys, minIlevelByProfile: s.minIlevelByProfile,
        wowheadTooltips: s.wowheadTooltips, consumablesCustomized: s.consumablesCustomized,
      }),
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<State>
        return {
          ...current, ...p,
          options: { ...defaultOptions(), ...(p.options ?? {}) },
          wowheadTooltips: p.wowheadTooltips ?? current.wowheadTooltips,
          consumablesCustomized: p.consumablesCustomized ?? false,
        }
      },
    },
  ),
)

/** Every job type whose `SimOptions` actually carries `consumables` — the ones `runJob` below
 * checks against `consumableOptions` before submitting. (simc_install/data_refresh/surrogate_train
 * don't sim anything and have no consumables to validate.) */
const SIM_PAGES = new Set<PageKey>([
  'quick', 'topgear', 'droptimizer', 'statweights', 'gearcompare', 'talentcompare', 'advanced',
  'upgrades', 'gems', 'consumables', 'omnium',
])

/** Fetches (or reuses the cached) `GET /api/data/recommendations` for a profile's klass/spec and
 * seeds `options.consumables` from it — the values SimC actually accepts for this build (see
 * API.md). Leaves every consumable empty ("" = disabled) when recommendations can't be loaded.
 * No-ops if the user already customized consumables for the current profile, or if the profile
 * changed again while this fetch was in flight. Called after a fresh import (ImportPage) and once
 * at store init for whatever profile was persisted from a previous session. */
export async function seedConsumablesForProfile(profile: CharacterProfile): Promise<void> {
  const recKey = `${profile.klass}:${profile.spec}`
  let recs: Recommendations | undefined = useStore.getState().recommendations[recKey]
  if (!recs) {
    try {
      recs = await api.recommendations(profile.klass, profile.spec)
      useStore.getState().setRecommendations(recKey, recs)
    } catch {
      recs = undefined
    }
  }
  const st = useStore.getState()
  if (st.consumablesCustomized) return
  if (!st.profile || st.profile.klass !== profile.klass || st.profile.spec !== profile.spec) return
  st.setOptions({ consumables: recs ? { ...recs.consumables } : { ...EMPTY_CONSUMABLES } })
}

// Re-seed consumables once at startup for a profile persisted from a previous session, in case it
// was saved before this seeding existed (or its recommendations have since changed) — skipped
// entirely once the user has customized consumables for it.
{
  const initial = useStore.getState()
  if (initial.profile && !initial.consumablesCustomized) {
    void seedConsumablesForProfile(initial.profile)
  }
}

/** Slugs already reconciled with the server this app load — `syncProfileToServer` is a no-op for
 * a slug already in here unless `opts.force` is set, so a profile change caused by the sync's own
 * `setProfile` call below can't re-trigger itself in a loop. */
const syncedProfileSlugs = new Set<string>()

/**
 * Reconciles the store's profile with the server-side character store (`GET`/`POST
 * /api/characters`, `/api/import/simc` — API.md "Characters"). Profiles imported before that
 * store existed (or otherwise only ever saved to this browser's persisted zustand store) can be
 * newer than, or entirely missing from, the server's `characters/<slug>.json` copy. When that's
 * the case, re-POSTing `profile.raw` to `/api/import/simc` re-parses and re-saves it server-side,
 * and the returned, freshly resolved `CharacterProfile` replaces the one in the store — keeping
 * items current with the data layer too, not just the character store.
 *
 * No-ops when `profile.raw` is empty (nothing to re-import), and — unless `opts.force` — when
 * this slug has already been checked once this app load (so the automatic checks at startup and
 * on every profile change never loop or hammer the server). The Import page's "Re-sync to server"
 * button passes `force: true` to bypass that once-per-load guard on demand.
 */
export async function syncProfileToServer(profile: CharacterProfile, opts: { force?: boolean } = {}): Promise<void> {
  if (!profile.raw?.trim()) return
  const slug = characterSlug(profile.name, profile.realm)
  if (!opts.force && syncedProfileSlugs.has(slug)) return
  syncedProfileSlugs.add(slug)
  try {
    let serverProfile: CharacterProfile | null = null
    try {
      serverProfile = await api.character(slug)
    } catch {
      serverProfile = null // none saved server-side yet (or unreachable) — treat like "server has none"
    }
    const stale = !serverProfile || new Date(serverProfile.imported_at).getTime() < new Date(profile.imported_at).getTime()
    if (!stale) {
      if (opts.force) useStore.getState().toast(`${profile.name} is already up to date on the server`, 'info')
      return
    }
    const fresh = await api.importSimc(profile.raw)
    const st = useStore.getState()
    // Only replace the active profile if it's still this same character — avoids clobbering a
    // character switch that happened while this request was in flight.
    if (st.profile && characterSlug(st.profile.name, st.profile.realm) === slug) st.setProfile(fresh)
    st.toast(`Synced ${fresh.name} to the server`, 'success')
  } catch (e) {
    useStore.getState().toast(`Could not sync ${profile.name} to the server: ${(e as Error).message}`, 'error')
    syncedProfileSlugs.delete(slug) // allow a later attempt (another profile change, or the manual button)
  }
}

// Check the profile persisted from a previous session against the server once at startup, and
// again whenever the active profile changes (import, character switch, ...) — `profile !== prev`
// is a new object on every `setProfile`, and `syncProfileToServer`'s own guard keeps this from
// looping when that setProfile call is the sync itself replacing the profile with the server's copy.
{
  const initial = useStore.getState()
  if (initial.profile) void syncProfileToServer(initial.profile)
}
useStore.subscribe((state, prev) => {
  if (state.profile && state.profile !== prev.profile) void syncProfileToServer(state.profile)
})

// ---------- job orchestration (module level so it survives page unmounts) ----------
const watchers = new Map<string, Unsubscribe>()

function watch(page: PageKey, job: Job, fetchResult: boolean) {
  const existing = watchers.get(job.id)
  if (existing) return
  const unsub = api.subscribeJob(job.id, (j) => {
    const st = useStore.getState()
    st.setPage(page, { job: j })
    if (isTerminal(j)) {
      watchers.get(job.id)?.()
      watchers.delete(job.id)
      if (j.status === 'done' && fetchResult) {
        api.result(j.id)
          .then((result) => useStore.getState().setPage(page, { result, error: null }))
          .catch((e: Error) => {
            useStore.getState().setPage(page, { error: e.message })
            useStore.getState().toast(`Could not load result: ${e.message}`, 'error')
          })
      } else if (j.status === 'failed') {
        useStore.getState().setPage(page, { error: j.error ?? 'Job failed' })
        useStore.getState().toast(`Job failed: ${j.error ?? 'unknown error'}`, 'error')
      }
    }
  })
  watchers.set(job.id, unsub)
}

/** Submit a job for a page, track it, and load the result when done. */
export async function runJob(page: PageKey, submit: () => Promise<Job>, opts: { fetchResult?: boolean } = {}): Promise<Job | null> {
  const st = useStore.getState()
  const prev = st.pages[page].job
  if (prev && !isTerminal(prev)) {
    st.toast('A job is already running on this page', 'info')
    return null
  }
  if (SIM_PAGES.has(page)) {
    const badCat = invalidConsumableCategory(st.options.consumables, st.consumableOptions)
    if (badCat) {
      const label = CONSUMABLE_CATEGORY_LABELS[badCat] ?? badCat
      const msg = `${label}: "${st.options.consumables[badCat]}" isn't a name this SimC build accepts — pick from the list or clear it in Sim options → Consumables.`
      st.setPage(page, { error: msg, result: null })
      st.toast(msg, 'error')
      return null
    }
  }
  st.setPage(page, { error: null, result: null })
  try {
    const job = await submit()
    useStore.getState().setPage(page, { job })
    watch(page, job, opts.fetchResult ?? true)
    return job
  } catch (e) {
    const msg = (e as Error).message
    useStore.getState().setPage(page, { error: msg })
    useStore.getState().toast(msg, 'error')
    return null
  }
}

export async function cancelJob(page: PageKey): Promise<void> {
  const job = useStore.getState().pages[page].job
  if (!job || isTerminal(job)) return
  try {
    const j = await api.cancel(job.id)
    useStore.getState().setPage(page, { job: j })
  } catch (e) {
    useStore.getState().toast((e as Error).message, 'error')
  }
}

/** Load a finished job from history into a page without re-running it. */
export async function openHistoryJob(page: PageKey, id: string): Promise<void> {
  const st = useStore.getState()
  try {
    const [job, result] = await Promise.all([api.job(id).catch(() => null), api.result(id)])
    st.setPage(page, { job: job ?? { id, type: result.type, status: 'done', progress: { phase: 'done', current: 1, total: 1, pct: 100, message: '' }, created: '' }, result, error: null })
  } catch (e) {
    st.toast(`Could not open job: ${(e as Error).message}`, 'error')
    throw e
  }
}

/**
 * Deletes a character server-side (`DELETE /api/characters/{slug}`) and its saved report, if any
 * (`DELETE /api/reports/{slug}` — 404 when there's none, swallowed). Clears the store profile too
 * when the deleted character was the active one, so nothing keeps pointing at a profile the
 * backend no longer has. Used by the character switcher's "Manage characters" view and the Import
 * page's "Delete from server" button.
 */
export async function deleteCharacterEverywhere(slug: string): Promise<void> {
  const st = useStore.getState()
  const wasActive = !!st.profile && characterSlug(st.profile.name, st.profile.realm) === slug
  await api.deleteCharacter(slug)
  try {
    await api.deleteCharacterReport(slug)
  } catch {
    /* no report saved for this character — nothing to clean up */
  }
  if (wasActive) useStore.getState().setProfile(null)
}

/** `GET /api/characters/{slug}` into the store, same path as Reports' "Load this character" and
 * the top-bar character switcher: setProfile + seed consumables for that klass/spec. */
export async function loadCharacterIntoStore(slug: string): Promise<CharacterProfile> {
  const p = await api.character(slug)
  useStore.getState().setProfile(p)
  await seedConsumablesForProfile(p)
  return p
}

/** Loads `slug` into the store only if it isn't already the active profile (compared via
 * `characterSlug`), and toasts "Loaded <character>" when it does. Used before jumping to a sim
 * page from a sim_ref / History "Open" so that page doesn't render `NeedProfile` just because the
 * user hadn't pressed "Load this character" first. */
export async function ensureProfileLoaded(slug: string): Promise<void> {
  const st = useStore.getState()
  const activeSlug = st.profile ? characterSlug(st.profile.name, st.profile.realm) : null
  if (activeSlug === slug) return
  const p = await loadCharacterIntoStore(slug)
  useStore.getState().toast(`Loaded ${p.name}`, 'success')
}
