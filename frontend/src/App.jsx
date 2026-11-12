// Simple page state instead of a router: login -> patients -> one patient's pages.
import { useCallback, useState } from "react";
import { hasSession, logout, setDummyUser } from "./api";
import Countdown from "./components/Countdown";
import Disclaimer from "./components/Disclaimer";
import Header from "./components/Header";
import AskPage from "./pages/AskPage";
import AuditPage from "./pages/AuditPage";
import BriefPage from "./pages/BriefPage";
import ConsentPage from "./pages/ConsentPage";
import DeletePage from "./pages/DeletePage";
import FlagsPage from "./pages/FlagsPage";
import LoginPage from "./pages/LoginPage";
import MedicationsPage from "./pages/MedicationsPage";
import MetricsPage from "./pages/MetricsPage";
import OpenSharePage from "./pages/OpenSharePage";
import PatientsPage from "./pages/PatientsPage";
import SharePage from "./pages/SharePage";
import ThingsToCheckPage from "./pages/ThingsToCheckPage";
import TimelinePage from "./pages/TimelinePage";
import UploadPage from "./pages/UploadPage";

function load(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}

function save(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage blocked: state just won't survive a refresh
  }
}

// tabs shown for an open patient; the first tab differs by role
const tabsFor = (role) => [
  role === "doctor" ? ["brief", "Brief"] : ["questions", "Things to check"],
  ["timeline", "Timeline"],
  ["medications", "Medications"],
  ["flags", "Flags"],
  ["ask", "Ask my records"],
  ["upload", "Upload"],
  ["audit", "Audit log"],
  ["delete", "Delete data"],
  ...(role === "patient" ? [["share", "Share by QR"]] : []),
];

// a doctor viewing records shared by QR / code can only read: hide the tabs that change data
const SHARED_HIDDEN_TABS = ["upload", "delete"];

// a scanned QR opens the app as http://localhost:5173/?share=<token>: read the token once,
// then remove it from the address bar
function takeShareToken() {
  const token = new URLSearchParams(window.location.search).get("share");
  if (token) window.history.replaceState(null, "", window.location.pathname);
  return token;
}

export default function App() {
  const [user, setUser] = useState(() => {
    const saved = hasSession() ? load("user") : null;
    setDummyUser(saved);
    return saved;
  });
  const [shareToken, setShareToken] = useState(takeShareToken);
  const [page, setPage] = useState(() => (shareToken ? "open-share" : "patients"));
  const [patient, setPatient] = useState(null);
  const [notice, setNotice] = useState("");

  function handleLogin(u) {
    save("user", u);
    setDummyUser(u);
    setUser(u);
    setPage(shareToken && u.role === "doctor" ? "open-share" : "patients");
  }

  function handleLogout() {
    logout();
    save("user", null);
    setUser(null);
    setPatient(null);
  }

  function openPatient(p, target) {
    setPatient(p);
    // consent is asked once per user, before their first upload
    if (target === "upload" && !load(`consent_${user.username}`)) setPage("consent");
    else setPage(target);
  }

  function acceptConsent() {
    save(`consent_${user.username}`, { accepted_at: new Date().toISOString() });
    setPage("upload");
  }

  function goToPatients() {
    setPatient(null);
    setPage("patients");
  }

  // a doctor opened a patient's QR / code: show that patient, read-only
  const openShared = useCallback((p) => {
    setShareToken(null);
    setNotice("");
    setPatient(p);
    setPage("brief");
  }, []);

  // the patient's chosen time ran out: leave their records
  const sharedAccessEnded = useCallback(() => {
    setPatient(null);
    setPage("patients");
    setNotice("Shared access has ended. Ask the patient for a new code to see their records again.");
  }, []);

  const shared = Boolean(patient?.shared_until);

  let content;
  if (!user) content = <LoginPage onLogin={handleLogin} />;
  else if (page === "metrics") content = <MetricsPage />;
  else if (page === "open-share" && user.role === "doctor")
    content = <OpenSharePage initialToken={shareToken} onOpened={openShared} />;
  else if (page === "share" && patient && user.role === "patient") content = <SharePage patient={patient} />;
  else if (page === "consent")
    content = <ConsentPage onAccept={acceptConsent} onCancel={goToPatients} />;
  else if (!patient) content = <PatientsPage user={user} onOpen={openPatient} />;
  else if (page === "upload") content = <UploadPage patient={patient} onDone={() => setPage("timeline")} />;
  else if (page === "medications") content = <MedicationsPage patient={patient} />;
  else if (page === "flags") content = <FlagsPage patient={patient} />;
  else if (page === "ask") content = <AskPage patient={patient} />;
  else if (page === "audit") content = <AuditPage patient={patient} />;
  else if (page === "delete") content = <DeletePage patient={patient} onDeleted={goToPatients} />;
  else if (page === "brief" && user.role === "doctor") content = <BriefPage patient={patient} user={user} />;
  else if (page === "questions") content = <ThingsToCheckPage patient={patient} />;
  else content = <TimelinePage patient={patient} user={user} />;

  return (
    <>
      <Header user={user} onLogout={handleLogout} />
      <Disclaimer />
      <main>
        {user && (
          <nav className="nav">
            <button onClick={goToPatients} disabled={page === "patients"}>
              {user.role === "doctor" ? "Patients" : "My records"}
            </button>
            {user.role === "doctor" && (
              <button
                onClick={() => {
                  setPatient(null);
                  setNotice("");
                  setPage("open-share");
                }}
                disabled={page === "open-share"}
              >
                Open shared record
              </button>
            )}
            {patient &&
              page !== "consent" &&
              tabsFor(user.role)
                .filter(([key]) => !(shared && SHARED_HIDDEN_TABS.includes(key)))
                .map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => openPatient(patient, key)}
                  disabled={page === key}
                >
                  {label}
                </button>
              ))}
            <button onClick={() => setPage("metrics")} disabled={page === "metrics"}>
              Accuracy
            </button>
          </nav>
        )}
        {user && shared && (
          <p className="share-banner" role="status">
            Shared by the patient · read-only · ends in{" "}
            <Countdown expiresAt={patient.shared_until} onEnd={sharedAccessEnded} />
          </p>
        )}
        {user && notice && !patient && <p className="warn">{notice}</p>}
        {content}
      </main>
    </>
  );
}
