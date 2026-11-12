import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Html5Qrcode } from 'html5-qrcode';
import { CheckCircle2, X } from 'lucide-react';
import { useApp } from '../context/AppContext.jsx';
import { scanQR, createQR, isDummy } from '../api.js';

// Doctor scans the patient's QR once. One scan opens every patient tab.
export default function ScanModal() {
  const { t } = useTranslation();
  const { setSession, setScanOpen, pendingPath, setPendingPath } = useApp();
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [status, setStatus] = useState('idle'); // idle | ok | expired
  const [patientId, setPatientId] = useState(null);
  const scannerRef = useRef(null);
  const boxId = 'qr-reader';

  const finish = (res) => {
    setSession({ patientId: res.patient_id, expiresAt: res.expires_at });
    setPatientId(res.patient_id);
    setStatus('ok');
    setTimeout(() => {
      setScanOpen(false);
      if (pendingPath) navigate(pendingPath);
      setPendingPath(null);
    }, 900);
  };

  const close = () => {
    setScanOpen(false);
    setPendingPath(null);
  };

  const check = async (value) => {
    try {
      const res = await scanQR(value);
      finish(res);
    } catch {
      setStatus('expired');
    }
  };

  // Live camera (not used in dummy mode).
  useEffect(() => {
    if (isDummy) return undefined;
    const scanner = new Html5Qrcode(boxId);
    scannerRef.current = scanner;
    scanner.start({ facingMode: 'environment' }, { fps: 8, qrbox: 220 }, (text) => {
      scanner.stop().catch(() => {});
      check(text);
    }, () => {}).catch(() => {});
    return () => { scanner.stop().catch(() => {}); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const simulate = async () => {
    // Demo only: create a QR for p1 and scan it.
    const qr = await createQR('p1');
    check(qr.token);
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="scan-title">
      <div className="modal card-lift">
        <div className="modal-head">
          <h2 id="scan-title">{t('scan.title')}</h2>
          <button className="icon-btn" aria-label={t('common.close')} onClick={close}><X size={20} /></button>
        </div>

        {status === 'ok' ? (
          <div className="success-box">
            <CheckCircle2 size={48} className="success-icon" />
            <p>{t('scan.granted')}</p>
            <p className="muted small">{patientId}</p>
          </div>
        ) : (
          <>
            {!isDummy && <div id={boxId} className="scan-box" />}
            {isDummy && <div className="scan-box placeholder">Camera (live mode)</div>}
            {status === 'expired' && <p className="error-text">{t('scan.expired')}</p>}
            <label className="field-label" htmlFor="code">{t('scan.orCode')}</label>
            <div className="row">
              <input id="code" className="input" value={code} onChange={(e) => setCode(e.target.value)} />
              <button className="btn btn-primary" onClick={() => check(code.trim())}>{t('scan.check')}</button>
            </div>
            {isDummy && <button className="btn btn-ghost btn-block" onClick={simulate}>{t('scan.simulate')}</button>}
          </>
        )}
      </div>
    </div>
  );
}
