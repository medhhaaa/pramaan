// Simple page state instead of a router: login -> patients -> one patient's pages.
import { useCallback, useEffect, useState } from "react";
import { hasSession, logout, setDummyUser, setLanguage } from "./api";
import Countdown from "./components/Countdown";
import Disclaimer from "./components/Disclaimer";
import Header from "./components/Header";
import LanguagePopup from "./components/LanguagePopup";
import { LanguageContext, translate } from "./i18n";
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

// tabs shown for an open patient; the first tab differs by role (labels: "tab.<key>" in i18n.jsx)
const tabsFor = (role) => [
  role === "doctor" ? "brief" : "questions",
  "timeline",
  "medications",
  "flags",
  "ask",
  "upload",
  "audit",
  "delete",
  ...(role === "patient" ? ["share"] : []),
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

  // The user's saved language. Before login (and before they choose), the last language
  // used on this browser, else English.
  const lang = user?.language || load("last_language") || "en";
  const t = (key, vars) => translate(lang, key, vars);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  function handleLogin(u) {
    save("user", u);
    if (u.language) save("last_language", u.language);
    setDummyUser(u);
    setUser(u);
    setPage(shareToken && u.role === "doctor" ? "open-share" : "patients");
  }

  // from the first-login popup and the header switch; saved on the account (users.language)
  async function changeLanguage(language) {
    await setLanguage(language);
    const updated = { ...user, language };
    save("user", updated);
    save("last_language", language);
    setUser(updated);
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
    setNotice("share.ended");
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
    <LanguageContext.Provider value={lang}>
      <Header user={user} onLogout={handleLogout} onChangeLanguage={changeLanguage} />
      <Disclaimer />
      <main>
        {user && (
          <nav className="nav">
            <button onClick={goToPatients} disabled={page === "patients"}>
              {user.role === "doctor" ? t("nav.patients") : t("nav.myRecords")}
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
                {t("nav.openShared")}
              </button>
            )}
            {patient &&
              page !== "consent" &&
              tabsFor(user.role)
                .filter((key) => !(shared && SHARED_HIDDEN_TABS.includes(key)))
                .map((key) => (
                <button
                  key={key}
                  onClick={() => openPatient(patient, key)}
                  disabled={page === key}
                >
                  {t(`tab.${key}`)}
                </button>
              ))}
            <button onClick={() => setPage("metrics")} disabled={page === "metrics"}>
              {t("nav.accuracy")}
            </button>
          </nav>
        )}
        {user && shared && (
          <p className="share-banner" role="status">
            {t("share.banner")}{" "}
            <Countdown expiresAt={patient.shared_until} onEnd={sharedAccessEnded} />
          </p>
        )}
        {user && notice && !patient && <p className="warn">{t(notice)}</p>}
        {content}
      </main>
      {/* first login: the account has no language yet */}
      {user && !user.language && <LanguagePopup onChoose={changeLanguage} />}
    </LanguageContext.Provider>
  );
}
