import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import UserFooter from '../../user/components/UserFooter.jsx';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '../../shared/components/ui/Card.jsx';
import Input from '../../shared/components/ui/Input.jsx';
import Label from '../../shared/components/ui/Label.jsx';
import Button from '../../shared/components/ui/Button.jsx';
import Separator from '../../shared/components/ui/Separator.jsx';

export default function AdminLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  const [adminId, setAdminId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    // Demo: any non-empty credentials pass. Wire to real auth in backend step.
    if (!adminId.trim() || !password.trim()) {
      setError('Please enter both your admin ID and password.');
      return;
    }
    localStorage.setItem('rg_admin_auth', '1');
    const redirectTo = location.state?.from?.pathname || '/admin/dashboard';
    navigate(redirectTo, { replace: true });
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <Card className="w-full max-w-md">
          <CardHeader>
            <Link to="/" className="text-sm text-blue-600 hover:underline">
              ← Back to home
            </Link>
            <CardTitle className="mt-2">Admin sign in</CardTitle>
            <CardDescription>
              Restricted access for ReliefGrid coordinators.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="admin-id">Admin ID</Label>
                <Input
                  id="admin-id"
                  placeholder="admin@reliefgrid"
                  autoComplete="username"
                  value={adminId}
                  onChange={(e) => setAdminId(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin-pass">Password</Label>
                <Input
                  id="admin-pass"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <p className="text-sm text-red-600" role="alert">
                  {error}
                </p>
              )}
              <Button type="submit" className="w-full">
                Sign in
              </Button>
            </form>
          </CardContent>
          <Separator />
          <CardFooter>
            <p className="text-xs text-slate-500">
              Demo build — authentication is mocked. The dashboard will be
              wired in the next step.
            </p>
          </CardFooter>
        </Card>
      </main>
      <UserFooter />
    </div>
  );
}