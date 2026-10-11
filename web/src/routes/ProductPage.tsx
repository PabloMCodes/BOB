import { lazy, Suspense } from 'react'
import { AgentChapter } from '../components/AgentChapter.tsx'
import { Audience } from '../components/Audience.tsx'
import { Credits } from '../components/Credits.tsx'
import { Hero } from '../components/Hero.tsx'
import { Overview } from '../components/Overview.tsx'
import { SkillsRail } from '../components/SkillsRail.tsx'
import { SystemLine } from '../components/SystemLine.tsx'
import { Targets } from '../components/Targets.tsx'
import { VideoSection } from '../components/VideoSection.tsx'
import { WhyBob } from '../components/WhyBob.tsx'

const SiteScene = lazy(() =>
  import('../components/scene/SiteScene.tsx').then((module) => ({ default: module.SiteScene })),
)

export function ProductPage() {
  return (
    <>
      <main>
        <Hero />
        <VideoSection />
        <WhyBob />
        <Targets />
        <Overview />
        <SkillsRail />
        <Audience />
        <SystemLine />
        <AgentChapter />
        <Suspense fallback={<div className="h-svh" />}>
          <SiteScene />
        </Suspense>
      </main>
      <Credits />
    </>
  )
}
