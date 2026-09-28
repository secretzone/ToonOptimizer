import { Play } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { SingleResult } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { PageTitle } from '../components/ui'
import { Zap } from 'lucide-react'

export function QuickSimPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('quick')

  if (!profile) return <><PageTitle title="Quick Sim" /><NeedProfile /></>

  return (
    <div>
      <PageTitle
        title="Quick Sim"
        subtitle={`Simulate ${profile.name} as-is with the chosen fight settings.`}
        actions={
          <button type="button" className="btn btn-primary" disabled={running} onClick={() => run(() => api.quick({ profile, options }))}>
            <Play size={15} /> Run sim
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[340px_1fr]">
        <OptionsPanel options={options} onChange={setOptions} show={{ gear: false }} />
        <div className="flex flex-col gap-4">
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? <SingleResult result={result} /> : !job && (
            <EmptyState icon={<Zap size={32} strokeWidth={1.5} />} title="Ready to sim" body="Adjust the options on the left and hit Run sim. Results stay here while you browse other pages." />
          )}
        </div>
      </div>
    </div>
  )
}
