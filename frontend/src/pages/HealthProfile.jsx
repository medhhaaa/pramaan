import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getProfile } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import HealthProfileForm from '../components/HealthProfileForm.jsx';
import LoadError from '../components/LoadError.jsx';

// Patient page: see and change the health profile (date of birth, sex, blood group, allergies).
export default function HealthProfile() {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [version, setVersion] = useState(0); // remounts the form with the saved answers

  useEffect(() => { getProfile(pid).then(setProfile).catch((e) => setError(e.message)); }, [pid]);

  if (error) return <LoadError message={error} />;
  return (
    <section>
      <div className="page-head"><h1>{t('profile.title')}</h1></div>
      <div className="card">
        {saved && <p className="chip chip-doc" role="status">{t('profile.saved')}</p>}
        {profile && (
          <HealthProfileForm key={version} pid={pid} initial={profile}
            onSaved={(p) => { setProfile(p); setSaved(true); setVersion((v) => v + 1); }} />
        )}
      </div>
    </section>
  );
}
