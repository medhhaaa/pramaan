import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getFlags } from '../api.js';
import { useActivePatientId, useApp } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';

const ORDER = ['contradiction', 'duplicate', 'unit_mismatch', 'ambiguous_date', 'wrong_patient', 'implausible_value', 'gap'];

function FlagsInner() {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const { user } = useApp();
  const [data, setData] = useState(null);

  useEffect(() => { getFlags(pid).then(setData); }, [pid]);
  if (!data) return <div className="skeleton" />;

  const isDoctor = user.role === 'doctor';

  return (
    <section>
      <div className="page-head"><h1>{t('flagsPage.title')}</h1></div>
      {ORDER.map((type) => {
        const list = data[type] || [];
        if (list.length === 0) return null;
        // Wrong-patient items are shown to the doctor only.
        if (type === 'wrong_patient' && !isDoctor) return null;
        return (
          <div key={type} className="card flag-group">
            <h2>{t(`flagNames.${type}`)}</h2>
            <p className="muted small">{t(`flagTips.${type}`)}</p>

            {type === 'contradiction' ? (
              <table className="table">
                <thead>
                  <tr><th scope="col">{t('flagsPage.allergen')}</th><th scope="col">{t('flagsPage.details')}</th></tr>
                </thead>
                <tbody>
                  {list.map((f) => (
                    <tr key={f.fact_id}>
                      <td>{f.name}</td>
                      <td>{f.quote} <span className="muted small">{f.date_raw}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <ul className="list">
                {list.map((f) => (
                  <li key={f.fact_id} className="list-row">
                    <span>{f.name || f.fact_id}</span>
                    <span className="muted small">{f.date_raw || ''}</span>
                    {type === 'wrong_patient' && <span className="chip chip-warn">{t('flagsPage.held')}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </section>
  );
}

export default function Flags() {
  return <PatientGate><FlagsInner /></PatientGate>;
}
