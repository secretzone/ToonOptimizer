import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { ImportPage } from './pages/ImportPage'
import { QuickSimPage } from './pages/QuickSimPage'
import { TopGearPage } from './pages/TopGearPage'
import { DroptimizerPage } from './pages/DroptimizerPage'
import { UpgradesPage } from './pages/UpgradesPage'
import { GemsPage } from './pages/GemsPage'
import { ConsumablesPage } from './pages/ConsumablesPage'
import { GearComparePage } from './pages/GearComparePage'
import { TalentComparePage } from './pages/TalentComparePage'
import { AdvancedPage } from './pages/AdvancedPage'
import { HistoryPage } from './pages/HistoryPage'
import { ReportsPage } from './pages/ReportsPage'
import { ReportDetailPage } from './pages/ReportDetailPage'
import { SettingsPage } from './pages/SettingsPage'
import { Spinner } from './components/ui'

// recharts is only used here; keep it out of the main chunk.
const StatWeightsPage = lazy(() => import('./pages/StatWeightsPage').then((m) => ({ default: m.StatWeightsPage })))

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<ImportPage />} />
          <Route path="quick" element={<QuickSimPage />} />
          <Route path="topgear" element={<TopGearPage />} />
          <Route path="droptimizer" element={<DroptimizerPage />} />
          <Route path="upgrades" element={<UpgradesPage />} />
          <Route path="gems" element={<GemsPage />} />
          <Route path="consumables" element={<ConsumablesPage />} />
          <Route path="statweights" element={<Suspense fallback={<div className="flex items-center gap-2 text-muted"><Spinner /> Loading…</div>}><StatWeightsPage /></Suspense>} />
          <Route path="gearcompare" element={<GearComparePage />} />
          <Route path="talentcompare" element={<TalentComparePage />} />
          <Route path="advanced" element={<AdvancedPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/:slug" element={<ReportDetailPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
