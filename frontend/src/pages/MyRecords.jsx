import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { listPatients, getTimeline, getQuestions } from '../api.js';
import { useApp } from '../context/AppContext.jsx';
import { BadgeChip } from '../components/Chip.jsx';
import { fmtDate } from '../lib/format.js';

export default function MyRecords() {
  const { t, i18n } = useTranslation();
  const { user } = useApp();
  const [patient, setPatient] = useState(null);
  const [latest, setLatest] = useState([]);
  const [openQ, setOpenQ] = useState(0);

  useEffect(() => {
    listPatients().then((ps) => setPatient(ps.find((p) => p.id === user.patientId)));
    getTimeline(user.patientId).then((f) => setLatest(f.filter((x) => !x.echo_of).slice(-5).reverse()));
    getQuestions(user.patientId).then((q) => setOpenQ(q.filter((x) => x.status === 'open').length));
  }, [user.patientId]);

  if (!patient) return <div className="skeleton" />;

  return (
    <section>
      <div className="page-head"><h1>{t('myRecords.title')}</h1></div>

      <article className="card patient-card card-lift">
        <h2>{patient.name}</h2>
        <p className="muted">{patient.sex} · {t('patients.born')} {patient.dob} · {t('patients.bloodGroup')} {patient.blood_group}</p>
        <div className="btn-row">
          <Link className="btn btn-primary" to="/things">
            {t('myRecords.thingsButton')} {openQ > 0 && <span className="count-badge">{openQ}</span>}
          </Link>
        </div>
      </article>

      <div className="card mt">
        <h3>{t('myRecords.latest')}</h3>
        <ul className="list">
          {latest.map((f) => (
            <li key={f.fact_id} className="list-row">
              <span>{f.name}{f.dose ? ` ${f.dose}` : ''}{f.value ? ` ${f.value} ${f.unit || ''}` : ''}</span>
              <BadgeChip badge={f.badge} />
              <span className="muted small">{fmtDate(f.event_date, i18n.language)}</span>
            </li>
          ))}
        </ul>
        <Link to="/timeline" className="link-btn">{t('myRecords.viewTimeline')}</Link>
      </div>
    </section>
  );
}
