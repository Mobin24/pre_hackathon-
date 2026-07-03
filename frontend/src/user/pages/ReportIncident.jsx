import { useState } from 'react';
import UserNavbar from '../components/UserNavbar.jsx';
import UserFooter from '../components/UserFooter.jsx';
import ReportForm from '../components/ReportForm.jsx';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '../../shared/components/ui/Card.jsx';
import Button from '../../shared/components/ui/Button.jsx';
import Badge from '../../shared/components/ui/Badge.jsx';

function buildMockAnalysis(payload) {
  const text = (payload.description || '').toLowerCase();
  const danger = payload.immediateDanger;
  const count = Number(payload.affectedCount) || 0;

  let category = 'General Emergency';
  if (/flood|water|boat|river|monsoon/.test(text)) category = 'Flood / Water Rescue';
  else if (/fire|smoke|burn/.test(text)) category = 'Fire';
  else if (/building|collapse|wall|roof/.test(text)) category = 'Structural Collapse';
  else if (/medic|injured|injury|hospital|doctor/.test(text)) category = 'Medical Emergency';
  else if (/earthquake|quake|tremor/.test(text)) category = 'Earthquake';

  let severity = 'Medium';
  if (danger && count >= 50) severity = 'Critical';
  else if (danger || count >= 20) severity = 'High';
  else if (!danger && count === 0) severity = 'Low';

  const urgencyScore =
    (danger ? 50 : 10) +
    Math.min(count, 50) +
    (payload.assistance.length * 4);

  const entities = [
    payload.location?.area && `Area: ${payload.location.area}`,
    payload.location?.upazila && `Upazila: ${payload.location.upazila}`,
    payload.location?.district && `District: ${payload.location.district}`,
    count > 0 && `Affected: ~${count}`,
    danger && 'Immediate danger reported',
  ].filter(Boolean);

  const keywords = Array.from(
    new Set(
      (text.match(/\b[a-z]{4,}\b/g) || []).slice(0, 6),
    ),
  );

  return {
    category,
    severity,
    urgencyScore,
    entities,
    keywords,
    recommendedRelief: payload.assistance,
    location: payload.location,
    summary: payload.description
      ? payload.description.slice(0, 220)
      : 'No description provided.',
  };
}

function SeverityBadge({ level }) {
  const map = {
    Critical: 'bg-red-600 text-white',
    High: 'bg-orange-500 text-white',
    Medium: 'bg-amber-400 text-slate-900',
    Low: 'bg-emerald-500 text-white',
  };
  return (
    <Badge className={map[level] || 'bg-slate-500 text-white'}>
      {level} severity
    </Badge>
  );
}

export default function ReportIncident() {
  const [phase, setPhase] = useState('form'); // 'form' | 'analyzing' | 'preview'
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState('');

  function handleSubmit(payload) {
    if (!payload.location?.division) {
      setError('Please select a division before submitting.');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    if (!payload.description) {
      setError('Please describe the incident before submitting.');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    setError('');
    setPhase('analyzing');
    // Simulated AI structuring — replace with real API call later.
    setTimeout(() => {
      setAnalysis(buildMockAnalysis(payload));
      setPhase('preview');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }, 1600);
  }

  function handleNewReport() {
    setAnalysis(null);
    setPhase('form');
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <UserNavbar />
      <main className="flex-1 mx-auto w-full max-w-3xl px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-slate-900">
            Report an incident
          </h1>
          <p className="mt-2 text-slate-600">
            Your report goes to verified responders in your area. The more
            detail you share, the faster help arrives.
          </p>
        </div>

        {phase === 'form' && (
          <>
            {error && (
              <div
                role="alert"
                className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {error}
              </div>
            )}
            <ReportForm onSubmit={handleSubmit} />
          </>
        )}

        {phase === 'analyzing' && (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="flex flex-col items-center justify-center gap-4 py-16 text-center">
              <div className="h-12 w-12 rounded-full border-4 border-slate-200 border-t-red-600 animate-spin" />
              <div>
                <p className="text-lg font-semibold text-slate-900">
                  AI is analyzing your report…
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  Structuring the description, detecting severity, and routing
                  to the right teams.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {phase === 'preview' && analysis && (
          <div className="space-y-6">
            <Card className="border-emerald-200 bg-emerald-50 shadow-sm">
              <CardHeader>
                <CardTitle className="text-emerald-900">
                  ✓ Report received
                </CardTitle>
                <CardDescription className="text-emerald-800">
                  Here&apos;s the AI-structured preview. A volunteer admin will
                  review and dispatch shortly.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge level={analysis.severity} />
                  <Badge variant="secondary">{analysis.category}</Badge>
                  <Badge variant="outline">
                    Urgency score: {analysis.urgencyScore}
                  </Badge>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-slate-700 mb-1">
                    Summary
                  </h3>
                  <p className="text-sm text-slate-800 whitespace-pre-line">
                    {analysis.summary}
                  </p>
                </div>

                {analysis.location?.division && (
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-1">
                      Location
                    </h3>
                    <p className="text-sm text-slate-800">
                      {[
                        analysis.location.area,
                        analysis.location.upazila,
                        analysis.location.district,
                        analysis.location.division,
                      ]
                        .filter(Boolean)
                        .join(', ')}
                    </p>
                    {analysis.location.coords && (
                      <p className="text-xs text-slate-500 mt-1">
                        GPS: {analysis.location.coords.lat.toFixed(5)},{' '}
                        {analysis.location.coords.lng.toFixed(5)}
                      </p>
                    )}
                  </div>
                )}

                {analysis.entities.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-1">
                      Detected entities
                    </h3>
                    <ul className="text-sm text-slate-800 list-disc pl-5 space-y-0.5">
                      {analysis.entities.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {analysis.recommendedRelief.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-1">
                      Recommended relief dispatch
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {analysis.recommendedRelief.map((key) => (
                        <Badge key={key} variant="outline">
                          {key.replace(/_/g, ' ')}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {analysis.keywords.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-1">
                      Keywords
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {analysis.keywords.map((k) => (
                        <Badge key={k} variant="secondary">
                          #{k}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
              <CardFooter className="flex flex-col sm:flex-row gap-3">
                <Button onClick={handleNewReport} className="w-full sm:w-auto">
                  Submit another report
                </Button>
                <Button
                  variant="outline"
                  className="w-full sm:w-auto"
                  onClick={() => (window.location.href = '/')}
                >
                  Back to home
                </Button>
              </CardFooter>
            </Card>
          </div>
        )}
      </main>
      <UserFooter />
    </div>
  );
}