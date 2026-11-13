import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Html5Qrcode } from 'html5-qrcode';
import { CheckCircle2, X, CameraOff } from 'lucide-react';
import { useApp } from '../context/AppContext.jsx';
import { scanQR, createQR, isDummy } from '../api.js';

// a phone's back camera if there is one; a laptop usually has just its front webcam
function pickCamera(cameras) {
  return cameras.find((c) => /back|rear|environment/i.test(c.label)) || cameras[0];
}

// why the camera did not start, as a key under scan.cam*
function cameraProblem(err) {
  const text = `${err?.name || ''} ${err?.message || err || ''}`;
  if (/NotAllowed|Permission/i.test(text)) return 'denied';
  if (/NotFound|DevicesNotFound|no camera/i.test(text)) return 'none';
  return 'error'; // e.g. NotReadableError: another app (Teams, Zoom) is using the camera
}

// Doctor scans the patient's QR once. One scan opens every patient tab.
export default function ScanModal() {
  const { t } = useTranslation();
  const { setSession, setScanOpen, pendingPath, setPendingPath } = useApp();
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [status, setStatus] = useState('idle'); // idle | checking | ok | expired | locked
  const [camera, setCamera] = useState(isDummy ? 'demo' : 'starting'); // starting | on | denied | none | error | insecure | demo
  const [patientId, setPatientId] = useState(null);
  const busyRef = useRef(false); // ignore more QR frames while one is being checked
  // QR texts the backend already refused. The camera sees the same QR ~8 times a second;
  // re-sending it would burn through the 5-wrong-codes limit in under a second (429 lockout).
  const refusedRef = useRef(new Set());
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

  // value = the QR's text (a link with ?share=<token>) or a typed 8-character code
  const check = async (value, fromCamera = false) => {
    if (!value || busyRef.current) return;
    if (fromCamera && refusedRef.current.has(value)) return; // same refused QR still in view
    busyRef.current = true;
    setStatus('checking');
    try {
      finish(await scanQR(value));
    } catch (e) {
      if (fromCamera) refusedRef.current.add(value);
      setStatus(/too many/i.test(e.message) ? 'locked' : 'expired');
      busyRef.current = false; // the camera keeps running: the doctor can show a new QR
    }
  };

  // Live camera. Written to survive React StrictMode (dev mounts this effect twice): the
  // library fails if stop() is called while start() is still running, which used to leave
  // an empty box. Camera errors are shown instead of being swallowed.
  useEffect(() => {
    if (isDummy) return undefined;
    if (!window.isSecureContext) { // browsers only allow the camera on https or localhost
      setCamera('insecure');
      return undefined;
    }
    let cancelled = false;
    let starting = null;
    const scanner = new Html5Qrcode(boxId, { verbose: false });

    (async () => {
      try {
        const cameras = await Html5Qrcode.getCameras(); // asks for permission the first time
        if (cancelled) return;
        if (!cameras.length) { setCamera('none'); return; }
        starting = scanner.start(pickCamera(cameras).id, { fps: 8, qrbox: { width: 200, height: 200 } },
          (text) => check(text, true), () => {});
        await starting;
        if (!cancelled) setCamera('on');
      } catch (err) {
        if (!cancelled) setCamera(cameraProblem(err));
      }
    })();

    return () => {
      cancelled = true;
      if (!starting) return; // never started: nothing to stop (and clear() would wipe the box)
      starting.then(() => scanner.stop()).then(() => scanner.clear()).catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const simulate = async () => {
    // Demo only: create a QR for p1 and scan it.
    const qr = await createQR('p1');
    check(qr.token);
  };

  const cameraNote = ['denied', 'none', 'error', 'insecure'].includes(camera);

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
            {!isDummy && (
              <div className={`scan-box ${cameraNote ? 'scan-box-off' : ''}`}>
                <div id={boxId} className="scan-video" />
                {camera === 'starting' && <p className="scan-overlay muted small">{t('scan.camStarting')}</p>}
                {cameraNote && (
                  <p className="scan-overlay small" role="status"><CameraOff size={20} />{t(`scan.cam_${camera}`)}</p>
                )}
              </div>
            )}
            {isDummy && <div className="scan-box placeholder">Camera (live mode)</div>}
            {camera === 'on' && <p className="muted small">{t('scan.camHint')}</p>}
            {status === 'expired' && <p className="error-text">{t('scan.expired')}</p>}
            {status === 'locked' && <p className="error-text">{t('scan.locked')}</p>}
            <label className="field-label" htmlFor="code">{t('scan.orCode')}</label>
            <form className="row" onSubmit={(e) => { e.preventDefault(); check(code.trim()); }}>
              <input id="code" className="input" value={code} placeholder="K7P3-QXM9" autoComplete="off"
                onChange={(e) => setCode(e.target.value)} />
              <button type="submit" className="btn btn-primary" disabled={status === 'checking' || !code.trim()}>{t('scan.check')}</button>
            </form>
            {isDummy && <button className="btn btn-ghost btn-block" onClick={simulate}>{t('scan.simulate')}</button>}
          </>
        )}
      </div>
    </div>
  );
}
