// Browser cache for screen state that should survive moving between pages and a page refresh:
// upload results and the assistant chat. (Medha)
//
// Kept in sessionStorage, like the login token: gone when the tab closes, and cleared on log out
// (clearSessionCache, called by AppContext.logout). Health data never goes to localStorage.
// Callers put the username and patient id in the key, so another login in the same tab never sees it.
//
// The value lives in memory first and is copied to sessionStorage on every change. Updates work
// even after the screen has closed: an upload that finishes while you are on another page still
// lands, and you see it when you come back.
import { useCallback, useSyncExternalStore } from 'react';

const PREFIX = 'pramaan_cache:';
const memory = new Map();    // key -> value
const listeners = new Map(); // key -> Set of callbacks

function load(key, fallback, revive) {
  if (memory.has(key)) return memory.get(key);
  let value = fallback;
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (raw !== null) value = revive ? revive(JSON.parse(raw)) : JSON.parse(raw);
  } catch { /* storage blocked or bad data: start fresh */ }
  memory.set(key, value);
  return value;
}

export function writeCache(key, value) {
  memory.set(key, value);
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch { /* storage full or blocked: the value stays in memory for this page */ }
  (listeners.get(key) || []).forEach((notify) => notify());
}

export function clearSessionCache() {
  memory.clear();
  try {
    Object.keys(sessionStorage).filter((k) => k.startsWith(PREFIX)).forEach((k) => sessionStorage.removeItem(k));
  } catch { /* storage blocked: nothing was saved there */ }
  listeners.forEach((set) => set.forEach((notify) => notify()));
}

// Like useState, but cached under `key`. revive(saved) runs once when a value comes back from
// sessionStorage after a page refresh (e.g. an upload that was running is no longer running).
export function useCachedState(key, fallback, revive) {
  const subscribe = useCallback((notify) => {
    if (!listeners.has(key)) listeners.set(key, new Set());
    listeners.get(key).add(notify);
    return () => listeners.get(key).delete(notify);
  }, [key]);
  const value = useSyncExternalStore(subscribe, () => load(key, fallback, revive));
  const set = useCallback((next) => {
    const current = load(key, fallback, revive);
    writeCache(key, typeof next === 'function' ? next(current) : next);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return [value, set];
}
