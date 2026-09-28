import { useEffect, useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { api } from '../lib/api'
import { deleteCharacterEverywhere, useStore } from '../store'
import { CLASS_COLORS, characterSlug, titleCase } from '../lib/wow'
import { fmtDate } from '../lib/format'
import { ConfirmButton, Spinner } from './ui'
import type { CharacterSummary } from '../lib/types'

/**
 * "Manage characters" view opened from the character switcher: every saved character
 * (`GET /api/characters`) with a per-row Delete button. Deleting calls
 * `deleteCharacterEverywhere` (store.ts) which cascades to the character's report, if any, and
 * clears the store profile if it was the active one.
 */
export function ManageCharactersModal({ onClose, onChanged }: { onClose: () => void; onChanged?: () => void }) {
  const profile = useStore((s) => s.profile)
  const toast = useStore((s) => s.toast)
  const [list, setList] = useState<CharacterSummary[] | null>(null)

  useEffect(() => {
    let cancelled = false
    api.characters().then((r) => { if (!cancelled) setList(r) }).catch((e: Error) => { if (!cancelled) { toast(e.message, 'error'); setList([]) } })
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const activeSlug = profile ? characterSlug(profile.name, profile.realm) : null

  const remove = async (c: CharacterSummary) => {
    try {
      await deleteCharacterEverywhere(c.slug)
      setList((l) => l?.filter((x) => x.slug !== c.slug) ?? null)
      toast(`Deleted ${c.name} (and its report, if any)`, 'success')
      onChanged?.()
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 flex max-h-[80vh] w-[600px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Manage characters</h2>
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-2">
          {list === null ? (
            <div className="flex items-center gap-2 p-4 text-sm text-muted"><Spinner /> Loading…</div>
          ) : list.length === 0 ? (
            <div className="p-4 text-sm text-muted">No saved characters yet — import one first.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="px-2 py-1.5">Name</th>
                  <th className="px-2 py-1.5">Spec</th>
                  <th className="px-2 py-1.5">Ilvl</th>
                  <th className="px-2 py-1.5">Imported</th>
                  <th className="px-2 py-1.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((c) => {
                  const color = CLASS_COLORS[c.klass] ?? '#fff'
                  return (
                    <tr key={c.slug} className="border-t border-border/50">
                      <td className="px-2 py-2">
                        <span className="block truncate font-medium" style={{ color }}>
                          {c.name}<span className="text-faint"> - {c.realm}</span>
                        </span>
                        {c.slug === activeSlug && <span className="chip text-accent">active</span>}
                      </td>
                      <td className="whitespace-nowrap px-2 py-2 text-muted">{titleCase(c.spec)} {titleCase(c.klass)}</td>
                      <td className="px-2 py-2 text-muted">{c.ilevel_equipped.toFixed(1)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-muted">{fmtDate(c.imported_at)}</td>
                      <td className="px-2 py-2 text-right">
                        <ConfirmButton
                          label={<><Trash2 size={13} /> Delete</>}
                          confirmLabel="Confirm delete"
                          onConfirm={() => remove(c)}
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
        <div className="border-t border-border px-4 py-2 text-[11px] text-faint">
          Deleting a character also deletes its saved report, if any, and clears it from the active profile if it's currently loaded.
        </div>
      </div>
    </>
  )
}
