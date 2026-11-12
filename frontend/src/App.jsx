import { useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext.jsx';
import Layout from './components/Layout.jsx';
import LanguagePopup from './components/LanguagePopup.jsx';
import ScanModal from './components/ScanModal.jsx';
import Login from './pages/Login.jsx';
import Patients from './pages/Patients.jsx';
import Brief from './pages/Brief.jsx';
import Timeline from './pages/Timeline.jsx';
import Medication from './pages/Medication.jsx';
import Flags from './pages/Flags.jsx';
import Ask from './pages/Ask.jsx';
import Upload from './pages/Upload.jsx';
import Accuracy from './pages/Accuracy.jsx';
import Audit from './pages/Audit.jsx';
import Delete from './pages/Delete.jsx';
import MyRecords from './pages/MyRecords.jsx';
import Things from './pages/Things.jsx';
import GenerateQR from './pages/GenerateQR.jsx';
import Claim from './pages/Claim.jsx';
import ClaimDocuments from './pages/ClaimDocuments.jsx';
import PatientGate from './components/PatientGate.jsx';

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
  if (!roles.includes(user.role)) return <Navigate to={user.role === 'doctor' ? '/patients' : '/my-records'} replace />;
  return children;
}

function Shell() {
  const { scanOpen, user } = useApp();
  return (
    <>
      <Routes>
        <Route element={<RequireLogin><Layout /></RequireLogin>}>
          <Route path="/" element={<Navigate to={user?.role === 'doctor' ? '/patients' : '/my-records'} replace />} />
          <Route path="/patients" element={<RoleRoute roles={['doctor']}><Patients /></RoleRoute>} />
          <Route path="/accuracy" element={<RoleRoute roles={['doctor']}><Accuracy /></RoleRoute>} />
          <Route path="/brief" element={<RoleRoute roles={['doctor']}><PatientGate><Brief /></PatientGate></RoleRoute>} />
          <Route path="/my-records" element={<RoleRoute roles={['patient']}><MyRecords /></RoleRoute>} />
          <Route path="/things" element={<RoleRoute roles={['patient']}><Things /></RoleRoute>} />
          <Route path="/qr" element={<RoleRoute roles={['patient']}><GenerateQR /></RoleRoute>} />
          <Route path="/claim-documents" element={<RoleRoute roles={['patient']}><ClaimDocuments /></RoleRoute>} />
          <Route path="/timeline" element={<Timeline />} />
          <Route path="/medication" element={<Medication />} />
          <Route path="/flags" element={<Flags />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/audit" element={<Audit />} />
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
  const [langDone, setLangDone] = useState(() => !!localStorage.getItem('pramaan_lang'));
  const { user } = useApp();
  return (
    <>
      {!langDone && <LanguagePopup onDone={() => setLangDone(true)} />}
      {!user ? (
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      ) : (
        <Shell />
      )}
    </>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Root />
    </AppProvider>
  );
}
