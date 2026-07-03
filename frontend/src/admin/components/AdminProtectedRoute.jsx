import { Navigate, useLocation } from 'react-router-dom';

export default function AdminProtectedRoute({ children }) {
  const location = useLocation();
  const isAuthed =
    typeof window !== 'undefined' &&
    localStorage.getItem('rg_admin_auth') === '1';

  if (!isAuthed) {
    return <Navigate to="/admin/login" replace state={{ from: location }} />;
  }

  return children;
}