import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import {
  answerQuestion, createHospitalStay, downloadClaimPack, getClaimChecklist, getHospitalStays,
  listPatients, updateHospitalStay,
} from '../api.js';
import { useActivePatientId, useApp } from '../context/AppContext.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import '../styles/claim-docs.css';

// Claim Documents (patient): documents COMMONLY needed for a reimbursement claim after a
// hospital stay, which are already saved in Pramaan, and a reminder to collect the rest.
// No insurer integration and no claim decision: the insurer makes the final decision.
// Wording rule: "commonly needed", "saved", "not saved yet". Never "complete", "eligible",
// "approved", "guaranteed" or a claim deadline (the patient may type their own reminder date).
// Checklist logic: pipeline/claim_checklist.py. API: backend/routes/claims.py.

const REFRESH_MS = 15000; // documents uploaded meanwhile show up without a reload
const ANSWERS = ['yes', 'no', 'dont_know'];
const CHIP = { saved: 'chip-verified', not_saved: 'chip-neutral', unsure: 'chip-warn', not_needed: 'chip-outline' };

// the patient's own id: from login in dummy mode, else their one record in the patient list
function usePatientId() {
  const fromLogin = useActivePatientId();
  const [pid, setPid] = useState(fromLogin);
  useEffect(() => {
    if (fromLogin) setPid(fromLogin);
    else listPatients().then((ps) => setPid(ps[0]?.id || null));
  }, [fromLogin]);
  return pid;
}

function StayDates({ pid, stay, onSaved }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    admitted_on: stay.admitted_on || '', discharged_on: stay.discharged_on || '', my_reminder_date: stay.my_reminder_date || '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await updateHospitalStay(pid, stay.id, form);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="card mt">
      <summary><strong>{t('claimDocs.datesTitle')}</strong></summary>
      <form onSubmit={save} className="stack mt">
        {[['admitted_on', 'admitted'], ['discharged_on', 'discharged'], ['my_reminder_date', 'myReminder']].map(([key, label]) => (
          <label key={key} className="field-label">
            {t(`claimDocs.${label}`)}
            <input type="date" className="input" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
          </label>
        ))}
        <p className="muted small">{t('claimDocs.myReminderHint')}</p>
        <button type="submit" className="btn btn-primary" disabled={busy}>{t('claimDocs.save')}</button>
        {error && <p className="error-text">{error}</p>}
      </form>
    </details>
  );
}

