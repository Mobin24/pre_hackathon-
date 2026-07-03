import AppRouter from './router.jsx';
import { UserAuthProvider } from './user/context/UserAuthContext.jsx';

export default function App() {
  return (
    <UserAuthProvider>
      <AppRouter />
    </UserAuthProvider>
  );
}
