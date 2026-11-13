import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Stethoscope, Tablets } from 'lucide-react';
import MyMedicines from './MyMedicines.jsx';
import MyCareTeam from './MyCareTeam.jsx';
import '../styles/care-team.css';

// Patient: "Doctors & medicines", one sidebar entry for My medicines (prescribed here: doses,
// refills) and My care team (the doctors who can see the records). Both addresses still work:
// /my-medicines (refill notifications link there) and /care-team (the share page links there).
export default function CareTeamHub({ tab }) {
  const { t } = useTranslation();
  return (
    <section>
      <div className="page-head"><h1>{t('nav.careAndMedicines')}</h1></div>
      <nav className="sub-tabs" aria-label={t('nav.careSections')}>
        <NavLink to="/my-medicines" replace className={({ isActive }) => `sub-tab ${isActive ? 'active' : ''}`}>
          <Tablets size={16} aria-hidden="true" /> {t('nav.myMedicines')}
        </NavLink>
        <NavLink to="/care-team" replace className={({ isActive }) => `sub-tab ${isActive ? 'active' : ''}`}>
          <Stethoscope size={16} aria-hidden="true" /> {t('nav.myDoctors')}
        </NavLink>
      </nav>
      {tab === 'doctors' ? <MyCareTeam embedded /> : <MyMedicines embedded />}
    </section>
  );
}
