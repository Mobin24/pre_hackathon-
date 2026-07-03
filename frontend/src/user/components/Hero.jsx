import { Link } from 'react-router-dom';
import Button from '../../shared/components/ui/Button.jsx';
import Badge from '../../shared/components/ui/Badge.jsx';

export default function Hero() {
  return (
    <section className="relative overflow-hidden bg-white">
      <div className="absolute inset-0 bg-grid-slate" aria-hidden />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-16 pb-20 sm:pt-24 sm:pb-28">
        <div className="mx-auto max-w-3xl text-center">
          <Badge variant="secondary" className="mb-5">
            <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live across Bangladesh
          </Badge>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-slate-900">
            Faster disaster response,
            <br className="hidden sm:block" />
            <span className="text-blue-600"> coordinated relief.</span>
          </h1>

          <p className="mt-6 text-lg text-slate-600 leading-relaxed">
            Report incidents in seconds. AI structures your message, geocodes the
            location, and routes the right help — to the right place — before
            minutes become casualties.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link to="/report">
              <Button size="lg">Report an incident</Button>
            </Link>
            <a href="#how-it-works">
              <Button size="lg" variant="outline">See how it works</Button>
            </a>
          </div>

          <p className="mt-4 text-xs text-slate-500">
            No login required. Works on slow networks.
          </p>
        </div>

        {/* Floating dashboard preview card */}
        <div className="mx-auto mt-14 max-w-4xl">
          <div className="relative rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/5 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-3 text-xs text-slate-500">reliefgrid.app / live</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-200">
              <PreviewStat label="Active incidents" value="34" tone="rose" />
              <PreviewStat label="Critical zones" value="6" tone="amber" />
              <PreviewStat label="Rescues dispatched" value="12" tone="emerald" />
            </div>
            <div className="border-t border-slate-200 p-5">
              <div className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-3">
                Latest AI-structured report
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <Badge variant="danger">Critical</Badge>
                  <Badge variant="secondary">Flood</Badge>
                  <span className="text-xs text-slate-500">Sylhet · 2 min ago</span>
                </div>
                <p className="text-sm text-slate-800">
                  "Water rising fast in Sunamganj, 3 villages cut off. Need
                  rescue boats and medical supplies."
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function PreviewStat({ label, value, tone }) {
  const tones = {
    rose: 'text-rose-600 bg-rose-50',
    amber: 'text-amber-600 bg-amber-50',
    emerald: 'text-emerald-600 bg-emerald-50',
  };
  return (
    <div className="p-5">
      <div className="text-xs uppercase tracking-wide text-slate-500 font-semibold">
        {label}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`inline-block rounded-md px-1.5 ${tones[tone]} text-2xl font-bold`}>
          {value}
        </span>
      </div>
    </div>
  );
}