import UserNavbar from '../components/UserNavbar.jsx';
import Hero from '../components/Hero.jsx';
import StatsStrip from '../components/StatsStrip.jsx';
import ProblemSection from '../components/ProblemSection.jsx';
import HowItWorks from '../components/HowItWorks.jsx';
import Capabilities from '../components/Capabilities.jsx';
import CtaBand from '../components/CtaBand.jsx';
import UserFooter from '../components/UserFooter.jsx';

export default function Landing() {
  return (
    <div className="min-h-screen bg-white">
      <UserNavbar />
      <main>
        <Hero />
        <StatsStrip />
        <ProblemSection />
        <HowItWorks />
        <Capabilities />
        <CtaBand />
      </main>
      <UserFooter />
    </div>
  );
}