// Screens that can be switched on or off in .env.local (see .env.example).
// Ask my records is hidden unless VITE_ENABLE_ASK=true; its backend route (POST /patients/{id}/ask) stays.
export const ASK_ON = import.meta.env.VITE_ENABLE_ASK === 'true';
