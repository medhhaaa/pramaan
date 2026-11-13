import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import {
  correctConsultRecord, downloadConsultPdf, getConsultRecord, getConsultRecords, prescribe, verifyConsultRecord,
} from '../api.js';
import { useActivePatientId, useApp } from '../context/AppContext.jsx';
import '../styles/care-team.css';
import '../styles/refills.css';

// Consult records (doctor) for the open patient, plus Write prescription.
// A record is created automatically for every prescription and refill decision: the brief as
// shown, the decision, warnings shown and override reasons, sealed with a SHA-256 hash.
// Records are never edited; a correction is a new record pointing at the original.
// API: backend/routes/consult_records.py, backend/routes/refills.py.

const FREQUENCIES = ['OD', 'BD', 'TDS', 'QID', 'HS'];
const EMPTY_ITEM = { medicine: '', dose: '', frequency: 'OD', duration_days: 30 };

function summary(decision, t) {
  if (decision.correction_of) return t('consult.correctionOf', { id: decision.correction_of });
  if (decision.items) return decision.items.map((i) => [i.medicine, i.dose, i.frequency].filter(Boolean).join(' ')).join(', ');
  return `${t(`myMeds.status.${decision.status}`, decision.status || '')} · ${decision.medicine || ''}`;
}

function Prescribe({ pid, onSaved }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([{ ...EMPTY_ITEM }]);
  const [warnings, setWarnings] = useState(null);
  const [override, setOverride] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(null);

  const set = (i, key, value) => {
    setItems(items.map((it, n) => (n === i ? { ...it, [key]: value } : it)));
    setWarnings(null); // changed: the checks run again on submit
  };
  const ready = items.every((i) => i.medicine.trim().length >= 2 && Number(i.duration_days) >= 1)
    && (!warnings || override.trim());

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = items.map((i) => ({ medicine: i.medicine.trim(), dose: i.dose.trim() || null, frequency: i.frequency,
        duration_days: Number(i.duration_days) }));
      const res = await prescribe(pid, body, warnings ? override.trim() : null);
      setSaved(res);
      setItems([{ ...EMPTY_ITEM }]);
      setWarnings(null);
      setOverride('');
      onSaved(res.consult_record_id);
    } catch (err) {
      if (err.status === 422 && err.detail?.warnings) setWarnings(err.detail.warnings);
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>{t('consult.prescribeTitle')}</h3>
      <p className="muted small">{t('consult.prescribeIntro')}</p>
      {items.map((it, i) => (
        <div key={i} className="rx-row">
          <label className="rx-field rx-wide">
            <span className="field-label">{t('consult.medicine')}</span>
            <input className="input" value={it.medicine} onChange={(e) => set(i, 'medicine', e.target.value)} required minLength={2} maxLength={80} />
          </label>
          <label className="rx-field">
            <span className="field-label">{t('consult.dose')}</span>
            <input className="input" value={it.dose} placeholder="500mg" onChange={(e) => set(i, 'dose', e.target.value)} maxLength={40} />
          </label>
          <label className="rx-field">
            <span className="field-label">{t('consult.frequency')}</span>
            <select className="input" value={it.frequency} onChange={(e) => set(i, 'frequency', e.target.value)}>
              {FREQUENCIES.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <label className="rx-field">
            <span className="field-label">{t('consult.days')}</span>
            <input className="input" type="number" min={1} max={365} value={it.duration_days} onChange={(e) => set(i, 'duration_days', e.target.value)} />
          </label>
          {items.length > 1 && (
            <button type="button" className="icon-btn rx-remove" aria-label={t('consult.removeItem')}
              onClick={() => { setItems(items.filter((_, n) => n !== i)); setWarnings(null); }}><Trash2 size={16} /></button>
          )}
        </div>
      ))}
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setItems([...items, { ...EMPTY_ITEM }])}>
        <Plus size={14} /> {t('consult.addItem')}
      </button>

      {warnings && (
        <div className="mt">
          {warnings.map((w, i) => <div key={i} className="alert alert-danger" role="alert"><p>{w.text}</p></div>)}
          <label className="field-label" htmlFor="rx-override">{t('refill.overrideLabel')}</label>
          <textarea id="rx-override" className="input" rows={2} maxLength={1000} value={override} onChange={(e) => setOverride(e.target.value)} />
        </div>
      )}
      {error && <p className="error-text" role="alert">{error}</p>}
      {saved && <p className="muted small">{t('consult.saved', { id: saved.consult_record_id })}</p>}
      <div className="btn-row">
        <button className="btn btn-primary" disabled={!ready || busy}>
          {busy ? t('common.loading') : warnings ? t('consult.prescribeAnyway') : t('consult.prescribe')}
        </button>
      </div>
    </form>
  );
}

