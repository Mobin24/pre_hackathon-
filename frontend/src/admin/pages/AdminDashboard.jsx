import { Link } from 'react-router-dom';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '../../shared/components/ui/Card.jsx';
import Button from '../../shared/components/ui/Button.jsx';

export default function AdminDashboard() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-blue-600" />
            <span className="font-semibold text-slate-900">
              ReliefGrid · Admin
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              View public site
            </Link>
            <Button
              variant="outline"
              onClick={() => {
                localStorage.removeItem('rg_admin_auth');
                window.location.href = '/admin/login';
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Operations dashboard
          </h1>
          <p className="text-slate-600">
            All reports submitted from the public site will appear here with AI
            structure, severity, geo, and recommended relief actions.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            ['Active incidents', '—'],
            ['Critical zones', '—'],
            ['Rescues dispatched', '—'],
            ['Avg. response time', '—'],
          ].map(([label, value]) => (
            <Card key={label}>
              <CardHeader>
                <CardDescription>{label}</CardDescription>
                <CardTitle className="text-3xl">{value}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Incoming reports</CardTitle>
            <CardDescription>
              Wires up to the report intake API in the next step.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-600">
              Once the public Report Incident form is connected, every
              submission (with consent) will be AI-structured and queued here
              for triage, geo-tagging, and relief matching.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}