export default function ClaimDocuments() {
  const { t } = useTranslation();
  const { user } = useApp();
  const location = useLocation();
  const pid = usePatientId();
  const [stays, setStays] = useState(null);
  const [stayId, setStayId] = useState(location.state?.stayId || null);
  const [list, setList] = useState(null);
  const [doc, setDoc] = useState(null); // {id, line} open in the source drawer
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadStays = useCallback(() => {
    if (pid) getHospitalStays(pid).then(setStays).catch((e) => setError(e.message));
  }, [pid]);
  useEffect(loadStays, [loadStays]);

  const stay = stays && (stays.find((s) => s.id === stayId) || stays[0]);
  const activeId = stay?.id;

  const loadList = useCallback(() => {
    if (pid && activeId) getClaimChecklist(pid, activeId).then(setList).catch((e) => setError(e.message));
  }, [pid, activeId]);
  useEffect(() => {
    loadList();
    const timer = setInterval(loadList, REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadList]);

  const refresh = () => { loadStays(); loadList(); };
  const closeDoc = useCallback(() => setDoc(null), []); // DocDrawer refetches when onClose changes

  const run = async (action) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(e.message === 'needs_backend' ? t('claimDocs.needsBackend') : e.message);
    } finally {
      setBusy(false);
    }
  };

  const newStay = () => run(async () => {
    const created = await createHospitalStay(pid);
    setStayId(created.id);
    loadStays();
  });

  const answer = (qid, value) => run(async () => { await answerQuestion(qid, value); refresh(); });

  const download = () => run(async () => {
    const blob = await downloadClaimPack(pid, activeId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `claim_pack_stay_${activeId}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  });

  const docLabel = (d) => t(`claimDocs.doc.${d}`);
  const stayLabel = (s) => (!s.admitted_on && !s.discharged_on
    ? t('claimDocs.noDates')
    : t('claimDocs.stayDates', { from: s.admitted_on || t('claimDocs.dateUnknown'), to: s.discharged_on || t('claimDocs.dateUnknown') }));
  const isPatient = user.role === 'patient';

  if (error && !stays) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!stays) return <div className="skeleton" />;

  const banner = <div className="card claim-banner" role="note">{t('claimDocs.banner')} {t('claimDocs.finalDecision')}</div>;
  const newStayButton = isPatient && (
    <button className="btn btn-ghost" onClick={newStay} disabled={busy}>{t('claimDocs.newStay')}</button>
  );

  if (stays.length === 0) {
    return (
      <section>
        <div className="page-head"><h1>{t('claimDocs.title')}</h1></div>
        {banner}
        <div className="card mt"><p>{t('claimDocs.noStays')}</p>{newStayButton}</div>
        {error && <p className="error-text">{error}</p>}
      </section>
    );
  }

  const ready = list && list.stay.id === activeId;

  return (
    <section className="claim-docs">
      <div className="page-head">
        <h1>{t('claimDocs.title')}</h1>
        <span className="muted">{stayLabel(stay)}</span>
      </div>
      {banner}
      {error && <p className="error-text">{error}</p>}
      {!ready && <div className="skeleton" />}

      {ready && (
        <>
          <h2 className="mt">{t('claimDocs.count', { saved: list.summary.saved_count, required: list.summary.required_count })}</h2>

          {list.reminder.show && (
            <div className="card claim-reminder" role="status">
              {t('claimDocs.reminder', { list: list.reminder.docs.map(docLabel).join(', ') })}
            </div>
          )}
          {list.stay.my_reminder_date && <p className="muted small">{t('claimDocs.reminderSet', { date: list.stay.my_reminder_date })}</p>}

          <ul className="list claim-list mt">
            {list.items.map((item) => {
              const q = list.condition_questions[item.when];
              const current = list.stay[item.when] === true ? 'yes' : list.stay[item.when] === false ? 'no' : null;
              return (
                <li key={item.doc} className={`card claim-item claim-${item.status}`}>
                  <div className="row">
                    <strong>{docLabel(item.doc)}</strong>
                    <span className={`chip ${CHIP[item.status]}`}>{t(`claimDocs.status.${item.status}`)}</span>
                  </div>
                  {item.status === 'saved' && item.documents.map((d) => (
                    <button key={d.id} className="link-btn" onClick={() => setDoc({ id: d.id, line: d.doc_type_line })}>
                      {d.filename}{d.document_date ? ` (${d.document_date})` : ''}
                    </button>
                  ))}
                  {item.status === 'not_saved' && <p className="muted small">{t('claimDocs.tipNotSaved')}</p>}
                  {item.when !== 'always' && isPatient && q && (
                    <div className="mt">
                      <p className="small">{t(`claimDocs.question.${item.when}`)}</p>
                      <div className="chip-row">
                        {ANSWERS.map((a) => (
                          <button key={a} className={`answer ${current === a ? 'selected' : ''}`} disabled={busy || current === a}
                            onClick={() => answer(q.id, a)}>
                            {t(`claimDocs.answer.${a}`)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          <div className="card mt">
            <h3>{t('claimDocs.alsoKeep')}</h3>
            <p className="muted small">{t('claimDocs.alsoKeepHint')}</p>
            <ul>{list.also_keep_ready.map((k) => <li key={k.key}>{t(`claimDocs.keep.${k.key}`, k.label)}</li>)}</ul>
          </div>

          <div className="btn-row mt">
            <button className="btn btn-primary" onClick={download} disabled={busy || list.summary.saved_count === 0}>
              {busy ? t('claimDocs.downloading') : t('claimDocs.download')}
            </button>
            {newStayButton}
          </div>

          {isPatient && <StayDates key={stay.id} pid={pid} stay={list.stay} onSaved={refresh} />}
        </>
      )}

      {stays.length > 1 && (
        <p className="muted small mt">
          {t('claimDocs.otherStays')}{' '}
          {stays.filter((s) => s.id !== activeId).map((s) => (
            <button key={s.id} className="link-btn" onClick={() => setStayId(s.id)}>{stayLabel(s)}</button>
          ))}
        </p>
      )}

      {doc && <DocDrawer docId={doc.id} highlightLine={doc.line} onClose={closeDoc} />}
    </section>
  );
}