function RecordDetail({ id, onCorrected }) {
  const { t } = useTranslation();
  const [rec, setRec] = useState(null);
  const [verify, setVerify] = useState(null);
  const [note, setNote] = useState('');
  const [correcting, setCorrecting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setRec(null);
    setVerify(null);
    setCorrecting(false);
    getConsultRecord(id).then(setRec).catch((e) => setError(e.message));
  }, [id]);

  const pdf = async () => {
    try {
      const blob = await downloadConsultPdf(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `consult_record_${id}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e.message);
    }
  };
  const check = async () => {
    try { setVerify(await verifyConsultRecord(id)); } catch (e) { setError(e.message); }
  };
  const correct = async (e) => {
    e.preventDefault();
    try {
      const res = await correctConsultRecord(id, note.trim());
      setNote('');
      setCorrecting(false);
      onCorrected(res.id);
    } catch (err) {
      setError(err.message);
    }
  };

  if (error) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!rec) return <div className="skeleton" />;
  const brief = rec.snapshot.brief || {};

  return (
    <div className="card record-detail">
      <div className="team-row">
        <h3>{t('consult.recordNo', { id: rec.id })} · {t(`consult.type.${rec.type}`)}</h3>
        <span className="muted small">{rec.created_at} UTC</span>
      </div>
      <p className="small">{rec.doctor.name} · {t('careTeam.regNo')} {rec.doctor.registration_number || '—'}</p>
      {rec.corrects_record_id && <p className="chip chip-info">{t('consult.corrects', { id: rec.corrects_record_id })}</p>}

      <h4>{t('consult.decision')}</h4>
      <p className="small">{summary(rec.decision, t)}</p>
      {rec.decision.note && <p className="doctor-note small">“{rec.decision.note}”</p>}

      <h4>{t('consult.warningsShown')}</h4>
      {rec.warnings_shown.length === 0 && <p className="muted small">{t('consult.none')}</p>}
      <ul className="list small">{rec.warnings_shown.map((w, i) => <li key={i}>{w.text}</li>)}</ul>
      {rec.overrides.length > 0 && (
        <>
          <h4>{t('consult.overrides')}</h4>
          <ul className="list small">{rec.overrides.map((o, i) => <li key={i}>{t('consult.overrideReason')}: “{o.reason}”</li>)}</ul>
        </>
      )}

      <h4>{t('consult.snapshot')}</h4>
      <p className="small">
        {t('brief.currentMeds')}: {(brief.current_medicines || []).map((m) => m.name).join(', ') || '—'}<br />
        {t('brief.allergies')}: {(brief.allergies || []).map((a) => a.name).join(', ') || t('status.not_documented')}<br />
        {t('brief.conditions')}: {(brief.conditions || []).map((c) => c.name).join(', ') || '—'}
      </p>
      <p className="muted small">{t('consult.sources')}: {(rec.snapshot.source_document_ids || []).join(', ') || '—'}</p>

      <p className="muted small">SHA-256 <span className="mono hash">{rec.sha256}</span></p>
      <div className="btn-row">
        <button className="btn btn-ghost btn-sm" onClick={pdf}><Download size={14} /> {t('consult.pdf')}</button>
        <button className="btn btn-ghost btn-sm" onClick={check}><ShieldCheck size={14} /> {t('consult.verify')}</button>
        <button className="btn btn-ghost btn-sm" onClick={() => setCorrecting(!correcting)}>{t('consult.addCorrection')}</button>
      </div>
      {verify && (
        <p className={`chip ${verify.valid ? 'chip-verified' : 'chip-danger'} mt`} role="status">
          {verify.valid ? t('consult.valid') : t('consult.tampered')}
        </p>
      )}
      {correcting && (
        <form onSubmit={correct} className="mt">
          <label className="field-label" htmlFor="correction-note">{t('consult.correctionLabel')}</label>
          <textarea id="correction-note" className="input" rows={2} minLength={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="btn-row"><button className="btn btn-primary btn-sm" disabled={note.trim().length < 3}>{t('consult.saveCorrection')}</button></div>
        </form>
      )}
    </div>
  );
}

export default function ConsultRecords() {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const { session } = useApp();
  const [rows, setRows] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (!pid) return;
    getConsultRecords(pid).then((r) => { setRows(r); setError(''); }).catch((e) => setError(e.message));
  }, [pid]);
  useEffect(load, [load]);

  const opened = (id) => { load(); setOpenId(id); };

  return (
    <section className="consult-records">
      <div className="page-head"><h1>{t('consult.title')}</h1><span className="muted">{pid}</span></div>
      <p className="muted small">{t('consult.intro')}</p>
      {session?.careTeam ? <Prescribe pid={pid} onSaved={opened} /> : <p className="muted small card">{t('consult.careTeamOnly')}</p>}

      <div className="consult-grid mt">
        <div className="card">
          <h3>{t('consult.list')}</h3>
          {error && <p className="error-text">{error}</p>}
          {rows && rows.length === 0 && <p className="muted">{t('consult.empty')}</p>}
          {!rows && !error && <div className="skeleton" />}
          <ul className="list record-list">
            {(rows || []).map((r) => (
              <li key={r.id}>
                <button className={`record-row ${openId === r.id ? 'active' : ''}`} onClick={() => setOpenId(r.id)}>
                  <span><strong>#{r.id}</strong> {t(`consult.type.${r.type}`)}{r.corrects_record_id ? ` · ${t('consult.corrects', { id: r.corrects_record_id })}` : ''}</span>
                  <span className="muted small">{r.created_at.slice(0, 10)} · {summary(r.decision, t)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>{openId ? <RecordDetail id={openId} onCorrected={opened} /> : <p className="muted card">{t('consult.pick')}</p>}</div>
      </div>
    </section>
  );
}
