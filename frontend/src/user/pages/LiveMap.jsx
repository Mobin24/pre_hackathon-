import UserNavbar from '../components/UserNavbar.jsx';
import UserFooter from '../components/UserFooter.jsx';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '../../shared/components/ui/Card.jsx';

export default function LiveMap() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <UserNavbar />
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
        <Card>
          <CardHeader>
            <CardTitle>Live incident map</CardTitle>
            <CardDescription>
              Public view of recent incidents with severity clustering.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="aspect-video w-full rounded-lg bg-gradient-to-br from-slate-100 to-slate-200 border border-slate-200 flex items-center justify-center text-slate-500 text-sm">
              Map placeholder — geocoding + clustering wires up next.
            </div>
          </CardContent>
        </Card>
      </main>
      <UserFooter />
    </div>
  );
}