import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { listPatients } from '../api.js';
import { useApp } from '../context/AppContext.jsx';

export default function Patients() {
  const { t } = useTranslation();
  const { setScanOpen, setPendingPath, session } = useApp();
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listPatients().then((p) => { setPatients(p); setLoading(false); });
  }, []);

  const shown = patients.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
  const sessionOk = (pid) => session && session.patientId === pid && session.expiresAt > Date.now();

  // BRIEF / TIMELINE / UPLOAD: without a scan, the scan modal opens first.
  const go = (pid, path) => {
    if (sessionOk(pid)) {
      navigate(path);
    } else {
      setPendingPath(path);
      setScanOpen(true);
    }
  };

  return (
    <section>
      <div className="page-head">
        <h1>{t('patients.title')}</h1>
        <span className="muted">{t('patients.count', { count: patients.length })}</span>
      </div>
      <div className="search">
        <Search size={18} />
        <input className="input" placeholder={t('patients.search')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('patients.search')} />
      </div>

      {loading && <div className="skeleton" />}
      {!loading && shown.length === 0 && <div className="empty-state card"><p>{t('patients.empty')}</p></div>}

      <div className="grid-cards">
        {shown.map((p) => (
          <article key={p.id} className="card patient-card card-lift">
            <h2>{p.name}</h2>
            <p className="muted">
              {p.sex} · {t('patients.born')} {p.dob} · {t('patients.bloodGroup')} {p.blood_group}
            </p>
            <div className="btn-row">
              <button className="btn btn-primary" onClick={() => go(p.id, '/brief')}>{t('patients.brief')}</button>
              <button className="btn btn-ghost" onClick={() => go(p.id, '/timeline')}>{t('patients.timeline')}</button>
              <button className="btn btn-ghost" onClick={() => go(p.id, '/upload')}>{t('patients.upload')}</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
