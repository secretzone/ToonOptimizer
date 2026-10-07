import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { AlertTriangle, ClipboardPaste, Download, Globe, RefreshCw, Trash2, Zap } from 'lucide-react'
import { api } from '../lib/api'
import { deleteCharacterEverywhere, seedConsumablesForProfile, syncProfileToServer, useStore } from '../store'
import { SLOT_LABELS, PAPERDOLL_LEFT, PAPERDOLL_RIGHT, PAPERDOLL_BOTTOM, characterSlug } from '../lib/wow'
import { useWowheadRefresh } from '../lib/wowhead'
import { CharacterHeader } from '../components/CharacterHeader'
import { ItemCard, EmptySlot } from '../components/ItemCard'
import { Card, ConfirmButton, CopyButton, Field, Input, Select, Spinner, Checkbox } from '../components/ui'
import { EmptyState } from '../components/EmptyState'
import type { AddonStatus, Item } from '../lib/types'

function relTime(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (!Number.isFinite(s)) return iso
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

const REGIONS = ['us', 'eu', 'kr', 'tw', 'cn']

function ItemList({ items, title, candidateKeys, setCandidateKeys }: { items: Item[]; title: string; candidateKeys: string[]; setCandidateKeys: (k: string[]) => void }) {
  const toggleKey = (key: string, on: boolean) => setCandidateKeys(on ? [...new Set([...candidateKeys, key])] : candidateKeys.filter((k) => k !== key))
  return (
    <Card
      title={`${title} (${items.length})`}
      actions={items.length ? (
        <>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setCandidateKeys([...new Set([...candidateKeys, ...items.map((i) => i.key)])])}>All</button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setCandidateKeys(candidateKeys.filter((k) => !items.some((i) => i.key === k)))}>None</button>
        </>
      ) : undefined}
    >
      {items.length ? (
        <div className="flex flex-col gap-0.5">
          {items.map((it) => (
            <div key={it.key} className="flex items-center gap-1">
              <Checkbox checked={candidateKeys.includes(it.key)} onChange={(v) => toggleKey(it.key, v)} label="" className="pl-1" />
              <ItemCard item={it} slotLabel={SLOT_LABELS[it.slot] ?? it.slot} showSource className="flex-1" />
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-muted">Nothing found in the export.</div>
      )}
    </Card>
  )
}

export function ImportPage() {
  const navigate = useNavigate()
  const profile = useStore((s) => s.profile)
  const setProfile = useStore((s) => s.setProfile)
  const candidateKeys = useStore((s) => s.candidateKeys)
  const setCandidateKeys = useStore((s) => s.setCandidateKeys)
  const toast = useStore((s) => s.toast)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [addon, setAddon] = useState<AddonStatus | null>(null)
  const [addonLoading, setAddonLoading] = useState(true)
  const [addonError, setAddonError] = useState<string | null>(null)
  const [resyncing, setResyncing] = useState(false)
  const [armory, setArmory] = useState({ region: 'us', realm: '', name: '' })

  useWowheadRefresh([profile])

  const unresolvedCount = useMemo(() => {
    if (!profile) return 0
    const all = [...Object.values(profile.equipped), ...profile.bags, ...profile.vault]
    return all.filter((i) => i.resolved === false).length
  }, [profile])

  const importSimc = async () => {
    if (!text.trim()) return
    setBusy('simc')
    try {
      const p = await api.importSimc(text)
      setProfile(p)
      void seedConsumablesForProfile(p)
      toast(`Saved as ${characterSlug(p.name, p.realm)}; see Reports`, 'success')
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`, 'error')
    } finally {
      setBusy(null)
    }
  }
  const importArmory = async () => {
    if (!armory.name.trim() || !armory.realm.trim()) return
    setBusy('armory')
    try {
      const p = await api.importArmory(armory.region, armory.realm.trim(), armory.name.trim())
      setProfile(p)
      void seedConsumablesForProfile(p)
      toast(`Saved as ${characterSlug(p.name, p.realm)}; see Reports`, 'success')
    } catch (e) {
      toast(`Armory lookup failed: ${(e as Error).message}`, 'error')
    } finally {
      setBusy(null)
    }
  }
  const loadCaptures = useCallback(async () => {
    setAddonLoading(true)
    setAddonError(null)
    try {
      setAddon(await api.addonCaptures())
    } catch (e) {
      setAddonError((e as Error).message)
    } finally {
      setAddonLoading(false)
    }
  }, [])
  useEffect(() => { void loadCaptures() }, [loadCaptures])

  const captures = addon?.captures ?? []
  const currentSlug = profile ? characterSlug(profile.name, profile.realm) : null
  const currentMatch = currentSlug ? captures.find((c) => c.saved_slug === currentSlug) : undefined
  const preferred = currentMatch ?? captures[0]

  const importFromAddon = async (key: string) => {
    setBusy(`addon:${key}`)
    try {
      const p = await api.importAddon(key)
      setProfile(p)
      void seedConsumablesForProfile(p)
      toast(`Saved as ${characterSlug(p.name, p.realm)}; see Reports`, 'success')
      void loadCaptures()
    } catch (e) {
      toast(`Addon import failed: ${(e as Error).message}`, 'error')
    } finally {
      setBusy(null)
    }
  }
  const importAllNewer = async () => {
    setBusy('addon:all')
    try {
      const results = await api.importAddonAll()
      const imported = results.filter((r) => r.status === 'imported')
      const skipped = results.filter((r) => r.status === 'skipped').length
      const errors = results.filter((r) => r.status === 'error')
      const cur = imported.find((r) => r.profile && characterSlug(r.profile.name, r.profile.realm) === currentSlug)?.profile
      const p = cur ?? (profile ? null : imported[0]?.profile ?? null)
      if (p) {
        setProfile(p)
        void seedConsumablesForProfile(p)
      }
      const parts = [`Imported ${imported.length}`, `skipped ${skipped}`]
      if (errors.length) parts.push(`${errors.length} error${errors.length === 1 ? '' : 's'} (${errors.map((r) => `${r.key}: ${r.detail ?? 'failed'}`).join('; ')})`)
      toast(parts.join(', '), errors.length ? 'error' : 'success')
      void loadCaptures()
    } catch (e) {
      toast(`Addon import failed: ${(e as Error).message}`, 'error')
    } finally {
      setBusy(null)
    }
  }
  const resync = async () => {
    if (!profile) return
    setResyncing(true)
    try {
      await syncProfileToServer(profile, { force: true })
    } finally {
      setResyncing(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Import from addon"
        actions={
          <button type="button" className="btn btn-ghost btn-sm" disabled={addonLoading} onClick={() => void loadCaptures()}>
            {addonLoading ? <Spinner /> : <RefreshCw size={13} />} Refresh
          </button>
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!preferred || busy !== null}
            onClick={() => preferred && void importFromAddon(preferred.key)}
          >
            {busy?.startsWith('addon:') ? <Spinner /> : <Download size={15} />} Import from addon
          </button>
          <button type="button" className="btn" disabled={!captures.some((c) => c.newer_than_saved) || busy !== null} onClick={() => void importAllNewer()}>
            {busy === 'addon:all' ? <Spinner /> : <Download size={15} />} Import all newer
          </button>
          {preferred && <span className="text-xs text-muted">Imports <span className="text-text">{preferred.name}-{preferred.realm}</span>{currentMatch ? ' (current character)' : ' (newest capture)'}</span>}
          <span className="ml-auto text-xs text-faint">or paste a /simc export below</span>
        </div>
        {addonError && <div className="mt-3 rounded-md border border-red-600/50 bg-red-500/10 p-2 text-sm text-red-300">{addonError}</div>}
        {addonLoading && !addon && <div className="mt-3 flex items-center gap-2 text-sm text-muted"><Spinner /> Looking for addon data...</div>}
        {!addonLoading && !addonError && captures.length === 0 && (
          <div className="mt-3 text-sm text-muted">
            Install the ToonOptimizer addon (<span className="mono text-text">scripts/Install-Addons.ps1</span>), log in, then /reload or log out — WoW only writes addon data then.
          </div>
        )}
        {captures.length > 0 && (
          <div className="mt-3 flex flex-col gap-1">
            {captures.map((c) => (
              <div key={c.key} className="flex flex-wrap items-center gap-2 rounded px-1 py-1 hover:bg-surface-2">
                <span className="min-w-0 truncate text-sm font-medium">{c.name}-{c.realm}</span>
                <span className="text-xs text-muted">{[c.spec, c.class && c.class.toLowerCase().replace(/_/g, ' ')].filter(Boolean).join(' ')}</span>
                {c.ilvl != null && <span className="mono text-xs text-muted">{c.ilvl} ilvl</span>}
                <span className="text-xs text-faint" title={c.captured_at}>{relTime(c.captured_at)}</span>
                {c.newer_than_saved && <span className="chip text-info">newer than saved</span>}
                <button type="button" className="btn btn-sm ml-auto" disabled={busy !== null} onClick={() => void importFromAddon(c.key)}>
                  {busy === `addon:${c.key}` ? <Spinner /> : <Download size={13} />} Import
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        <Card title="Paste your /simc export" actions={<span className="text-xs text-muted">Type <span className="mono text-text">/simc</span> in game with the SimulationCraft addon</span>}>
          <textarea
            className="input mono h-48 resize-y text-xs"
            placeholder={'# Frostbyte - Frost - ...\ndeathknight="Frostbyte"\nlevel=90\n...'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') void importSimc() }}
            spellCheck={false}
          />
          <div className="mt-3 flex items-center gap-2">
            <button type="button" className="btn btn-primary" disabled={!text.trim() || busy !== null} onClick={importSimc}>
              {busy === 'simc' ? <Spinner /> : <ClipboardPaste size={15} />} Import
            </button>
            <span className="text-xs text-faint">Ctrl+Enter</span>
            {text && <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={() => setText('')}>Clear</button>}
          </div>
        </Card>
        <Card title="Armory lookup" actions={<span className="text-xs text-muted">best effort, via raider.io</span>}>
          <form
            className="grid grid-cols-[90px_1fr] gap-3"
            onSubmit={(e) => { e.preventDefault(); void importArmory() }}
          >
            <Field label="Region">
              <Select value={armory.region} onChange={(e) => setArmory({ ...armory, region: e.target.value })}>
                {REGIONS.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
              </Select>
            </Field>
            <Field label="Realm">
              <Input value={armory.realm} placeholder="Area 52" onChange={(e) => setArmory({ ...armory, realm: e.target.value })} />
            </Field>
            <Field label="Name" className="col-span-2">
              <Input value={armory.name} placeholder="Character name" onChange={(e) => setArmory({ ...armory, name: e.target.value })} />
            </Field>
            <div className="col-span-2 flex items-center gap-2">
              <button type="submit" className="btn" disabled={!armory.name.trim() || !armory.realm.trim() || busy !== null}>
                {busy === 'armory' ? <Spinner /> : <Globe size={15} />} Look up
              </button>
              <span className="text-xs text-faint">Bags and vault are only available from a /simc export.</span>
            </div>
          </form>
        </Card>
      </div>

      {!profile ? (
        <EmptyState title="No character yet" body="Paste a /simc export above or look one up from the Armory. The profile is kept in this browser." />
      ) : (
        <>
          <div className="flex items-start gap-3">
            <div className="flex-1"><CharacterHeader profile={profile} /></div>
          </div>
          {(!!profile.warnings?.length || unresolvedCount > 0) && (
            <div className="flex flex-wrap items-start gap-3 rounded-md border border-amber-600/50 bg-amber-500/10 p-3 text-sm text-amber-200">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-400" />
              <div className="min-w-0 flex-1">
                {profile.warnings?.length ? (
                  profile.warnings.map((w, i) => <div key={i}>{w}</div>)
                ) : (
                  <div>{unresolvedCount} item{unresolvedCount === 1 ? '' : 's'} could not be resolved against the cached game data.</div>
                )}
                <div className="mt-1 text-xs text-amber-300/80">
                  Unresolved items show a placeholder icon and their raw item id below. Try refreshing game data.
                </div>
              </div>
              <button type="button" className="btn btn-sm shrink-0 border-amber-600/50 text-amber-200 hover:bg-amber-500/20" onClick={() => navigate('/settings')}>
                Go to Settings
              </button>
            </div>
          )}
          <div className="flex gap-2">
            <button type="button" className="btn btn-primary" onClick={() => navigate('/quick')}><Zap size={15} /> Quick sim</button>
            <button type="button" className="btn" onClick={() => navigate('/topgear')}>Top Gear</button>
            <button type="button" className="btn" onClick={() => navigate('/droptimizer')}>Droptimizer</button>
            <button
              type="button"
              className="btn btn-ghost ml-auto text-muted"
              disabled={!profile.raw?.trim() || resyncing}
              title={!profile.raw?.trim() ? 'No raw export text on this profile to re-import' : 'Re-check and, if needed, re-save this profile to the server'}
              onClick={resync}
            >
              {resyncing ? <Spinner /> : <RefreshCw size={14} />} Re-sync to server
            </button>
            <ConfirmButton
              label={<><Trash2 size={14} /> Delete from server</>}
              confirmLabel="Confirm delete"
              onConfirm={async () => {
                const slug = characterSlug(profile.name, profile.realm)
                try {
                  await deleteCharacterEverywhere(slug)
                  toast(`Deleted ${profile.name} from the server`, 'success')
                } catch (e) {
                  toast((e as Error).message, 'error')
                }
              }}
            />
            <ConfirmButton
              label={<><Trash2 size={14} /> Remove from this browser</>}
              confirmLabel="Confirm remove"
              onConfirm={() => setProfile(null)}
            />
          </div>

          {!!profile.saved_loadouts?.length && (
            <Card title="Saved loadouts" actions={<span className="text-xs text-muted">from the export's loadout comments</span>}>
              <div className="flex flex-col gap-1">
                {profile.saved_loadouts.map((l) => (
                  <div key={l.name} className="flex items-center gap-2 rounded px-1 py-1 hover:bg-surface-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{l.name}</span>
                    <span className={`chip ${l.kind === 'active' ? 'text-info' : ''}`}>{l.kind}</span>
                    <CopyButton text={l.string} />
                  </div>
                ))}
              </div>
              <div className="mt-2 text-xs text-faint">Used to seed the Talent Compare page and the Talents override dropdown in sim options.</div>
            </Card>
          )}

          <Card title="Equipped">
            <div className="grid grid-cols-1 gap-x-6 gap-y-1 md:grid-cols-2">
              <div className="flex flex-col gap-1">
                {PAPERDOLL_LEFT.map((slot) => profile.equipped[slot] ? <ItemCard key={slot} item={profile.equipped[slot]} slotLabel={SLOT_LABELS[slot]} /> : <EmptySlot key={slot} label={SLOT_LABELS[slot]} />)}
                {PAPERDOLL_BOTTOM.map((slot) => profile.equipped[slot] ? <ItemCard key={slot} item={profile.equipped[slot]} slotLabel={SLOT_LABELS[slot]} /> : <EmptySlot key={slot} label={SLOT_LABELS[slot]} />)}
              </div>
              <div className="flex flex-col gap-1">
                {PAPERDOLL_RIGHT.map((slot) => profile.equipped[slot] ? <ItemCard key={slot} item={profile.equipped[slot]} slotLabel={SLOT_LABELS[slot]} /> : <EmptySlot key={slot} label={SLOT_LABELS[slot]} />)}
              </div>
            </div>
            <div className="mt-3 text-xs text-muted">
              Talents: <span className="mono break-all text-faint">{profile.talents || '—'}</span>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ItemList items={profile.bags} title="Bags" candidateKeys={candidateKeys} setCandidateKeys={setCandidateKeys} />
            <ItemList items={profile.vault} title="Great Vault" candidateKeys={candidateKeys} setCandidateKeys={setCandidateKeys} />
          </div>
          <div className="text-xs text-muted">Checked bag and vault items are used as Top Gear candidates.</div>
        </>
      )}
    </div>
  )
}
