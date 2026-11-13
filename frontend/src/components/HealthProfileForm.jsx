import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { saveProfile } from '../api.js';
import '../styles/profile.css';

// The patient's health profile: date of birth, sex, blood group, allergies (+ reaction).
// Every answer is optional. The backend stores them as "patient-reported" facts, shown to the
// doctor next to what the records say (backend/routes/profile.py). "I don't know" stores nothing.
// Used in the first-login popup (App.jsx) and on the Health profile page.
const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const SEXES = ['Female', 'Male', 'Other'];
const FIELD_KEY = { dob: 'profile.dob', sex: 'profile.sex', blood_group: 'profile.bloodGroup' };
const EMPTY_ALLERGY = { name: '', reaction: '' };

export default function HealthProfileForm({ pid, initial, onSaved, onLater }) {
  const { t } = useTranslation();
  const [dob, setDob] = useState(initial?.dob || '');
  const [sex, setSex] = useState(initial?.sex || '');
  const [bloodGroup, setBloodGroup] = useState(initial?.blood_group || '');
  const [allergyAnswer, setAllergyAnswer] = useState(initial?.allergy_answer || '');
  const [allergies, setAllergies] = useState(
    initial?.allergies?.length ? initial.allergies.map((a) => ({ name: a.name, reaction: a.reaction || '' })) : [EMPTY_ALLERGY],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null); // the saved profile (with mismatches)

  const setAllergy = (i, key, value) => setAllergies(allergies.map((a, j) => (j === i ? { ...a, [key]: value } : a)));
  const today = new Date().toISOString().slice(0, 10);

  const submit = async (e) => {
    e.preventDefault();
    const typed = allergies.filter((a) => a.name.trim()).map((a) => ({ name: a.name.trim(), reaction: a.reaction.trim() || null }));
    if (allergyAnswer === 'yes' && typed.length === 0) { setError(t('profile.needOneAllergy')); return; }
    setBusy(true);
    setError('');
    try {
      const saved = await saveProfile(pid, {
        dob: dob || null,
        sex: sex || null,
        blood_group: bloodGroup || null,
        allergy_answer: allergyAnswer || null,
        allergies: allergyAnswer === 'yes' ? typed : [],
      });
      if (saved.mismatches?.length) setResult(saved); // show what differs before closing
      else onSaved?.(saved);
    } catch (err) {
      // our own 422 messages are plain text ("Date of birth must be between 1900 and today")
      setError(err.status === 422 && typeof err.detail === 'string' ? err.detail : t('profile.saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="profile-form">
        <h3>{t('profile.mismatchTitle')}</h3>
        <ul className="profile-mismatches">
          {result.mismatches.map((m) => (
            <li key={`${m.field}-${m.records_say}`} className="card alert-warn">
              <strong>{t(FIELD_KEY[m.field])}</strong>
              <div>{t('profile.mismatch', { you_said: m.you_said, records_say: m.records_say, source: m.source })}</div>
            </li>
          ))}
        </ul>
        <button className="btn btn-primary btn-block" onClick={() => onSaved?.(result)}>{t('profile.done')}</button>
      </div>
    );
  }

  return (
    <form className="profile-form" onSubmit={submit}>
      <p className="muted small">{t('profile.intro')}</p>

      <label className="profile-field">
        <span className="field-label">{t('profile.dob')}</span>
        <input className="input" type="date" value={dob} max={today} min="1900-01-01" onChange={(e) => setDob(e.target.value)} />
      </label>

      <div className="profile-row">
        <label className="profile-field">
          <span className="field-label">{t('profile.sex')}</span>
          <select className="input" value={sex} onChange={(e) => setSex(e.target.value)}>
            <option value="">{t('profile.notAnswered')}</option>
            {SEXES.map((s) => <option key={s} value={s}>{t(`profile.${s.toLowerCase()}`)}</option>)}
          </select>
        </label>
        <label className="profile-field">
          <span className="field-label">{t('profile.bloodGroup')}</span>
          <select className="input" value={bloodGroup} onChange={(e) => setBloodGroup(e.target.value)}>
            <option value="">{t('profile.dontKnow')}</option>
            {BLOOD_GROUPS.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>
      </div>

      <fieldset className="profile-field">
        <legend className="field-label">{t('profile.allergies')}</legend>
        <div className="profile-choices" role="radiogroup">
          {[['yes', 'profile.allergyYes'], ['none', 'profile.allergyNone'], ['dont_know', 'profile.dontKnow']].map(([value, key]) => (
            <label key={value} className={`radio-row ${allergyAnswer === value ? 'selected' : ''}`}>
              <input type="radio" name="allergy" value={value} checked={allergyAnswer === value} onChange={() => setAllergyAnswer(value)} />
              <span>{t(key)}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {allergyAnswer === 'yes' && (
        <div className="profile-allergies">
          {allergies.map((a, i) => (
            <div key={i} className="profile-allergy">
              <label className="profile-field">
                <span className="field-label">{t('profile.allergyName')}</span>
                <input className="input" value={a.name} placeholder={t('profile.allergyNamePh')} maxLength={60}
                  onChange={(e) => setAllergy(i, 'name', e.target.value)} />
              </label>
              <label className="profile-field">
                <span className="field-label">{t('profile.reaction')}</span>
                <input className="input" value={a.reaction} placeholder={t('profile.reactionPh')} maxLength={80}
                  onChange={(e) => setAllergy(i, 'reaction', e.target.value)} />
              </label>
              {allergies.length > 1 && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAllergies(allergies.filter((_, j) => j !== i))}>
                  {t('profile.remove')}
                </button>
              )}
            </div>
          ))}
          {allergies.length < 20 && (
            <button type="button" className="link-btn" onClick={() => setAllergies([...allergies, EMPTY_ALLERGY])}>{t('profile.addAllergy')}</button>
          )}
        </div>
      )}

      {error && <p className="error-text small" role="alert">{error}</p>}
      <div className="btn-row profile-actions">
        <button className="btn btn-primary" type="submit" disabled={busy}>{t('profile.save')}</button>
        {onLater && <button className="btn btn-ghost" type="button" onClick={onLater} disabled={busy}>{t('profile.later')}</button>}
      </div>
    </form>
  );
}
