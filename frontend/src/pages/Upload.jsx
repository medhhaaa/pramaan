import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { UploadCloud, CheckCircle2 } from 'lucide-react';
import { upload } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';

const CONSENT_KEY = 'pramaan_consent_v1';

function UploadInner() {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const [consented, setConsented] = useState(() => localStorage.getItem(CONSENT_KEY) === 'yes');
  const [ticks, setTicks] = useState([false, false, false]);
  const [files, setFiles] = useState([]);
  const [step, setStep] = useState(-1);
  const [result, setResult] = useState(null);
  const [dragging, setDragging] = useState(false);

  const steps = t('upload.steps', { returnObjects: true });

  const acceptConsent = () => {
    localStorage.setItem(CONSENT_KEY, 'yes');
    setConsented(true);
  };

  const run = async (list) => {
    const pdfs = list.filter((f) => f.type === 'application/pdf');
    if (pdfs.length === 0) return;
    setFiles(pdfs);
    setResult(null);
    for (let i = 0; i < steps.length; i += 1) {
      setStep(i);
      await new Promise((r) => setTimeout(r, 350));
    }
    const res = await upload(pid, pdfs[0]);
    setStep(-1);
    setResult(res);
  };

  if (!consented) {
    return (
      <section className="card consent">
        <h1>{t('upload.consentTitle')}</h1>
        {[t('upload.consent1'), t('upload.consent2'), t('upload.consent3')].map((label, i) => (
          <label key={i} className="check-row">
            <input type="checkbox" checked={ticks[i]} onChange={(e) => setTicks(ticks.map((v, j) => (j === i ? e.target.checked : v)))} />
            <span>{label}</span>
          </label>
        ))}
        <button className="btn btn-primary" disabled={!ticks.every(Boolean)} onClick={acceptConsent}>{t('upload.continue')}</button>
      </section>
    );
  }

  return (
    <section>
      <div className="page-head"><h1>{t('upload.title')}</h1></div>

      <label
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); run(Array.from(e.dataTransfer.files)); }}
      >
        <UploadCloud size={36} />
        <span>{t('upload.drop')}</span>
        <span className="btn btn-ghost btn-sm">{t('upload.choose')}</span>
        <input type="file" accept="application/pdf" multiple hidden onChange={(e) => run(Array.from(e.target.files))} />
      </label>

      {files.length > 0 && <p className="muted small">{files.map((f) => f.name).join(', ')}</p>}

      {step >= 0 && (
        <ol className="steps">
          {steps.map((s, i) => (
            <li key={s} className={i < step ? 'done' : i === step ? 'current' : ''}>{s}</li>
          ))}
        </ol>
      )}

      {result && (
        <div className="card result-card">
          <CheckCircle2 size={28} className="success-icon" />
          <p><strong>{t('upload.result', { added: result.facts_added, held: result.held_back })}</strong></p>
          {result.held_back > 0 && <p className="muted small">{t('upload.heldNote')}</p>}
        </div>
      )}
    </section>
  );
}

export default function Upload() {
  return <PatientGate><UploadInner /></PatientGate>;
}
