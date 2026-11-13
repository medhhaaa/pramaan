// Public landing page at "/" for visitors who are not logged in.
// All text comes from the "landing" block in src/i18n/*.json.
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight, FileSearch, Quote, Copy, CircleHelp, UserX, MessageSquareText,
  Upload, ScanText, ListChecks, ShieldCheck, Lock, ScrollText, Trash2,
} from 'lucide-react';
import Logo from '../components/Logo.jsx';
import { ThemeToggle } from '../components/Layout.jsx';
import '../styles/landing.css';

const FEATURES = [
  ['proof', FileSearch],
  ['quote', Quote],
  ['echo', Copy],
  ['gaps', CircleHelp],
  ['wrong', UserX],
  ['ask', MessageSquareText],
];
const STEPS = [
  ['upload', Upload],
  ['verify', ScanText],
  ['review', ListChecks],
];
const PRIVACY = [
  ['deid', ShieldCheck],
  ['encrypted', Lock],
  ['audit', ScrollText],
  ['delete', Trash2],
];

function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  const change = (e) => {
    i18n.changeLanguage(e.target.value);
    try { localStorage.setItem('pramaan_lang', e.target.value); } catch { /* storage blocked */ }
  };
  return (
    <select className="landing-lang" value={i18n.resolvedLanguage || 'en'} onChange={change} aria-label={t('landing.langLabel')}>
      {Object.entries(t('langs', { returnObjects: true })).map(([code, name]) => (
        <option key={code} value={code}>{name}</option>
      ))}
    </select>
  );
}

// A static picture of one timeline entry: an echoed medicine with its source line,
// plus a gap. Decoration that explains the idea; not real data.
function DemoCard() {
  const { t } = useTranslation();
  return (
    <div className="landing-demo" aria-hidden="true">
      <p className="landing-demo-label">{t('landing.demo.label')}</p>
      <div className="landing-demo-fact">
        <div className="landing-demo-row">
          <strong>{t('landing.demo.fact')}</strong>
          <span className="landing-pill landing-pill-echo"><Copy size={13} />{t('landing.demo.echo')}</span>
        </div>
        <div className="landing-demo-source">
          <span className="landing-demo-where">{t('landing.demo.source')}</span>
          <code className="landing-demo-quote"><mark>{t('landing.demo.quote')}</mark></code>
        </div>
        <p className="landing-demo-note">{t('landing.demo.note')}</p>
      </div>
      <div className="landing-demo-fact landing-demo-gap">
        <div className="landing-demo-row">
          <strong>{t('landing.demo.gap')}</strong>
          <span className="landing-pill landing-pill-gap"><CircleHelp size={13} /></span>
        </div>
        <p className="landing-demo-note">{t('landing.demo.gapNote')}</p>
      </div>
    </div>
  );
}

export default function Landing() {
  const { t } = useTranslation();
  return (
    <div className="landing">
      <header className="landing-nav">
        <Logo compact />
        <div className="landing-nav-actions">
          <LanguageSwitch />
          <ThemeToggle />
          <Link to="/login" className="btn btn-primary">{t('landing.navLogin')}</Link>
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero-text">
            <p className="landing-eyebrow">{t('landing.eyebrow')}</p>
            <h1>
              {t('landing.title')} <span className="landing-accent">{t('landing.titleAccent')}</span>
            </h1>
            <p className="landing-lead">{t('landing.lead')}</p>
            <div className="landing-ctas">
              <Link to="/login" className="btn btn-primary btn-lg">
                {t('landing.ctaStart')} <ArrowRight size={18} />
              </Link>
              <a href="#how" className="btn btn-ghost btn-lg">{t('landing.ctaHow')}</a>
            </div>
          </div>
          <DemoCard />
        </section>

        <section className="landing-section">
          <h2>{t('landing.featuresTitle')}</h2>
          <ul className="landing-features">
            {FEATURES.map(([key, Icon]) => (
              <li key={key} className="landing-feature">
                <span className="landing-icon"><Icon size={20} /></span>
                <h3>{t(`landing.features.${key}.title`)}</h3>
                <p>{t(`landing.features.${key}.text`)}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="landing-section" id="how">
          <h2>{t('landing.howTitle')}</h2>
          <ol className="landing-steps">
            {STEPS.map(([key, Icon], i) => (
              <li key={key} className="landing-step">
                <span className="landing-step-num">{i + 1}</span>
                <span className="landing-icon"><Icon size={20} /></span>
                <h3>{t(`landing.steps.${key}.title`)}</h3>
                <p>{t(`landing.steps.${key}.text`)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-section landing-privacy">
          <h2>{t('landing.privacyTitle')}</h2>
          <p className="landing-privacy-lead">{t('landing.privacyLead')}</p>
          <ul className="landing-privacy-list">
            {PRIVACY.map(([key, Icon]) => (
              <li key={key}><Icon size={18} /><span>{t(`landing.privacy.${key}`)}</span></li>
            ))}
          </ul>
        </section>

        <section className="landing-closing">
          <p>{t('landing.closing')}</p>
          <Link to="/login" className="btn btn-primary btn-lg">
            {t('landing.ctaStart')} <ArrowRight size={18} />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <p>{t('disclaimer')}</p>
        <p className="muted small">{t('landing.footerDemo')}</p>
      </footer>
    </div>
  );
}
