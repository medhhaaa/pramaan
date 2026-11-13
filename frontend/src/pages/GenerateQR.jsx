import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import { QrCode, ShieldCheck, UserRound, Clock, Eye, MessageSquareMore, TriangleAlert } from 'lucide-react';
import { createQR, listShares, stopShare, shareOptions, listShareRequests, answerShareRequest, updateShareScope, SHARE_MINUTES } from '../api.js';
import { useApp } from '../context/AppContext.jsx';
import { mmss } from '../lib/format.js';
import '../styles/share-scope.css';

const REFRESH_MS = 10000; // see a doctor's scan or request appear without reloading

// Share with a doctor (patient). Left: choose what the doctor may see, then make a QR + typed
// code. Right: who can see the records right now, with a Stop button. On top: a doctor's
// request to see more. A doctor sees a patient ONLY while a share is open (backend/auth.py),
// and only the parts picked here (backend/scope.py); allergies and blood group / sex / DOB
// are always shown for safety.
export default function GenerateQR() {
  const { t } = useTranslation();
  const { user } = useApp();
  const pid = user.patientId;
  const [qr, setQr] = useState(null); // the share just made: {token, url, code, share_id, expires_at (ms), scope}
  const [shares, setShares] = useState([]);
  const [requests, setRequests] = useState([]);
  const [groups, setGroups] = useState([]);
  const [mode, setMode] = useState('all'); // 'all' | 'some'
  const [picked, setPicked] = useState([]);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // share_id whose "what they see" is being changed
  const [notice, setNotice] = useState('');

  const load = useCallback(() => {
    if (!pid) return;
    listShares(pid).then(setShares).catch(() => {});
    listShareRequests(pid).then(setRequests).catch(() => {});
  }, [pid]);

  useEffect(() => {
    if (pid) shareOptions(pid).then((o) => setGroups(o.groups || [])).catch(() => {});
  }, [pid]);

  useEffect(() => {
    load();
    const refresh = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(refresh); clearInterval(tick); };
  }, [load]);

  const run = async (action) => {
    setBusy(true);
    setError('');
    try { await action(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const labelOf = (tag) => t(`shareScope.tags.${tag}`, { defaultValue: groups.find((g) => g.tag === tag)?.label || tag });
  const scopeText = (scope) => (!scope || scope === 'all' ? t('shareScope.seesAll') : t('shareScope.sees', { what: scope.map(labelOf).join(', ') }));
  // ticking every group is the same as "everything" (and the doctor isn't told anything is hidden)
  const chosenScope = mode === 'all' || (groups.length > 0 && picked.length === groups.length) ? 'all' : picked;
  const canMake = chosenScope === 'all' || picked.length > 0;

  const toggle = (tag) => setPicked((p) => (p.includes(tag) ? p.filter((x) => x !== tag) : [...p, tag]));
  const generate = () => run(async () => { setQr(await createQR(pid, chosenScope)); load(); });
  const stop = (shareId) => run(async () => {
    await stopShare(shareId);
    if (qr?.share_id === shareId) setQr(null);
    load();
  });
  const answer = (requestId, body) => run(async () => {
    const res = await answerShareRequest(requestId, body);
    if (qr && res.scope) setQr({ ...qr, scope: res.scope });
    load();
  });

  const saveScope = (shareId, scope) => run(async () => {
    const res = await updateShareScope(shareId, scope);
    if (qr?.share_id === shareId) setQr({ ...qr, scope: res.scope });
    setEditing(null);
    setNotice(t('shareScope.changed'));
    load();
  });

  const qrLive = qr && now < qr.expires_at; // stopping it clears qr (see stop)
  const active = shares.filter((s) => Date.parse(s.expires_at) > now);

  return (
    <section className="share-page">
      <div className="page-head"><h1>{t('qr.title')}</h1></div>
      <p className="muted share-intro">{t('qr.intro')}</p>
      {error && <p className="error-text">{error}</p>}
      {notice && <p className="chip chip-doc" role="status">{notice}</p>}

      {requests.map((r) => (
        <ShareRequest key={r.id} request={r} labelOf={labelOf} busy={busy} onAnswer={(body) => answer(r.id, body)} />
      ))}

      <div className="share-layout">
        <div className="card share-make">
          <h2 className="share-h"><QrCode size={20} /> {t('qr.makeTitle')}</h2>
          {qrLive ? (
            <>
              {/* the link inside works with the doctor's scanner and a phone camera */}
              <div className="qr-box"><QRCodeSVG value={qr.url || qr.token} size={208} bgColor="#FFFFFF" fgColor="#0F1424" /></div>
              {qr.code && (
                <div className="share-code">
                  <span className="muted small">{t('qr.codeLabel')}</span>
                  <strong className="mono">{qr.code}</strong>
                </div>
              )}
              <p className="timer" aria-live="polite">{t('qr.expires', { time: mmss(qr.expires_at - now) })}</p>
              <p className="scope-line"><Eye size={15} aria-hidden="true" /> {scopeText(qr.scope)}</p>
              <p className="muted small">{t('qr.share', { minutes: SHARE_MINUTES })}</p>
              {qr.share_id != null && (
                <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => stop(qr.share_id)}>{t('qr.stop')}</button>
              )}
            </>
          ) : (
            <>
              <p className="muted">{t('qr.how', { minutes: SHARE_MINUTES })}</p>
              <fieldset className="scope-pick">
                <legend className="scope-title">{t('shareScope.title')}</legend>
                <label className={`radio-row ${mode === 'all' ? 'selected' : ''}`}>
                  <input type="radio" name="scope-mode" checked={mode === 'all'} onChange={() => setMode('all')} />
                  <span className="scope-option"><strong>{t('shareScope.everything')}</strong><span className="muted small">{t('shareScope.everythingHint')}</span></span>
                </label>
                <label className={`radio-row ${mode === 'some' ? 'selected' : ''}`}>
                  <input type="radio" name="scope-mode" checked={mode === 'some'} onChange={() => setMode('some')} disabled={groups.length === 0} />
                  <span className="scope-option"><strong>{t('shareScope.some')}</strong><span className="muted small">{t('shareScope.someHint')}</span></span>
                </label>
                {mode === 'some' && (
                  <div className="scope-groups">
                    {groups.map((g) => (
                      <GroupCheck key={g.tag} group={g} label={labelOf(g.tag)} checked={picked.includes(g.tag)} onChange={() => toggle(g.tag)} />
                    ))}
                    <p className="muted small">{t('shareScope.always')}</p>
                    <p className="muted small">{t('shareScope.doctorKnows')}</p>
                  </div>
                )}
              </fieldset>
              <ul className="share-points small">
                <li>{t('qr.scope')}</li>
                <li>{t('qr.oneDoctor')}</li>
              </ul>
              {!canMake && <p className="muted small" role="status">{t('shareScope.pickOne')}</p>}
              <button className="btn btn-primary" disabled={busy || !pid || !canMake} onClick={generate}>
                {qr ? t('qr.new') : t('qr.button')}
              </button>
            </>
          )}
        </div>

        <div className="card share-who">
          <h2 className="share-h"><ShieldCheck size={20} /> {t('qr.whoTitle')}</h2>
          {active.length === 0 ? (
            <p className="muted">{t('qr.nobody')}</p>
          ) : (
            <ul className="list share-list">
              {active.map((s) => (
                <li key={s.share_id} className="list-row share-row">
                  <div>
                    <div className="share-who-name">
                      <UserRound size={16} />
                      {s.opened_by ? <strong>{s.opened_by}</strong> : <span className="muted">{t('qr.waiting')}</span>}
                    </div>
                    <div className="muted small">
                      <Clock size={13} /> {t('qr.timeLeft', { time: mmss(Date.parse(s.expires_at) - now) })}
                      {s.opened_at && <> · {t('qr.openedAt', { time: new Date(s.opened_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) })}</>}
                    </div>
                    <div className="muted small"><Eye size={13} /> {scopeText(s.sees ?? s.scope)}</div>
                    {editing === s.share_id ? (
                      <ScopeEditor scope={s.scope} groups={groups} labelOf={labelOf} busy={busy}
                        onSave={(scope) => saveScope(s.share_id, scope)} onCancel={() => setEditing(null)} />
                    ) : (
                      groups.length > 0 && (
                        <button className="link-btn small" disabled={busy} onClick={() => { setNotice(''); setEditing(s.share_id); }}>
                          {t('shareScope.edit')}
                        </button>
                      )
                    )}
                    {s.care_team_scope && JSON.stringify(s.sees) !== JSON.stringify(s.scope) && (
                      <p className="small share-careteam-note">
                        <TriangleAlert size={14} aria-hidden="true" />
                        <span>
                          {t('shareScope.careTeamWider', { doctor: s.opened_by })}{' '}
                          <Link to="/care-team">{t('shareScope.careTeamChange')}</Link>
                        </span>
                      </p>
                    )}
                  </div>
                  <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => stop(s.share_id)}>{t('qr.stop')}</button>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">{t('qr.auditNote')}</p>
        </div>
      </div>
    </section>
  );
}

// Change what an open share shows: everything, or only the ticked groups. Adding and taking
// back both work; the doctor's next screen load shows the change (PUT /share/{id}/scope).
function ScopeEditor({ scope, groups, labelOf, busy, onSave, onCancel }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(scope === 'all' ? 'all' : 'some');
  const [picked, setPicked] = useState(scope === 'all' ? groups.map((g) => g.tag) : scope || []);
  const toggle = (tag) => setPicked((p) => (p.includes(tag) ? p.filter((x) => x !== tag) : [...p, tag]));
  const chosen = mode === 'all' || picked.length === groups.length ? 'all' : picked;
  return (
    <fieldset className="scope-pick scope-edit">
      <legend className="scope-title">{t('shareScope.title')}</legend>
      <p className="muted small">{t('shareScope.editNote')}</p>
      <label className={`radio-row ${mode === 'all' ? 'selected' : ''}`}>
        <input type="radio" checked={mode === 'all'} onChange={() => setMode('all')} />
        <span className="scope-option"><strong>{t('shareScope.everything')}</strong></span>
      </label>
      <label className={`radio-row ${mode === 'some' ? 'selected' : ''}`}>
        <input type="radio" checked={mode === 'some'} onChange={() => setMode('some')} />
        <span className="scope-option"><strong>{t('shareScope.some')}</strong></span>
      </label>
      {mode === 'some' && (
        <div className="scope-groups">
          {groups.map((g) => (
            <GroupCheck key={g.tag} group={g} label={labelOf(g.tag)} checked={picked.includes(g.tag)} onChange={() => toggle(g.tag)} />
          ))}
          <p className="muted small">{t('shareScope.always')}</p>
        </div>
      )}
      <div className="share-request-actions">
        <button className="btn btn-primary btn-sm" disabled={busy || (chosen !== 'all' && chosen.length === 0)} onClick={() => onSave(chosen)}>
          {t('shareScope.saveScope')}
        </button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={onCancel}>{t('shareScope.cancel')}</button>
      </div>
    </fieldset>
  );
}

function GroupCheck({ group, label, checked, onChange }) {
  const { t } = useTranslation();
  return (
    <label className={`scope-group ${checked ? 'checked' : ''}`}>
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>
        <strong>{label}</strong>
        <span className="muted small scope-examples">{t('shareScope.items', { count: group.count, examples: group.examples.join(', ') })}</span>
      </span>
    </label>
  );
}

// A doctor asked to see more: the patient ticks what to add, shares everything, or says no.
function ShareRequest({ request, labelOf, busy, onAnswer }) {
  const { t } = useTranslation();
  const [add, setAdd] = useState([]);
  const toggle = (tag) => setAdd((a) => (a.includes(tag) ? a.filter((x) => x !== tag) : [...a, tag]));
  return (
    <div className="card share-request" role="region" aria-label={t('shareScope.requestsTitle')}>
      <h2 className="share-h"><MessageSquareMore size={20} /> {t('shareScope.asks', { doctor: request.doctor })}</h2>
      {request.note && <p className="share-request-note">{t('shareScope.note', { note: request.note })}</p>}
      <p className="muted small">{t('shareScope.nowSees', { what: (request.scope || []).map(labelOf).join(', ') })}</p>
      {request.options.length > 0 ? (
        <>
          <p className="scope-title">{t('shareScope.chooseMore')}</p>
          <div className="scope-groups">
            {request.options.map((g) => (
              <GroupCheck key={g.tag} group={g} label={labelOf(g.tag)} checked={add.includes(g.tag)} onChange={() => toggle(g.tag)} />
            ))}
          </div>
        </>
      ) : <p className="muted small">{t('shareScope.nothingMore')}</p>}
      <div className="share-request-actions">
        <button className="btn btn-primary btn-sm" disabled={busy || add.length === 0} onClick={() => onAnswer({ add })}>{t('shareScope.shareSelected')}</button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onAnswer({ add: 'all' })}>{t('shareScope.shareAll')}</button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onAnswer({ decline: true })}>{t('shareScope.decline')}</button>
      </div>
    </div>
  );
}
