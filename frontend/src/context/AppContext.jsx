import { createContext, useContext, useState, useCallback } from 'react';
import { setToken } from '../api.js';

// user: { role, name, username, patientId }   session: { patientId, expiresAt } (doctor only)
const Ctx = createContext(null);

export function AppProvider({ children }) {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [scanOpen, setScanOpen] = useState(false);
  // Page the doctor wanted before the scan. Opened right after a successful scan.
  const [pendingPath, setPendingPath] = useState(null);

  const logout = useCallback(() => {
    setUser(null);
    setSession(null);
    setToken(null);
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
