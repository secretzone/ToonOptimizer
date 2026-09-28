import { useEffect, useState } from 'react'
import type { ConsumableOptions, Metric, SimOptions } from '../lib/types'
import { FIGHT_STYLES, METRICS } from '../lib/types'
import {
  BUFF_LABELS, CONSUMABLE_CATEGORY_LABELS, CUSTOM_CONSUMABLE, DEFAULT_BUFFS, dungeonSliceDisabledReason,
  EMPTY_CONSUMABLES, FIGHT_STYLE_INFO, METRIC_LABELS, PRECISION_HELP, recommendedEnchantSummary, recommendedGemSummary,
  UNSUPPORTED_BUFFS,
} from '../lib/wow'
import { api } from '../lib/api'
import { useStore } from '../store'
import { Checkbox, Collapsible, Field, Input, Select, Tabs, Toggle } from './ui'

type Props = {
  options: SimOptions
  onChange: (patch: Partial<SimOptions>) => void
  show?: { gear?: boolean; talents?: boolean }
}

let seasonOptionsCache: ConsumableOptions | null = null

export function OptionsPanel({ options, onChange, show = {} }: Props) {
  const mode: 'iterations' | 'target_error' = options.iterations != null ? 'iterations' : 'target_error'
  const [seasonOptions, setSeasonOptions] = useState<ConsumableOptions | null>(seasonOptionsCache)
  // Which consumable categories are showing a free-text "Custom…" box because the current value
  // isn't one of the season's named options (or was explicitly picked as custom).
  const [customCats, setCustomCats] = useState<Set<string>>(new Set())
  const setConsumableOptions = useStore((s) => s.setConsumableOptions)

  useEffect(() => {
    if (seasonOptionsCache) { setConsumableOptions(seasonOptionsCache); return }
    api.season().then((s) => {
      if (s?.consumables?.options) {
        seasonOptionsCache = s.consumables.options
        setSeasonOptions(seasonOptionsCache)
        setConsumableOptions(seasonOptionsCache)
      }
    }).catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Recommendations, fetched once per profile klass/spec and cached in the store — the enchant_all
  // / socket_all toggles below name what they'd actually apply, and "Season defaults" below applies
  // recs.consumables (the SimC names valid for this binary; see API.md's /api/data/recommendations).
  const profile = useStore((s) => s.profile)
  const recsCache = useStore((s) => s.recommendations)
  const setRecommendations = useStore((s) => s.setRecommendations)
  const setConsumablesCustomized = useStore((s) => s.setConsumablesCustomized)
  const recKey = profile ? `${profile.klass}:${profile.spec}` : null
  const recs = recKey ? recsCache[recKey] : null
  const [recsUnavailable, setRecsUnavailable] = useState(false)
  useEffect(() => {
    if (!profile || !recKey) return
    setRecsUnavailable(false)
    if (recsCache[recKey]) return
    api.recommendations(profile.klass, profile.spec)
      .then((r) => setRecommendations(recKey, r))
      .catch(() => setRecsUnavailable(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recKey])

  const cons = options.consumables
  const setCons = (k: keyof SimOptions['consumables'], v: string) => {
    setConsumablesCustomized(true)
    onChange({ consumables: { ...cons, [k]: v } })
  }
  const buffsOn = Object.values(options.buffs).filter(Boolean).length

  // Tank profiles default to DTPS (damage taken/s) instead of DPS; only fires once, before the
  // user has picked a metric of their own (options.metric starts unset).
  useEffect(() => {
    if (options.metric == null && profile?.role === 'tank') onChange({ metric: 'dtps' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.role])

  const dsReason = dungeonSliceDisabledReason(profile?.klass, profile?.spec)
  const isDungeonSlice = options.fight_style === 'DungeonSlice'
  // DungeonSlice forces a fixed fight (see API.md) — lock the length/targets inputs to match
  // once it's picked so the UI can't disagree with what the server will actually simulate.
  useEffect(() => {
    if (isDungeonSlice && !dsReason && (options.max_time !== 360 || options.desired_targets !== 1)) {
      onChange({ max_time: 360, desired_targets: 1 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDungeonSlice, dsReason])
  const fightHint = dsReason ?? (isDungeonSlice ? 'DungeonSlice forces a 360s / 1 target fight — length and targets below are locked.' : FIGHT_STYLE_INFO[options.fight_style])
  const lengthLocked = isDungeonSlice && !dsReason

  const precisionOn = !!options.precision
  const savedLoadouts = profile?.saved_loadouts ?? []
  const talentsMatchesLoadout = savedLoadouts.find((l) => l.string === options.talents_override)
  const talentsMode: 'profile' | 'custom' | string = options.talents_override == null ? 'profile' : talentsMatchesLoadout ? talentsMatchesLoadout.string : 'custom'

  return (
    <div className="card p-4">
      <div className="mb-3 text-sm font-semibold">Sim options</div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Fight style" className="col-span-2" hint={fightHint}>
          <Select value={options.fight_style} onChange={(e) => onChange({ fight_style: e.target.value as SimOptions['fight_style'] })}>
            {FIGHT_STYLES.map((f) => {
              const disabled = f === 'DungeonSlice' && !!dsReason
              return <option key={f} value={f} disabled={disabled} title={disabled ? dsReason! : FIGHT_STYLE_INFO[f]}>{f}{disabled ? ' (unavailable for this spec)' : ''}</option>
            })}
          </Select>
        </Field>
        <Field label="Fight length (s)" hint={lengthLocked ? 'locked by DungeonSlice' : undefined}>
          <Input type="number" min={30} max={1800} step={10} value={options.max_time} disabled={lengthLocked} onChange={(e) => onChange({ max_time: Number(e.target.value) || 300 })} />
        </Field>
        <Field label="Targets" hint={lengthLocked ? 'locked by DungeonSlice' : undefined}>
          <Input type="number" min={1} max={20} value={options.desired_targets} disabled={lengthLocked} onChange={(e) => onChange({ desired_targets: Math.max(1, Number(e.target.value) || 1) })} />
        </Field>
        <Field label="Length variance" hint="vary_combat_length">
          <Input type="number" min={0} max={1} step={0.05} value={options.vary_combat_length} onChange={(e) => onChange({ vary_combat_length: Number(e.target.value) })} />
        </Field>
        <Field label="Threads" hint="blank = setting">
          <Input type="number" min={1} max={64} placeholder="auto" value={options.threads ?? ''} onChange={(e) => onChange({ threads: e.target.value ? Number(e.target.value) : null })} />
        </Field>
        <Field label="Metric" className="col-span-2" hint="Which SimC metric results are ranked by; lower is better for DTPS/damage taken">
          <Select value={options.metric ?? 'dps'} onChange={(e) => onChange({ metric: e.target.value as Metric })}>
            {METRICS.map((m) => <option key={m} value={m}>{METRIC_LABELS[m]}</option>)}
          </Select>
        </Field>
        <div className="col-span-2 flex flex-col gap-1.5">
          <span className="label">Iterations / target error{precisionOn ? ' (overridden by Smart Sim below)' : ''}</span>
          <div className={`flex items-center gap-2 ${precisionOn ? 'pointer-events-none opacity-40' : ''}`}>
            <Tabs
              value={mode}
              onChange={(m) => onChange(m === 'iterations' ? { iterations: 10000, target_error: null } : { iterations: null, target_error: 0.1 })}
              tabs={[{ value: 'target_error', label: 'Target error' }, { value: 'iterations', label: 'Iterations' }]}
            />
            {mode === 'iterations' ? (
              <Input type="number" min={100} step={1000} value={options.iterations ?? 10000} disabled={precisionOn} onChange={(e) => onChange({ iterations: Number(e.target.value) || 10000 })} className="flex-1" />
            ) : (
              <Select value={String(options.target_error ?? 0.1)} disabled={precisionOn} onChange={(e) => onChange({ target_error: Number(e.target.value) })} className="flex-1">
                {[0.05, 0.1, 0.2, 0.3, 0.5, 1].map((v) => <option key={v} value={v}>{v}% {v <= 0.1 ? '(slow, precise)' : v >= 0.5 ? '(fast, rough)' : ''}</option>)}
              </Select>
            )}
          </div>
        </div>
        <Field label="Smart Sim precision" className="col-span-2" hint={PRECISION_HELP}>
          <Select value={options.precision ?? ''} onChange={(e) => onChange({ precision: (e.target.value || null) as SimOptions['precision'] })}>
            <option value="">Off</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </Select>
        </Field>
      </div>

      <div className="mt-3">
        <Collapsible title="Raid buffs" right={`${buffsOn} / ${Object.keys(options.buffs).length}`}>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.keys(BUFF_LABELS).map((k) => (
              <Checkbox key={k} checked={!!options.buffs[k]} disabled={UNSUPPORTED_BUFFS.has(k)} onChange={(v) => onChange({ buffs: { ...options.buffs, [k]: v } })} label={BUFF_LABELS[k]} />
            ))}
          </div>
          <div className="mt-2 flex gap-1.5">
            <button type="button" className="btn btn-sm" onClick={() => onChange({ buffs: Object.fromEntries(Object.keys(BUFF_LABELS).map((k) => [k, !UNSUPPORTED_BUFFS.has(k)])) })}>All</button>
            <button type="button" className="btn btn-sm" onClick={() => onChange({ buffs: Object.fromEntries(Object.keys(BUFF_LABELS).map((k) => [k, false])) })}>None</button>
            <button type="button" className="btn btn-sm" onClick={() => onChange({ buffs: { ...DEFAULT_BUFFS } })}>Defaults</button>
          </div>
          <div className="mt-2 border-t border-border pt-2">
            <Toggle
              checked={!!options.buffs.power_infusion}
              onChange={(v) => onChange({ buffs: { ...options.buffs, power_infusion: v } })}
              label={<span>Power Infusion <span className="chip ml-1 text-[10px] text-accent">external</span></span>}
              description="external_buffs.power_infusion on a timer for the fight length — an ally's cooldown, not this spec's own"
            />
          </div>
        </Collapsible>

        <Collapsible title="Consumables" right={Object.values(cons).filter(Boolean).length ? 'set' : 'none'}>
          {!recs && (
            <div className="mb-2 text-xs text-faint">
              {recsUnavailable ? 'No season defaults available; set manually.' : 'Loading season defaults…'}
            </div>
          )}
          <div className="grid grid-cols-1 gap-2">
            {(['flask', 'food', 'potion', 'augmentation', 'temporary_enchant'] as const).map((k) => {
              const opts = seasonOptions?.[k] ?? []
              const current = cons[k] ?? ''
              // Empty string is a real, distinct choice (SimC "disabled"), not "unset" — API.md is
              // explicit that "SimC default" (omitting the line) and "" (explicitly disabled) are
              // different, so the dropdown spells out "None (disabled)" rather than leaving it blank.
              const isCustom = customCats.has(k) || (current !== '' && !opts.some((o) => o.value === current))
              return (
                <Field key={k} label={CONSUMABLE_CATEGORY_LABELS[k] ?? k.replace('_', ' ')}>
                  <div className="flex flex-col gap-1">
                    <Select
                      value={isCustom ? CUSTOM_CONSUMABLE : current}
                      onChange={(e) => {
                        const v = e.target.value
                        if (v === CUSTOM_CONSUMABLE) {
                          setCustomCats((prev) => new Set(prev).add(k))
                        } else {
                          setCustomCats((prev) => { const next = new Set(prev); next.delete(k); return next })
                          setCons(k, v)
                        }
                      }}
                    >
                      <option value="">None (disabled)</option>
                      {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      <option value={CUSTOM_CONSUMABLE}>Custom…</option>
                    </Select>
                    {isCustom && (
                      <Input value={current} placeholder="SimC name, e.g. flask_of_alchemical_chaos_3" onChange={(e) => setCons(k, e.target.value)} className="mono text-xs" />
                    )}
                  </div>
                </Field>
              )
            })}
          </div>
          <div className="mt-2 flex gap-1.5">
            <button
              type="button"
              className="btn btn-sm"
              disabled={!recs}
              title={recs ? undefined : 'No season recommendations loaded for this spec yet'}
              onClick={() => {
                if (!recs) return
                setCustomCats(new Set())
                setConsumablesCustomized(false)
                onChange({ consumables: { ...recs.consumables } })
              }}
            >
              Season defaults
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => { setCustomCats(new Set()); setConsumablesCustomized(true); onChange({ consumables: { ...EMPTY_CONSUMABLES } }) }}
            >
              None
            </button>
          </div>
        </Collapsible>

        {show.gear !== false && (
          <Collapsible title="Gear handling">
            <div className="flex flex-col gap-2">
              <div title={recs ? recommendedEnchantSummary(recs) : 'Loading recommendations…'}>
                <Toggle checked={options.enchant_all} onChange={(v) => onChange({ enchant_all: v })} label="Enchant all" description="Give every candidate the season's best enchant for its slot" />
              </div>
              <div title={recs ? recommendedGemSummary(recs) : 'Loading recommendations…'}>
                <Toggle checked={options.socket_all} onChange={(v) => onChange({ socket_all: v })} label="Socket all" description="Fill every socket with the season's gem" />
              </div>
            </div>
          </Collapsible>
        )}

        {show.talents !== false && (
          <Collapsible title="Talents override" right={options.talents_override ? 'set' : 'profile'}>
            {savedLoadouts.length > 0 && (
              <Select
                className="mb-2"
                value={talentsMode}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === 'profile') onChange({ talents_override: null })
                  else if (v === 'custom') onChange({ talents_override: options.talents_override ?? '' })
                  else onChange({ talents_override: v })
                }}
              >
                <option value="profile">Use imported talents</option>
                {savedLoadouts.map((l) => <option key={l.name} value={l.string}>{l.name} ({l.kind})</option>)}
                <option value="custom">Custom…</option>
              </Select>
            )}
            {(talentsMode === 'custom' || savedLoadouts.length === 0) && (
              <textarea
                className="input mono h-20 resize-y text-xs"
                placeholder="Paste a loadout string to override the imported talents"
                value={options.talents_override ?? ''}
                onChange={(e) => onChange({ talents_override: e.target.value.trim() || null })}
              />
            )}
          </Collapsible>
        )}

        <Collapsible title="Expert mode" right={options.expert && Object.values(options.expert).some((v) => v?.trim()) ? 'set' : undefined}>
          <div className="mb-2 text-xs text-faint">
            Raw SimC lines spliced into the generated input at each position. <span className="mono">threads=</span>, <span className="mono">json2=</span>,
            {' '}<span className="mono">html=</span>, <span className="mono">output=</span> and <span className="mono">xml=</span> lines are always stripped.
          </div>
          <div className="grid grid-cols-1 gap-2">
            {(['header', 'pre_actor', 'post_actor', 'footer'] as const).map((k) => (
              <Field key={k} label={k.replace('_', ' ')}>
                <textarea
                  className="input mono h-16 resize-y text-xs"
                  placeholder={`Lines to splice in ${k === 'header' ? 'at the very top of the file' : k === 'pre_actor' ? 'after globals, before the actor block' : k === 'post_actor' ? 'right after the actor block' : 'at the very end, after profilesets'}`}
                  value={options.expert?.[k] ?? ''}
                  onChange={(e) => onChange({ expert: { ...options.expert, [k]: e.target.value } })}
                />
              </Field>
            ))}
          </div>
        </Collapsible>

        <Collapsible title="Advanced">
          <Toggle checked={options.ptr} onChange={(v) => onChange({ ptr: v })} label="PTR" description="Use PTR data / ptr=1" />
        </Collapsible>
      </div>
    </div>
  )
}
