import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import UserNavbar from '../components/UserNavbar.jsx';
import UserFooter from '../components/UserFooter.jsx';
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
import { useUserAuth } from '../context/UserAuthContext.jsx';
import {
  signupSchema,
  signinSchema,
  formatZodError,
  fieldErrorsFromZod,
} from '../validation/authSchemas.js';

export default function UserLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signup, signin, isAuthed } = useUserAuth();
  const [mode, setMode] = useState(location.state?.intent === 'signup' ? 'signup' : 'signin');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Sign in fields
  const [identifier, setIdentifier] = useState('');
  const [signinPassword, setSigninPassword] = useState('');

  // Sign up fields
  const [fullName, setFullName] = useState('');
  const [nid, setNid] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // If already signed in, bounce them straight back.
  if (isAuthed) {
    const redirectTo = location.state?.from?.pathname || '/';
    navigate(redirectTo, { replace: true });
  }

  function validateSignup() {
    const result = signupSchema.safeParse({
      fullName,
      nid,
      phone,
      email,
      password: signupPassword,
      confirmPassword,
    });
    if (result.success) return { ok: true };
    return {
      ok: false,
      message: formatZodError(result.error),
      fields: fieldErrorsFromZod(result.error),
    };
  }

  function validateSignin() {
    const result = signinSchema.safeParse({
      identifier,
      password: signinPassword,
    });
    if (result.success) return { ok: true };
    return {
      ok: false,
      message: formatZodError(result.error),
      fields: fieldErrorsFromZod(result.error),
    };
  }

  function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (mode === 'signup') {
      const validation = validateSignup();
      if (!validation.ok) {
        setError(validation.message);
        return;
      }
      setBusy(true);
      const result = signup({
        fullName,
        nid,
        phone,
        email,
        password: signupPassword,
      });
      setBusy(false);
      if (!result.ok) {
        setError(result.message);
        return;
      }
    } else {
      const validation = validateSignin();
      if (!validation.ok) {
        setError(validation.message);
        return;
      }
      setBusy(true);
      const result = signin({ identifier, password: signinPassword });
      setBusy(false);
      if (!result.ok) {
        setError(result.message);
        return;
      }
    }

    const redirectTo = location.state?.from?.pathname || '/';
    navigate(redirectTo, { replace: true });
  }

  const isSignup = mode === 'signup';

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <UserNavbar />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <Card className="w-full max-w-lg">
          <CardHeader>
            <Link to="/" className="text-sm text-blue-600 hover:underline">
              ← Back to home
            </Link>
            <CardTitle className="mt-2">
              {isSignup ? 'Create your ReliefGrid account' : 'Sign in to ReliefGrid'}
            </CardTitle>
            <CardDescription>
              {isSignup
                ? 'Full name, email, and password are required. NID and phone are optional — but you must provide at least one contact method.'
                : 'Sign in to report incidents and follow up on your submissions.'}
            </CardDescription>
          </CardHeader>

          {/* Mode toggle */}
          <CardContent className="pt-0">
            <div className="grid grid-cols-2 gap-1 p-1 bg-slate-100 rounded-md text-sm font-medium">
              <button
                type="button"
                onClick={() => {
                  setMode('signin');
                  setError('');
                }}
                className={`py-2 rounded-sm transition ${
                  !isSignup
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode('signup');
                  setError('');
                }}
                className={`py-2 rounded-sm transition ${
                  isSignup
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                New sign up
              </button>
            </div>
          </CardContent>

          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              {isSignup && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="fullName">Full name</Label>
                    <Input
                      id="fullName"
                      placeholder="As shown on your NID"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      autoComplete="name"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="nid">
                      National ID (NID) <span className="text-slate-400">(optional)</span>
                    </Label>
                    <Input
                      id="nid"
                      placeholder="10 or 13 digit Bangladesh NID"
                      value={nid}
                      onChange={(e) => setNid(e.target.value)}
                      inputMode="numeric"
                      autoComplete="off"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="phone">
                      Phone (Bangladesh) <span className="text-slate-400">(optional)</span>
                    </Label>
                    <Input
                      id="phone"
                      placeholder="01712345678 or +8801712345678"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      autoComplete="tel"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="signupEmail">Email</Label>
                    <Input
                      id="signupEmail"
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      autoComplete="email"
                    />
                  </div>
                </>
              )}

              {!isSignup && (
                <div className="space-y-2">
                  <Label htmlFor="identifier">Email, phone, or NID</Label>
                  <Input
                    id="identifier"
                    placeholder="you@example.com / 017… / NID"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    autoComplete="username"
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="At least 8 characters"
                  value={isSignup ? signupPassword : signinPassword}
                  onChange={(e) =>
                    isSignup
                      ? setSignupPassword(e.target.value)
                      : setSigninPassword(e.target.value)
                  }
                  autoComplete={isSignup ? 'new-password' : 'current-password'}
                />
              </div>

              {isSignup && (
                <div className="space-y-2">
                  <Label htmlFor="confirm">Confirm password</Label>
                  <Input
                    id="confirm"
                    type="password"
                    placeholder="Re-enter password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
              )}

              {error && (
                <p className="text-sm text-red-600" role="alert">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full" disabled={busy}>
                {isSignup ? 'Create account' : 'Sign in'}
              </Button>
            </form>
          </CardContent>

          <Separator />

          <CardFooter>
            <p className="text-xs text-slate-500">
              {isSignup ? (
                <>
                  By signing up you agree to share your NID and contact
                  details with ReliefGrid coordinators for verified incident
                  reporting. Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signin');
                      setError('');
                    }}
                    className="text-blue-600 hover:underline"
                  >
                    Sign in
                  </button>
                  .
                </>
              ) : (
                <>
                  New to ReliefGrid?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signup');
                      setError('');
                    }}
                    className="text-blue-600 hover:underline"
                  >
                    Create an account
                  </button>
                  . Demo build — credentials are stored locally.
                </>
              )}
            </p>
          </CardFooter>
        </Card>
      </main>
      <UserFooter />
    </div>
  );
}