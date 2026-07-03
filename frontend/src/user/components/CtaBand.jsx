import { Link, useNavigate } from 'react-router-dom';
import Button from '../../shared/components/ui/Button.jsx';
import { useUserAuth } from '../context/UserAuthContext.jsx';

export default function CtaBand() {
  const { isAuthed } = useUserAuth();
  const navigate = useNavigate();

  function handleReportClick() {
    navigate(isAuthed ? '/report' : '/login', {
      state: isAuthed ? undefined : { from: { pathname: '/report' }, intent: 'report' },
    });
  }

  return (
    <section className="bg-blue-600 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 text-center">
        <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
          See something? Say something.
        </h2>
        <p className="mt-3 text-blue-100 max-w-2xl mx-auto">
          Your 30-second report could be the difference between a coordinated
          rescue and a delayed one.
        </p>
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Button size="lg" variant="secondary" onClick={handleReportClick}>
            Report an incident
          </Button>
          <Link to="/incidents">
            <Button size="lg" variant="ghost" className="text-white hover:bg-blue-700">
              View live map
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}