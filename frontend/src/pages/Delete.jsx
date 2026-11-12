import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { deletePatient, listPatients } from '../api.js';
import { useActivePatientId, useApp } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';

function DeleteInner() {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const { setSession } = useApp();
  const [ok, setOk] = useState(false);
  const [typed, setTyped] = useState('');
  const [done, setDone] = useState(false);
  const [name, setName] = useState(pid);

  useEffect(() => {
    listPatients().then((ps) => setName(ps.find((p) => p.id === pid)?.name || pid));
  }, [pid]);

  const confirm = async () => {
    await deletePatient(pid);
    setSession(null);
    setDone(true);
  };

  if (done) return <div className="card success-box"><p>{t('delete.done', { name })}</p></div>;

  return (
    <section className="card danger-zone">
      <div className="page-head"><h1>{t('delete.title')}</h1></div>
      <p><AlertTriangle size={18} className="warn-icon" /> {t('delete.explain')}</p>
      <label className="check-row">
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        <span>{t('delete.understand')}</span>
      </label>
      <label className="field-label" htmlFor="typed">{t('delete.typeDelete')}</label>
      <input id="typed" className="input" value={typed} onChange={(e) => setTyped(e.target.value)} />
      <button className="btn btn-danger" disabled={!ok || typed !== 'DELETE'} onClick={confirm}>{t('delete.button')}</button>
    </section>
  );
}

export default function Delete() {
  return <PatientGate><DeleteInner /></PatientGate>;
}
