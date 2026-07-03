import { Link, useNavigate } from 'react-router-dom';
import Button from '../../shared/components/ui/Button.jsx';
import { useUserAuth } from '../context/UserAuthContext.jsx';

export default function UserNavbar() {
  const { user, isAuthed, signout } = useUserAuth();
  const navigate = useNavigate();

  function handleSignout() {
    signout();
    navigate('/', { replace: true });
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600 text-white font-bold">
            R
          </div>
          <span className="text-lg font-bold tracking-tight text-slate-900">
            Relief<span className="text-blue-600">Grid</span>
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-700">
          <a href="#how-it-works" className="hover:text-slate-900">How it works</a>
          <a href="#capabilities" className="hover:text-slate-900">Capabilities</a>
          <a href="#contact" className="hover:text-slate-900">Contact</a>
        </nav>

        <div className="flex items-center gap-2">
          <Link to="/admin/login" className="hidden sm:inline-block">
            <Button variant="ghost" size="sm">Admin</Button>
          </Link>

          {isAuthed ? (
            <div className="flex items-center gap-2">
              <span className="hidden sm:inline text-sm text-slate-700">
                Hi, <span className="font-semibold text-slate-900">{user.fullName.split(' ')[0]}</span>
              </span>
              <Button variant="outline" size="sm" onClick={handleSignout}>
                Sign out
              </Button>
              <Link to="/report">
                <Button size="sm">Report incident</Button>
              </Link>
            </div>
          ) : (
            <>
              <Link to="/login" className="hidden sm:inline-block">
                <Button variant="ghost" size="sm">Sign in</Button>
              </Link>
              <Link to="/report">
                <Button size="sm">Report incident</Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}