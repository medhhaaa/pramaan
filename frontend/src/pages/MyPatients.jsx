import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { getMyPatients, setFollowUp } from '../api.js';
import { useApp } from '../context/AppContext.jsx';
import '../styles/care-team.css';

// My Patients (doctor): patients who added this doctor to their care team, with tags.
// Tags and order come from the backend (backend/routes/care_team.py). The app shows records
// and counts only; it never recommends what to do.

const POLL_MS = 10000; // live updates for the hackathon: poll every 10 seconds
export const TAGS = ['refill_request', 'new_report', 'missed_doses', 'followup_overdue', 'stable'];
export const TAG_CHIP = {
  refill_request: 'chip-danger', new_report: 'chip-info', missed_doses: 'chip-warn',
  followup_overdue: 'chip-neutral', stable: 'chip-verified',
};
const CARE_TEAM_SESSION_MS = 12 * 60 * 60 * 1000; // same as a login token

// backend times are UTC "YYYY-MM-DD HH:MM:SS"
export function parseUtc(s) {
  return s ? new Date(`${s.replace(' ', 'T')}Z`) : null;
}

export function useAgo() {
  const { t } = useTranslation();
  return (s) => {
    const d = parseUtc(s);
    if (!d) return t('myPatients.never');
    // calendar days in the viewer's time zone, so "yesterday" means yesterday's date
    const midnight = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const days = Math.round((midnight(new Date()) - midnight(d)) / 86400000);
    if (days <= 0) return t('myPatients.today');
    if (days === 1) return t('myPatients.yesterday');
    return t('myPatients.daysAgo', { count: days });
  };
}

function FollowUp({ row, onSaved }) {
  const { t } = useTranslation();
  const [value, setValue] = useState(row.followup_on || '');
  const save = async (date) => {
    setValue(date);
    await setFollowUp(row.patient_id, date || null);
    onSaved();
  };
  return (
    <label className="field-label small followup" onClick={(e) => e.stopPropagation()}>
      {t('myPatients.followUp')}
      <input type="date" className="input" value={value} onChange={(e) => save(e.target.value)} />
    </label>
  );
}

export default function MyPatients() {
  const { t } = useTranslation();
  const { setSession } = useApp();
  const navigate = useNavigate();
  const ago = useAgo();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');

  const load = useCallback(() => {
    getMyPatients().then((r) => { setRows(r); setError(''); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const open = (row) => {
    // care-team access is lasting: the "session" only tells the screens which patient is open
    setSession({ patientId: row.patient_id, expiresAt: Date.now() + CARE_TEAM_SESSION_MS, careTeam: true });
    navigate('/brief');
  };

  if (error && !rows) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!rows) return <div className="skeleton" />;

  const count = (tag) => rows.filter((r) => r.tags.includes(tag)).length;
  const shown = rows.filter((r) => (filter === 'all' || r.tags.includes(filter))
    && r.name.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <section className="my-patients">
      <div className="page-head">
        <h1>{t('myPatients.title')}</h1>
        <span className="muted">{t('myPatients.count', { count: rows.length })}</span>
      </div>
      <p className="muted small">{t('myPatients.intro')}</p>

      <div className="search">
        <Search size={18} />
        <input className="input" placeholder={t('patients.search')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('patients.search')} />
      </div>
      <div className="chip-row filter-row" role="group" aria-label={t('myPatients.filter')}>
        <button className={`answer ${filter === 'all' ? 'selected' : ''}`} onClick={() => setFilter('all')}>
          {t('myPatients.all')} ({rows.length})
        </button>
        {TAGS.map((tag) => (
          <button key={tag} className={`answer ${filter === tag ? 'selected' : ''}`} onClick={() => setFilter(tag)} aria-pressed={filter === tag}>
            {t(`myPatients.tag.${tag}`)} ({count(tag)})
          </button>
        ))}
      </div>

      {rows.length === 0 && <div className="empty-state card"><p>{t('myPatients.empty')}</p></div>}
      {rows.length > 0 && shown.length === 0 && <div className="empty-state card"><p>{t('myPatients.noMatch')}</p></div>}

      <ul className="list patient-rows">
        {shown.map((r) => (
          <li key={r.patient_id}>
            <div className="card patient-row card-lift" role="button" tabIndex={0} onClick={() => open(r)}
              onKeyDown={(e) => { if (e.key === 'Enter') open(r); }}>
              <div className="patient-row-main">
                <div>
                  <strong>{r.name}</strong>
                  <span className="muted"> · {r.age ?? '?'} · {r.sex}</span>
                </div>
                <div className="muted small">
                  {r.conditions.length ? r.conditions.join(', ') : t('myPatients.noConditions')}
                  {r.scope !== 'all' && <span> · {t('myPatients.scopeLimited', { tags: r.scope.map((s) => t(`careTeam.tagName.${s}`, s)).join(', ') })}</span>}
                </div>
                <div className="chip-row">
                  {r.tags.map((tag) => (
                    <span key={tag} className={`chip ${TAG_CHIP[tag]}`}>
                      {t(`myPatients.tag.${tag}`)}
                      {tag === 'missed_doses' && r.adherence_14d != null && ` · ${t('myPatients.taken', { percent: r.adherence_14d })}`}
                      {tag === 'followup_overdue' && r.followup_on && ` · ${r.followup_on}`}
                    </span>
                  ))}
                </div>
              </div>
              <div className="patient-row-side">
                {r.refill_request_id && (
                  <button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`/refill/${r.refill_request_id}`); }}>
                    {t('myPatients.reviewRefill')}
                  </button>
                )}
                <span className="muted small">{t('myPatients.lastActivity')}: {ago(r.last_activity)}</span>
                <FollowUp row={r} onSaved={load} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
