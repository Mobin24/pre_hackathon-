import { Link } from 'react-router-dom';
import Button from '../../shared/components/ui/Button.jsx';
import UserNavbar from '../components/UserNavbar.jsx';
import UserFooter from '../components/UserFooter.jsx';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <UserNavbar />
      <main className="flex-1 flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <p className="text-sm font-semibold text-blue-600">404</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">
            Page not found
          </h1>
          <p className="mt-3 text-slate-600">
            The page you are looking for does not exist or has been moved.
          </p>
          <Link to="/" className="inline-block mt-6">
            <Button>Back to home</Button>
          </Link>
        </div>
      </main>
      <UserFooter />
    </div>
  );
}