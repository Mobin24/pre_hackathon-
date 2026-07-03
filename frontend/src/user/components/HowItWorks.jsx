const STEPS = [
  {
    n: '01',
    title: 'You report',
    body:
      'Type a sentence, drop a photo, or share your live location. No forms, no accounts.',
  },
  {
    n: '02',
    title: 'AI structures it',
    body:
      'We extract disaster type, severity, urgency, and required aid in under 90 seconds.',
  },
  {
    n: '03',
    title: 'Geo + clustering',
    body:
      'Locations are geocoded and clustered to surface hotspots automatically.',
  },
  {
    n: '04',
    title: 'Matched relief',
    body:
      'Volunteers, ambulances, and shelters are dispatched by severity × distance × capacity.',
  },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-slate-50 border-y border-slate-200">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20">
        <div className="max-w-2xl">
          <span className="text-sm font-semibold uppercase tracking-wider text-blue-600">
            How it works
          </span>
          <h2 className="mt-2 text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            From a single sentence to dispatched aid.
          </h2>
        </div>

        <ol className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {STEPS.map((s) => (
            <li
              key={s.n}
              className="relative rounded-xl bg-white border border-slate-200 p-6"
            >
              <span className="absolute -top-3 left-6 rounded-full bg-blue-600 text-white text-xs font-bold px-2.5 py-1">
                {s.n}
              </span>
              <h3 className="mt-3 text-lg font-semibold text-slate-900">
                {s.title}
              </h3>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}