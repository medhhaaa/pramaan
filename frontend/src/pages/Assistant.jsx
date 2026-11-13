import { useTranslation } from 'react-i18next';
import { useApp, useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';
import AssistantChat from '../components/AssistantChat.jsx';

// /assistant: the patient's assistant on their own records, or the doctor's assistant on the
// patient whose share is open (PatientGate asks a doctor to scan first). Behind ASSISTANT_ON.
function AssistantInner() {
  const { t } = useTranslation();
  const { user } = useApp();
  const pid = useActivePatientId();
  const persona = user.role === 'doctor' ? 'doctor' : 'patient';
  return (
    <section className="assistant-page">
      <div className="page-head"><h1>{t(`assistant.${persona}.title`)}</h1></div>
      {/* a new patient gets a fresh conversation */}
      <AssistantChat key={pid} pid={pid} persona={persona} />
    </section>
  );
}

export default function Assistant() {
  return <PatientGate><AssistantInner /></PatientGate>;
}
