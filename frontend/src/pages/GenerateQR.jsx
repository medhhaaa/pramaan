import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { QRCodeSVG } from 'qrcode.react';
import { QrCode, ShieldCheck, UserRound, Clock } from 'lucide-react';
import { createQR, listShares, stopShare, SHARE_MINUTES } from '../api.js';
import { useApp } from '../context/AppContext.jsx';
import { mmss } from '../lib/format.js';

const REFRESH_MS = 10000; // see a doctor's scan appear without reloading

// Share with a doctor (patient). Left: make a QR + typed code. Right: who can see the
// records right now, with a Stop button. A doctor sees a patient ONLY while a share is
// open (backend/auth.py), so this page is where the patient stays in control.
export default function GenerateQR() {
  const { t } = useTranslation();
  const { user } = useApp();
  const pid = user.patientId;
  const [qr, setQr] = useState(null); // the share just made: {token, url, code, share_id, expires_at (ms)}
  const [shares, setShares] = useState([]);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (pid) listShares(pid).then(setShares).catch(() => {});
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
  const generate = () => run(async () => { setQr(await createQR(pid)); load(); });
  const stop = (shareId) => run(async () => {
    await stopShare(shareId);
    if (qr?.share_id === shareId) setQr(null);
    load();
  });

  const qrLive = qr && now < qr.expires_at; // stopping it clears qr (see stop)
  const active = shares.filter((s) => Date.parse(s.expires_at) > now);

  return (
    <section className="share-page">
      <div className="page-head"><h1>{t('qr.title')}</h1></div>
      <p className="muted share-intro">{t('qr.intro')}</p>
      {error && <p className="error-text">{error}</p>}

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
              <p className="muted small">{t('qr.share', { minutes: SHARE_MINUTES })}</p>
              {qr.share_id != null && (
                <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => stop(qr.share_id)}>{t('qr.stop')}</button>
              )}
            </>
          ) : (
            <>
              <p className="muted">{t('qr.how', { minutes: SHARE_MINUTES })}</p>
              <ul className="share-points small">
                <li>{t('qr.scope')}</li>
                <li>{t('qr.oneDoctor')}</li>
              </ul>
              <button className="btn btn-primary" disabled={busy || !pid} onClick={generate}>
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
