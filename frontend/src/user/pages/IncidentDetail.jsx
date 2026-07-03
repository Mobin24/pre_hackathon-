import { Link, useParams } from 'react-router-dom';
import UserNavbar from '../components/UserNavbar.jsx';
import UserFooter from '../components/UserFooter.jsx';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '../../shared/components/ui/Card.jsx';
import Button from '../../shared/components/ui/Button.jsx';

export default function IncidentDetail() {
  const { id } = useParams();

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <UserNavbar />
      <main className="flex-1 mx-auto w-full max-w-3xl px-4 sm:px-6 lg:px-8 py-12">
        <Card>
          <CardHeader>
            <Link
              to="/incidents"
              className="text-sm text-blue-600 hover:underline"
            >
              ← All incidents
            </Link>
            <CardTitle className="mt-2">Incident #{id}</CardTitle>
            <CardDescription>
              Detailed view with AI insight breakdown coming in the next step.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-600">
              Severity, category, geo coordinates, structured AI entities,
              recommended relief actions, and timeline will render here.
            </p>
            <Link to="/" className="inline-block mt-6">
              <Button variant="outline">Back to home</Button>
            </Link>
          </CardContent>
        </Card>
      </main>
      <UserFooter />
    </div>
  );
}