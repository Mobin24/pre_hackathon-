// Mocked-but-realistic stats shown in the landing strip.

const STATS = [
  { value: '2.4M+', label: 'People in disaster-prone districts' },
  { value: '< 90s', label: 'Avg. AI report processing time' },
  { value: '64', label: 'Districts covered' },
  { value: '24/7', label: 'Coordination uptime' },
];

export default function StatsStrip() {
  return (
    <section className="bg-slate-900 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
        <dl className="grid grid-cols-2 gap-y-8 gap-x-6 md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="text-center md:text-left">
              <dt className="text-xs uppercase tracking-wider text-slate-400">
                {s.label}
              </dt>
              <dd className="mt-1 text-2xl sm:text-3xl font-bold text-white">
                {s.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}