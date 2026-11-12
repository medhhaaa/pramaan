import { useTranslation } from 'react-i18next';
import { Scan } from 'lucide-react';
import { useApp, useActivePatientId } from '../context/AppContext.jsx';

// Wraps patient-level screens. Doctors need an active scan session first.
export default function PatientGate({ children }) {
  const { t } = useTranslation();
  const { user, setScanOpen } = useApp();
  const pid = useActivePatientId();
  if (user.role === 'patient' || pid) return children;
  return (
    <div className="empty-state card">
      <Scan size={36} />
      <p>{t('scan.needScan')}</p>
      <button className="btn btn-primary" onClick={() => setScanOpen(true)}>{t('nav.scan')}</button>
    </div>
  );
}
