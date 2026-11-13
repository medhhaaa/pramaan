import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import {
  addCareTeamDoctor, getAccessHistory, getCareTeam, getConditionTags, keepCareTeamDoctor,
  revokeCareTeamDoctor, searchDoctors,
} from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import { parseUtc, useAgo } from './MyPatients.jsx';
import '../styles/care-team.css';

// My Care Team (patient): the doctors who may see your records until you revoke them.
// Scope "all" or only some conditions. Allergies are always visible to them (safety).
// API: backend/routes/care_team.py. Access is checked in backend/auth.py.

const shortDate = (s) => (parseUtc(s) ? parseUtc(s).toISOString().slice(0, 10) : '');

function AddDoctor({ pid, tags, onAdded }) {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const [results, setResults] = useState(null);
  const [doctor, setDoctor] = useState(null);
  const [mode, setMode] = useState('all');
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const search = async (e) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setError('');
    setDoctor(null);
    try { setResults(await searchDoctors(q.trim())); } catch (err) { setError(err.message); }
  };

  const toggle = (tag) => setPicked((p) => (p.includes(tag) ? p.filter((x) => x !== tag) : [...p, tag]));

  const confirm = async () => {
    setBusy(true);
    setError('');
    try {
      await addCareTeamDoctor(pid, doctor.id, mode === 'all' ? 'all' : picked);
      setQ(''); setResults(null); setDoctor(null); setMode('all'); setPicked([]);
      onAdded();
    } catch (err) {
      setError(err.message.includes('409') || err.message.includes('already') ? t('careTeam.already') : err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card mt">
      <h2>{t('careTeam.addTitle')}</h2>
      <form onSubmit={search} className="search">
        <Search size={18} />
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('careTeam.searchHint')} aria-label={t('careTeam.searchHint')} />
        <button className="btn btn-ghost" type="submit" disabled={q.trim().length < 2}>{t('careTeam.search')}</button>
      </form>

      {results && results.length === 0 && <p className="muted small">{t('careTeam.noDoctors')}</p>}
      {results && results.length > 0 && !doctor && (
        <ul className="list doctor-results">
          {results.map((d) => (
            <li key={d.id}>
              <button className="link-btn" onClick={() => setDoctor(d)}>{d.name}</button>
              <span className="muted small"> · {t('careTeam.regNo')} {d.registration_number || '?'}</span>
            </li>
          ))}
        </ul>
      )}

      {doctor && (
        <div className="stack mt">
          <p><strong>{doctor.name}</strong> <span className="muted small">· {t('careTeam.regNo')} {doctor.registration_number}</span></p>
          <p className="field-label">{t('careTeam.scopeQuestion', { name: doctor.name })}</p>
          <label className={`radio-row ${mode === 'all' ? 'selected' : ''}`}>
            <input type="radio" name="scope" checked={mode === 'all'} onChange={() => setMode('all')} />
            <span>{t('careTeam.scopeAll')}</span>
          </label>
          <label className={`radio-row ${mode === 'some' ? 'selected' : ''}`}>
            <input type="radio" name="scope" checked={mode === 'some'} onChange={() => setMode('some')} />
            <span>{t('careTeam.scopeSome')}</span>
          </label>
          {mode === 'some' && (
            <div className="chip-row">
              {tags.map((tag) => (
                <label key={tag.tag} className={`answer ${picked.includes(tag.tag) ? 'selected' : ''}`}>
                  <input type="checkbox" className="sr-only" checked={picked.includes(tag.tag)} onChange={() => toggle(tag.tag)} />
                  {t(`careTeam.tagName.${tag.tag}`, tag.label)}
                </label>
              ))}
            </div>
          )}
          <p className="muted small">{t('careTeam.allergyNote')}</p>
          <div className="btn-row">
            <button className="btn btn-primary" onClick={confirm} disabled={busy || (mode === 'some' && picked.length === 0)}>
              {t('careTeam.confirmAdd', { name: doctor.name })}
            </button>
            <button className="btn btn-ghost" onClick={() => setDoctor(null)}>{t('careTeam.cancel')}</button>
          </div>
        </div>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default function MyCareTeam({ embedded = false }) {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const ago = useAgo();
  const [team, setTeam] = useState(null);
  const [history, setHistory] = useState([]);
  const [tags, setTags] = useState([]);
  const [confirming, setConfirming] = useState(null); // entry id waiting for "Yes, revoke"
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (!pid) return;
    getCareTeam(pid).then(setTeam).catch((e) => setError(e.message));
    getAccessHistory(pid).then(setHistory).catch(() => {});
  }, [pid]);
  useEffect(() => { load(); getConditionTags().then(setTags).catch(() => {}); }, [load]);

  const act = async (fn) => {
    setError('');
    try { await fn(); setConfirming(null); load(); } catch (e) { setError(e.message); }
  };

  if (error && !team) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!team) return <div className="skeleton" />;

  const active = team.filter((e) => e.status === 'active');
  const revoked = team.filter((e) => e.status === 'revoked');
  const scopeText = (e) => (e.scope === 'all' ? t('careTeam.scopeAllShort')
    : e.scope.map((s) => t(`careTeam.tagName.${s}`, s)).join(', '));

  return (
    <section className="care-team">
      {!embedded && <div className="page-head"><h1>{t('careTeam.title')}</h1></div>}
      <p className="muted small">{t('careTeam.intro')}</p>

      {active.filter((e) => e.review_due).map((e) => (
        <div key={`review-${e.id}`} className="card review-banner mt" role="status">
          <p><strong>{t('careTeam.reviewQuestion', { name: e.doctor.name })}</strong></p>
          <p className="small">{t('careTeam.reviewWhy')}</p>
          <div className="btn-row">
            <button className="btn btn-primary" onClick={() => act(() => keepCareTeamDoctor(pid, e.id))}>{t('careTeam.keep')}</button>
            <button className="btn btn-ghost" onClick={() => act(() => revokeCareTeamDoctor(pid, e.id))}>{t('careTeam.remove')}</button>
          </div>
        </div>
      ))}

      {error && <p className="error-text">{error}</p>}

      <h2 className="mt">{t('careTeam.yourDoctors')}</h2>
      {active.length === 0 && <div className="card"><p className="muted">{t('careTeam.none')}</p></div>}
      <ul className="list">
        {active.map((e) => (
          <li key={e.id} className="card team-row">
            <div>
              <strong>{e.doctor.name}</strong>
              <span className="muted small"> · {t('careTeam.regNo')} {e.doctor.registration_number || '?'}</span>
              <div className="small">{t('careTeam.sees')}: {scopeText(e)}</div>
              <div className="muted small">
                {t('careTeam.added')} {shortDate(e.created_at)} · {t('careTeam.lastViewed')}: {e.last_viewed_at ? ago(e.last_viewed_at) : t('myPatients.never')}
              </div>
            </div>
            {confirming === e.id ? (
              <div className="btn-row">
                <button className="btn btn-danger" onClick={() => act(() => revokeCareTeamDoctor(pid, e.id))}>{t('careTeam.yesRevoke')}</button>
                <button className="btn btn-ghost" onClick={() => setConfirming(null)}>{t('careTeam.cancel')}</button>
              </div>
            ) : (
              <button className="btn btn-ghost" onClick={() => setConfirming(e.id)}>{t('careTeam.revoke')}</button>
            )}
          </li>
        ))}
      </ul>

      <AddDoctor pid={pid} tags={tags} onAdded={load} />

      <h2 className="mt">{t('careTeam.historyTitle')}</h2>
      {history.length === 0 && <p className="muted small">{t('careTeam.noHistory')}</p>}
      <ul className="list access-history">
        {history.map((h) => (
          <li key={`${h.doctor_id}-${h.day}`} className="small">
            {t('careTeam.viewedOn', { name: h.doctor_name, date: h.day })}
          </li>
        ))}
      </ul>

      {revoked.length > 0 && (
        <details className="mt">
          <summary className="muted small">{t('careTeam.revokedTitle', { count: revoked.length })}</summary>
          <ul className="list">
            {revoked.map((e) => (
              <li key={e.id} className="muted small">
                {e.doctor.name} · {t('careTeam.revokedOn', { date: shortDate(e.revoked_at) || e.revoked_at?.slice(0, 10) })}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
