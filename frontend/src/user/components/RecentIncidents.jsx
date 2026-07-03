import { Link } from 'react-router-dom';
import Badge from '../../shared/components/ui/Badge.jsx';
import { timeAgo } from '../../utils/format.js';

const SAMPLE = [
  {
    id: 'RPT-1002',
    title: 'Suspected dengue cluster in Sector 7',
    location: 'Sector 7, Lane 9',
    severity: 'critical',
    category: 'Health',
    submittedAt: new Date(Date.now() - 1000 * 60 * 50).toISOString(),
  },
  {
    id: 'RPT-1001',
    title: 'Power outage in Block B substation',
    location: 'Block B, Sector 4',
    severity: 'high',
    category: 'Infrastructure',
    submittedAt: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(),
  },
  {
    id: 'RPT-1006',
    title: 'Suspicious activity near warehouse',
    location: 'Warehouse District, Gate 3',
    severity: 'high',
    category: 'Security',
    submittedAt: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
  },
  {
    id: 'RPT-1003',
    title: 'Illegal dumping near riverside',
    location: 'East Riverbank',
    severity: 'medium',
    category: 'Environment',
    submittedAt: new Date(Date.now() - 1000 * 60 * 60 * 30).toISOString(),
  },
];

const SEVERITY_VARIANT = {
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'success',
};

export default function RecentIncidents() {
  return (
    <section id="incidents" className="bg-slate-50 border-y border-slate-200">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20">
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div>
            <span className="text-sm font-semibold uppercase tracking-wider text-blue-600">
              Live feed
            </span>
            <h2 className="mt-2 text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
              What people are reporting right now.
            </h2>
          </div>
          <Link
            to="/incidents"
            className="text-sm font-medium text-blue-600 hover:underline"
          >
            View all incidents →
          </Link>
        </div>

        <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {SAMPLE.map((r) => (
            <Link
              key={r.id}
              to={`/incidents/${r.id}`}
              className="group block rounded-xl border border-slate-200 bg-white p-5 hover:border-blue-300 hover:shadow-md transition"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant={SEVERITY_VARIANT[r.severity]}>
                  {r.severity}
                </Badge>
                <Badge variant="secondary">{r.category}</Badge>
              </div>
              <h3 className="mt-3 text-sm font-semibold text-slate-900 group-hover:text-blue-700 line-clamp-2">
                {r.title}
              </h3>
              <p className="mt-1 text-xs text-slate-500">{r.location}</p>
              <p className="mt-3 text-xs text-slate-400">{timeAgo(r.submittedAt)}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}