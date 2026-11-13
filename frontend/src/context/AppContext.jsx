import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { setToken, hasToken } from '../api.js';
import { clearSessionCache } from '../lib/sessionCache.js';

// user: { role, name, username, patientId }   session: { patientId, expiresAt } (doctor only)
const Ctx = createContext(null);

// Kept in sessionStorage next to the token so a page refresh doesn't log you out.
function load(key) {
  try { return JSON.parse(sessionStorage.getItem(key)); } catch { return null; }
}
function save(key, value) {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value));
    else sessionStorage.removeItem(key);
  } catch { /* storage blocked: state stays in memory only */ }
}

export function AppProvider({ children }) {
  // a saved user without a token (or the other way round) is not a usable login
  const [user, setUser] = useState(() => (hasToken() ? load('pramaan_user') : null));
  const [session, setSession] = useState(() => (hasToken() ? load('pramaan_session') : null));

  useEffect(() => save('pramaan_user', user), [user]);
  useEffect(() => save('pramaan_session', session), [session]);
  const [scanOpen, setScanOpen] = useState(false);
  // Page the doctor wanted before the scan. Opened right after a successful scan.
  const [pendingPath, setPendingPath] = useState(null);

  const logout = useCallback(() => {
    setUser(null);
    setSession(null);
    setToken(null);
    clearSessionCache(); // cached upload reports and assistant chats (lib/sessionCache.js)
  }, []);

  const value = { user, setUser, session, setSession, logout, scanOpen, setScanOpen, pendingPath, setPendingPath };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useApp = () => useContext(Ctx);

// The patient whose data the current screen may show.
export function useActivePatientId() {
  const { user, session } = useApp();
  if (!user) return null;
  if (user.role === 'patient') return user.patientId;
  return session && session.expiresAt > Date.now() ? session.patientId : null;
}
