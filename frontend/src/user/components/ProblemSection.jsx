// "The Problem" — why this platform exists.

const PROBLEMS = [
  {
    title: 'Fragmented information',
    body:
      'Reports scattered across Facebook posts, phone calls, and walk-ins. Authorities waste hours assembling a coherent picture.',
  },
  {
    title: 'No severity triage',
    body:
      'A flooded village and a fallen tree look identical in the queue. Critical cases wait while low-urgency ones clog the channel.',
  },
  {
    title: 'Slow matching',
    body:
      'Volunteers, ambulances, and shelters are dispatched by hand. Distance, capacity, and urgency are rarely balanced together.',
  },
];

export default function ProblemSection() {
  return (
    <section className="bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20">
        <div className="max-w-2xl">
          <span className="text-sm font-semibold uppercase tracking-wider text-blue-600">
            The problem
          </span>
          <h2 className="mt-2 text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            Coordination breaks when seconds matter.
          </h2>
          <p className="mt-4 text-slate-600">
            In floods, cyclones, and landslides, the bottleneck is not data — it
            is structure. ReliefGrid turns chaotic citizen reports into a single,
            ranked, actionable picture.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          {PROBLEMS.map((p) => (
            <div
              key={p.title}
              className="rounded-xl border border-slate-200 bg-slate-50 p-6"
            >
              <div className="h-8 w-8 rounded-md bg-rose-100 text-rose-600 flex items-center justify-center font-bold">
                !
              </div>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">
                {p.title}
              </h3>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                {p.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}