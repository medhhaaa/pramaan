import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { QRCodeSVG } from 'qrcode.react';
import { createQR } from '../api.js';
import { useApp } from '../context/AppContext.jsx';
import { mmss } from '../lib/format.js';

export default function GenerateQR() {
  const { t } = useTranslation();
  const { user } = useApp();
  const [qr, setQr] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!qr) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [qr]);

  const generate = async () => setQr(await createQR(user.patientId));

  const expired = qr && now >= qr.expires_at;
  const left = qr ? qr.expires_at - now : 0;

  return (
    <section className="qr-page">
      <div className="page-head"><h1>{t('qr.title')}</h1></div>
      <div className="card qr-card">
        {qr && !expired && (
          <>
            <div className="qr-box"><QRCodeSVG value={qr.token} size={220} bgColor="#FFFFFF" fgColor="#0F1424" /></div>
            <p className="timer" aria-live="polite">{t('qr.expires', { time: mmss(left) })}</p>
            <p className="muted small center">{t('qr.share')}</p>
            <p className="muted small center">{t('qr.scope')}</p>
          </>
        )}
        {qr && expired && <p className="error-text">{t('qr.expired')}</p>}
        {(!qr || expired) && (
          <button className="btn btn-primary btn-lg" onClick={generate}>{expired ? t('qr.new') : t('qr.button')}</button>
        )}
      </div>
    </section>
  );
}
