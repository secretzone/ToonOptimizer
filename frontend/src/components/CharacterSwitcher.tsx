import { useEffect, useState } from 'react'
import { ChevronDown, Settings, User } from 'lucide-react'
import { api } from '../lib/api'
import { seedConsumablesForProfile, useStore } from '../store'
import { CLASS_COLORS, characterSlug, titleCase } from '../lib/wow'
import type { CharacterSummary } from '../lib/types'
import { Spinner } from './ui'
import { ManageCharactersModal } from './ManageCharactersModal'

/** Top-bar-style character switcher: lists every character the backend has saved
 * (`GET /api/characters`) and loads the picked one into the store the same way Import does
 * (`GET /api/characters/{slug}` -> setProfile), re-seeding consumables. See API.md "Characters". */
export function CharacterSwitcher() {
  const profile = useStore((s) => s.profile)
  const setProfile = useStore((s) => s.setProfile)
  const toast = useStore((s) => s.toast)
  const [list, setList] = useState<CharacterSummary[] | null>(null)
  const [open, setOpen] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const reload = () => api.characters().then(setList).catch(() => setList([]))
  useEffect(() => {
    let cancelled = false
    api.characters().then((r) => { if (!cancelled) setList(r) }).catch(() => { if (!cancelled) setList([]) })
    return () => { cancelled = true }
  }, [profile]) // eslint-disable-line react-hooks/exhaustive-deps -- refresh after switching/importing

  const activeSlug = profile ? characterSlug(profile.name, profile.realm) : null

  const select = async (slug: string) => {
    if (slug === activeSlug) { setOpen(false); return }
    setBusy(slug)
    try {
      const p = await api.character(slug)
      setProfile(p)
      void seedConsumablesForProfile(p)
      toast(`Loaded ${p.name} (${titleCase(p.spec)} ${titleCase(p.klass)})`, 'success')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(null)
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="btn btn-sm w-full justify-between"
        onClick={() => setOpen((o) => !o)}
        disabled={list === null}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <User size={13} className="shrink-0 text-faint" />
          <span className="truncate">{profile ? profile.name : 'Switch character'}</span>
        </span>
        <ChevronDown size={13} className="shrink-0" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-0 z-20 mt-1 w-64 rounded-md border border-border bg-surface-2 p-1 shadow-xl">
            {list === null ? (
              <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted"><Spinner /> Loading…</div>
            ) : list.length === 0 ? (
              <div className="px-2 py-2 text-xs text-muted">No saved characters yet — import one first.</div>
            ) : (
              list.map((c) => {
                const color = CLASS_COLORS[c.klass]
                return (
                  <button
                    key={c.slug}
                    type="button"
                    disabled={busy !== null}
                    className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-3 disabled:opacity-60 ${c.slug === activeSlug ? 'bg-surface-3' : ''}`}
                    onClick={() => select(c.slug)}
                  >
                    <span className="h-6 w-0.5 shrink-0 rounded-full" style={{ background: color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium" style={{ color }}>{c.name}<span className="text-faint"> - {c.realm}</span></span>
                      <span className="block truncate text-[11px] text-muted">{titleCase(c.spec)} {titleCase(c.klass)} · ilvl {c.ilevel_equipped.toFixed(1)}</span>
                    </span>
                    {busy === c.slug && <Spinner />}
                  </button>
                )
              })
            )}
            <div className="mt-1 border-t border-border pt-1">
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-muted hover:bg-surface-3 hover:text-text"
                onClick={() => { setOpen(false); setManageOpen(true) }}
              >
                <Settings size={13} className="shrink-0" />
                Manage characters…
              </button>
            </div>
          </div>
        </>
      )}
      {manageOpen && (
        <ManageCharactersModal
          onClose={() => setManageOpen(false)}
          onChanged={reload}
        />
      )}
    </div>
  )
}
