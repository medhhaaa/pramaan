import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getProfile, skipProfile } from '../api.js';
import HealthProfileForm from './HealthProfileForm.jsx';

// After a patient's first login (once the language is chosen): ask for the health profile.
// Shown until it is saved or the patient picks "Do it later"; the sidebar page can change it any time.
export default function ProfilePopup({ pid }) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    if (!pid) return;
    getProfile(pid).then(setProfile).catch(() => setProfile(null)); // never block the app on this
  }, [pid]);

  if (!profile?.needed) return null;
  const close = () => setProfile({ ...profile, needed: false });
  const later = () => { skipProfile(pid).catch(() => {}); close(); };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="profile-title">
      <div className="modal modal-profile card-lift">
        <h2 id="profile-title">{t('profile.title')}</h2>
        <HealthProfileForm pid={pid} initial={profile} onSaved={close} onLater={later} />
      </div>
    </div>
  );
}
