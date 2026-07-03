import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const UserAuthContext = createContext(null);

const USERS_KEY = 'rg_user_registry_v1';
const SESSION_KEY = 'rg_user_session_v1';

function readUsers() {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(USERS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

function readSession() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSession(user) {
  if (!user) {
    localStorage.removeItem(SESSION_KEY);
    return;
  }
  // Persist only safe, displayable fields — never the password hash.
  const safe = {
    id: user.id,
    fullName: user.fullName,
    email: user.email,
    phone: user.phone,
    nid: user.nid,
    signedInAt: new Date().toISOString(),
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(safe));
}

// Toy hash — demo only. Real backend will replace this.
function hash(value) {
  let h = 0;
  const s = String(value ?? '');
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return `h_${Math.abs(h).toString(16)}`;
}

export function UserAuthProvider({ children }) {
  const [user, setUser] = useState(() => readSession());

  // Keep multiple tabs in sync.
  useEffect(() => {
    function onStorage(e) {
      if (e.key === SESSION_KEY) {
        setUser(readSession());
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value = useMemo(() => {
    return {
      user,
      isAuthed: !!user,

      signup({ fullName, nid, phone, email, password }) {
        const users = readUsers();
        const exists = users.find(
          (u) =>
            u.email.toLowerCase() === email.toLowerCase() ||
            u.phone === phone ||
            u.nid === nid,
        );
        if (exists) {
          return {
            ok: false,
            code: 'duplicate',
            message: 'An account already exists with that email, phone, or NID.',
          };
        }
        const newUser = {
          id: `u_${Date.now().toString(36)}`,
          fullName: fullName.trim(),
          nid: nid.trim(),
          phone: phone.trim(),
          email: email.trim(),
          passwordHash: hash(password),
          createdAt: new Date().toISOString(),
        };
        writeUsers([...users, newUser]);
        writeSession(newUser);
        setUser(readSession());
        return { ok: true };
      },

      signin({ identifier, password }) {
        const users = readUsers();
        const id = String(identifier ?? '').trim();
        const found = users.find(
          (u) =>
            u.email.toLowerCase() === id.toLowerCase() ||
            u.phone === id ||
            u.nid === id,
        );
        if (!found || found.passwordHash !== hash(password)) {
          return {
            ok: false,
            code: 'invalid',
            message: 'Invalid credentials. Please check your details and try again.',
          };
        }
        writeSession(found);
        setUser(readSession());
        return { ok: true };
      },

      signout() {
        writeSession(null);
        setUser(null);
      },
    };
  }, [user]);

  return (
    <UserAuthContext.Provider value={value}>
      {children}
    </UserAuthContext.Provider>
  );
}

export function useUserAuth() {
  const ctx = useContext(UserAuthContext);
  if (!ctx) {
    throw new Error('useUserAuth must be used within a UserAuthProvider');
  }
  return ctx;
}