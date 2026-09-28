import { useState } from 'react'
import { Play, Terminal } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { SingleResult } from '../components/ResultView'
import { EmptyState } from '../components/EmptyState'
import { Card, PageTitle, Toggle } from '../components/ui'
import { isLowerBetter } from '../lib/wow'

export function AdvancedPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('advanced')
  const [text, setText] = useState('')
  const [useOptions, setUseOptions] = useState(true)

  const loadProfile = () => {
    if (!profile) return
    setText([profile.simc_header, '', ...Object.values(profile.equipped).map((i) => i.simc_string), '', '# profileset."example"=trinket1=,id=0', ''].join('\n'))
  }

  return (
    <div>
      <PageTitle
        title="Advanced"
        subtitle="Run raw SimulationCraft input. Profilesets are ranked automatically."
        actions={
          <button type="button" className="btn btn-primary" disabled={running || !text.trim()} onClick={() => run(() => api.advanced({ simc_text: text, ...(useOptions ? { options } : {}) }))}>
            <Play size={15} /> Run
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-4">
          <Card
            title="SimC input"
            actions={
              <>
                {profile && <button type="button" className="btn btn-sm" onClick={loadProfile}>Load {profile.name}</button>}
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => setText('')} disabled={!text}>Clear</button>
              </>
            }
          >
            <textarea
              className="input mono h-80 resize-y text-xs"
              placeholder={'deathknight="Frostbyte"\nlevel=90\n...\nprofileset."Alt trinket"=trinket1=,id=...'}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && text.trim() && !running) void run(() => api.advanced({ simc_text: text, ...(useOptions ? { options } : {}) })) }}
              spellCheck={false}
            />
            <div className="mt-2 flex items-center justify-between">
              <Toggle checked={useOptions} onChange={setUseOptions} label="Apply sim options" description="Off: only what's in the text box is used" />
              <span className="text-xs text-faint">Ctrl+Enter to run</span>
            </div>
          </Card>
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? (
            <>
              <SingleResult result={result} />
              {result.results.length > 0 && (
                <Card title={`${result.results.length} profilesets`}>
                  <ResultBars baseline={result.baseline} rows={result.results} lowerBetter={isLowerBetter(result.metric)} />
                </Card>
              )}
            </>
          ) : !job && (
            <EmptyState icon={<Terminal size={32} strokeWidth={1.5} />} title="Paste any SimC input" body="Full control: actor, gear, APL overrides, profilesets. Fight options from the panel are appended unless you turn them off." />
          )}
        </div>
        <OptionsPanel options={options} onChange={setOptions} show={{ gear: false }} />
      </div>
    </div>
  )
}
