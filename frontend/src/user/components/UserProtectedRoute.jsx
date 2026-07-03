import { Navigate, useLocation } from 'react-router-dom';
import { useUserAuth } from '../context/UserAuthContext.jsx';

export default function UserProtectedRoute({ children }) {
  const { isAuthed } = useUserAuth();
  const location = useLocation();

  if (!isAuthed) {
    return (
      <Navigate to="/login" replace state={{ from: location, intent: 'report' }} />
    );
  }

  return children;
}