import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext.jsx';
import Layout from './components/Layout.jsx';
import LanguagePopup from './components/LanguagePopup.jsx';
import ProfilePopup from './components/ProfilePopup.jsx';
import HealthProfile from './pages/HealthProfile.jsx';
import ScanModal from './components/ScanModal.jsx';
import Landing from './pages/Landing.jsx';
import Login from './pages/Login.jsx';
import Patients from './pages/Patients.jsx';
import Brief from './pages/Brief.jsx';
import Timeline from './pages/Timeline.jsx';
import Medication from './pages/Medication.jsx';
import Records from './pages/Records.jsx';
import DiseaseSearch from './pages/DiseaseSearch.jsx';
import Flags from './pages/Flags.jsx';
import Ask from './pages/Ask.jsx';
import { ASK_ON, ASSISTANT_ON } from './lib/features.js';
import Assistant from './pages/Assistant.jsx';
import Upload from './pages/Upload.jsx';
import Accuracy from './pages/Accuracy.jsx';
import Audit from './pages/Audit.jsx';
import Delete from './pages/Delete.jsx';
import MyRecords from './pages/MyRecords.jsx';
import Things from './pages/Things.jsx';
import GenerateQR from './pages/GenerateQR.jsx';
import Claim from './pages/Claim.jsx';
import ClaimDocuments from './pages/ClaimDocuments.jsx';
import MyPatients from './pages/MyPatients.jsx';
import CareTeamHub from './pages/CareTeamHub.jsx';
import RefillReview from './pages/RefillReview.jsx';
import ConsultRecords from './pages/ConsultRecords.jsx';
import PatientGate from './components/PatientGate.jsx';
import Security from './pages/Security.jsx';
import AiView from './pages/AiView.jsx';

const CLAIM_ON = import.meta.env.VITE_ENABLE_CLAIM_READY === 'true';

function RequireLogin({ children }) {
  const { user } = useApp();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

// Doctor-only and patient-only routes. Other roles go to their home.
function RoleRoute({ roles, children }) {
  const { user } = useApp();
  if (!roles.includes(user.role)) return <Navigate to={user.role === 'doctor' ? '/my-patients' : '/my-records'} replace />;
  return children;
}

function Shell() {
  const { scanOpen, user, setUser } = useApp();
  return (
    <>
      {!user.language && <LanguagePopup username={user.username} onDone={(language) => setUser({ ...user, language })} />}
      {user.language && user.role === 'patient' && <ProfilePopup pid={user.patientId} />}
      <Routes>
        <Route element={<RequireLogin><Layout /></RequireLogin>}>
          <Route path="/" element={<Navigate to={user?.role === 'doctor' ? '/my-patients' : '/my-records'} replace />} />
          <Route path="/my-patients" element={<RoleRoute roles={['doctor']}><MyPatients /></RoleRoute>} />
          <Route path="/care-team" element={<RoleRoute roles={['patient']}><CareTeamHub tab="doctors" /></RoleRoute>} />
          <Route path="/my-medicines" element={<RoleRoute roles={['patient']}><CareTeamHub tab="medicines" /></RoleRoute>} />
          <Route path="/refill/:id" element={<RoleRoute roles={['doctor']}><RefillReview /></RoleRoute>} />
          <Route path="/consult-records" element={<RoleRoute roles={['doctor']}><PatientGate><ConsultRecords /></PatientGate></RoleRoute>} />
          <Route path="/patients" element={<RoleRoute roles={['doctor']}><Patients /></RoleRoute>} />
          <Route path="/accuracy" element={<RoleRoute roles={['doctor']}><Accuracy /></RoleRoute>} />
          <Route path="/brief" element={<RoleRoute roles={['doctor']}><PatientGate><Brief /></PatientGate></RoleRoute>} />
          <Route path="/my-records" element={<RoleRoute roles={['patient']}><MyRecords /></RoleRoute>} />
          <Route path="/health-profile" element={<RoleRoute roles={['patient']}><HealthProfile /></RoleRoute>} />
          <Route path="/things" element={<RoleRoute roles={['patient']}><Things /></RoleRoute>} />
          <Route path="/qr" element={<RoleRoute roles={['patient']}><GenerateQR /></RoleRoute>} />
          <Route path="/claim-documents" element={<RoleRoute roles={['patient']}><ClaimDocuments /></RoleRoute>} />
          <Route path="/timeline" element={<Timeline />} />
          <Route path="/medication" element={<Medication />} />
          <Route path="/records" element={<RoleRoute roles={['doctor']}><Records /></RoleRoute>} />
          <Route path="/disease-search" element={<RoleRoute roles={['doctor']}><DiseaseSearch /></RoleRoute>} />
          <Route path="/flags" element={<Flags />} />
          {ASK_ON && <Route path="/ask" element={<Ask />} />}
          {ASSISTANT_ON && <Route path="/assistant" element={<Assistant />} />}
          <Route path="/upload" element={<Upload />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/security" element={<Security />} />
          <Route path="/ai-view/:docId" element={<AiView />} />
          <Route path="/delete" element={<Delete />} />
          {CLAIM_ON && <Route path="/claim" element={<Claim />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      {scanOpen && <ScanModal />}
    </>
  );
}

function Root() {
  const { user } = useApp();
  if (user) return <Shell />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Root />
    </AppProvider>
  );
}
