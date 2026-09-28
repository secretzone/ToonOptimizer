import { useEffect, useMemo, useState } from 'react'
import { FlaskConical, Play, Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Checkbox, Field, Input, PageTitle, Select } from '../components/ui'
import { CONSUMABLE_CATEGORY_LABELS, isLowerBetter } from '../lib/wow'
import type { ConsumableCategory, ConsumablesCustomSet, ResultRow, SeasonData } from '../lib/types'

const CATEGORIES: ConsumableCategory[] = ['flask', 'food', 'potion', 'augmentation', 'temporary_enchant']

type CustomSet = { id: number } & ConsumablesCustomSet
let setSeq = 1

export function ConsumablesPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('consumables')

  const [season, setSeason] = useState<SeasonData | null>(null)
  useEffect(() => { void api.season().then(setSeason).catch(() => undefined) }, [])
  const optionsByCategory = season?.consumables?.options

  const [categories, setCategories] = useState<Set<ConsumableCategory>>(new Set(CATEGORIES))
  const toggleCategory = (c: ConsumableCategory, on: boolean) => setCategories((prev) => {
    const next = new Set(prev)
    if (on) next.add(c); else next.delete(c)
    return next
  })

  const [sets, setSets] = useState<CustomSet[]>([{ id: setSeq++, name: 'Set A' }])
  const updateSet = (id: number, patch: Partial<CustomSet>) => setSets(sets.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  const setsValid = sets.filter((s) => CATEGORIES.some((c) => s[c]))

  const [selected, setSelected] = useState<ResultRow | null>(null)

  const rowsByCategory = useMemo(() => {
    const m = new Map<string, ResultRow[]>()
    for (const r of result?.results ?? []) {
      if (!r.meta.consumable) continue
      const cat = r.meta.consumable.category
      if (!m.has(cat)) m.set(cat, [])
      m.get(cat)!.push(r)
    }
    return [...m.entries()]
  }, [result])
  const customRows = useMemo(() => (result?.results ?? []).filter((r) => !r.meta.consumable), [result])

  if (!profile) return <><PageTitle title="Consumables" /><NeedProfile /></>

  const canRun = categories.size > 0 || setsValid.length > 0

  return (
    <div>
      <PageTitle
        title="Consumables"
        subtitle="Which flask, food, potion, augmentation and weapon rune are actually worth it."
        actions={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || !canRun}
            onClick={() => {
              setSelected(null)
              void run(() => api.runConsumables({
                profile, options,
                categories: categories.size ? [...categories] : undefined,
                custom: setsValid.length ? setsValid.map(({ name, ...rest }) => ({ name, ...rest })) : undefined,
              }))
            }}
          >
            <Play size={15} /> Run
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[400px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Categories" actions={<span className="text-xs text-muted">{categories.size} / {CATEGORIES.length}</span>}>
            <div className="mb-2 flex gap-1.5">
              <button type="button" className="btn btn-sm" onClick={() => setCategories(new Set(CATEGORIES))}>All</button>
              <button type="button" className="btn btn-sm" onClick={() => setCategories(new Set())}>None</button>
            </div>
            <div className="flex flex-col gap-1">
              {CATEGORIES.map((c) => (
                <Checkbox key={c} checked={categories.has(c)} onChange={(v) => toggleCategory(c, v)} label={CONSUMABLE_CATEGORY_LABELS[c] ?? c} />
              ))}
            </div>
            <div className="mt-2 text-xs text-faint">One profileset per option per checked category; the other categories are held at whatever's set in Sim options below.</div>
          </Card>

          <Card title="Custom sets" actions={<span className="text-xs text-muted">{setsValid.length} valid</span>}>
            <div className="flex flex-col gap-3">
              {sets.map((set) => (
                <div key={set.id} className="rounded-md border border-border p-2.5">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <Input value={set.name} onChange={(e) => updateSet(set.id, { name: e.target.value })} className="w-32 py-1 text-sm font-semibold" />
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSets(sets.filter((s) => s.id !== set.id))} disabled={sets.length === 1} aria-label="Remove set"><Trash2 size={13} /></button>
                  </div>
                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {CATEGORIES.map((c) => {
                      const opts = optionsByCategory?.[c] ?? []
                      return (
                        <Field key={c} label={CONSUMABLE_CATEGORY_LABELS[c] ?? c}>
                          <Select value={set[c] ?? ''} onChange={(e) => updateSet(set.id, { [c]: e.target.value } as Partial<CustomSet>)} className="py-1 text-xs">
                            <option value="">None (disabled)</option>
                            {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                          </Select>
                        </Field>
                      )
                    })}
                  </div>
                </div>
              ))}
              <button type="button" className="btn self-start" onClick={() => setSets([...sets, { id: setSeq++, name: `Set ${String.fromCharCode(65 + sets.length)}` }])} disabled={sets.length >= 6}>
                <Plus size={14} /> Add set
              </button>
            </div>
          </Card>

          <OptionsPanel options={options} onChange={setOptions} show={{ gear: false }} />
        </div>

        <div className="flex flex-col gap-4">
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />
              {rowsByCategory.length === 0 && customRows.length === 0 ? (
                <EmptyState icon={<FlaskConical size={32} strokeWidth={1.5} />} title="No consumable options" body="No category was checked and no custom set was defined." />
              ) : (
                <>
                  {rowsByCategory.map(([cat, rows]) => (
                    <Card key={cat} title={CONSUMABLE_CATEGORY_LABELS[cat] ?? cat}>
                      <ResultBars baseline={result.baseline} rows={rows} selected={selected?.name} onSelect={setSelected} labelWidth={280} lowerBetter={isLowerBetter(result.metric)} />
                    </Card>
                  ))}
                  {customRows.length > 0 && (
                    <Card title="Custom sets">
                      <ResultBars baseline={result.baseline} rows={customRows} selected={selected?.name} onSelect={setSelected} labelWidth={200} lowerBetter={isLowerBetter(result.metric)} />
                    </Card>
                  )}
                </>
              )}
            </>
          ) : !job && (
            <EmptyState icon={<FlaskConical size={32} strokeWidth={1.5} />} title="Pick categories and run" body="Every option in a checked category is simmed with the others held at whatever's configured in Sim options." />
          )}
        </div>
      </div>
    </div>
  )
}
