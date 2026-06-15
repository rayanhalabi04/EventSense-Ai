import { LandingNav } from '../components/landing/LandingNav'
import { HeroSection } from '../components/landing/HeroSection'
import { FeaturesSection } from '../components/landing/FeaturesSection'
import { UseCaseCarousel } from '../components/landing/UseCaseCarousel'
import { HowItWorksSection } from '../components/landing/HowItWorksSection'
import { BenefitsSection } from '../components/landing/BenefitsSection'
import { TestimonialsSection } from '../components/landing/TestimonialsSection'
import { CtaSection } from '../components/landing/CtaSection'
import { LandingFooter } from '../components/landing/LandingFooter'

export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-warm">
      <LandingNav />
      <HeroSection />
      <FeaturesSection />
      <UseCaseCarousel />
      <HowItWorksSection />
      <BenefitsSection />
      <TestimonialsSection />
      <CtaSection />
      <LandingFooter />
    </div>
  )
}
