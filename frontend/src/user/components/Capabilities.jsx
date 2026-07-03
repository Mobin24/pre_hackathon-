import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '../../shared/components/ui/Card.jsx';

const FEATURES = [
  {
    icon: '🧠',
    title: 'AI report intake',
    body:
      'LLM extracts disaster type, severity, urgency, and required assistance from raw text + images.',
  },
  {
    icon: '📍',
    title: 'Geolocation intelligence',
    body:
      'Manual or auto-detected coordinates. Geocoded addresses. Live map with hotspot clustering.',
  },
  {
    icon: '🚁',
    title: 'Smart relief matching',
    body:
      'Scores volunteers, ambulances, and shelters by severity × distance × capacity.',
  },
  {
    icon: '📊',
    title: 'Real-time dashboard',
    body:
      'Authorities see a ranked view of active incidents, assignments, and resource status.',
  },
  {
    icon: '📝',
    title: 'Auto situation reports',
    body:
      'Hourly or on-demand summaries — exportable as PDF or shareable text.',
  },
  {
    icon: '🤝',
    title: 'Volunteer coordination',
    body:
      'Onboard, track, and route volunteers by skillset and proximity to active incidents.',
  },
];

export default function Capabilities() {
  return (
    <section id="capabilities" className="bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20">
        <div className="max-w-2xl">
          <span className="text-sm font-semibold uppercase tracking-wider text-blue-600">
            Core capabilities
          </span>
          <h2 className="mt-2 text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            One platform. Five critical systems.
          </h2>
          <p className="mt-4 text-slate-600">
            Everything authorities and citizens need to turn chaos into a
            coordinated response.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <Card key={f.title}>
              <CardHeader>
                <div className="text-2xl">{f.icon}</div>
                <CardTitle className="text-base">{f.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription className="text-sm leading-relaxed">
                  {f.body}
                </CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}