// Public landing page at "/" for visitors who are not logged in.
// Text: the "landing" block in src/i18n/*.json.
// Images: src/assets/landing/ — the synthetic demo patient's real PDFs (rendered, key lines
// highlighted) and screenshots of the app itself in dummy mode, one per theme.
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, ArrowDown, ShieldCheck, Lock, ScrollText, Trash2, FileText } from 'lucide-react';
import Logo from '../components/Logo.jsx';
import { ThemeToggle } from '../components/Layout.jsx';
import doc2019 from '../assets/landing/doc-2019.jpg';
import doc2022 from '../assets/landing/doc-2022.jpg';
import doc2023 from '../assets/landing/doc-2023.jpg';
import timelineLight from '../assets/landing/app-timeline-light.jpg';
import timelineDark from '../assets/landing/app-timeline-dark.jpg';
import medicationLight from '../assets/landing/app-medication-light.jpg';
import medicationDark from '../assets/landing/app-medication-dark.jpg';
import '../styles/landing.css';

// Sunita's seven documents. Dates are copied exactly as written on each paper.
// tone = the kind of trap, which picks the colour of its tag.
const TRAIL = [
  { id: 'd1', date: '12/03/2019', tone: 'start' },
  { id: 'd2', date: '2021-06-20', tone: 'unit' },
  { id: 'd3', date: '05-Aug-2022', tone: 'conflict' },
  { id: 'd4', date: '15/01/2023', tone: 'copy' },
  { id: 'd5', date: '16/01/2023', tone: 'unit' },
  { id: 'd6', date: '16/01/2023', tone: 'duplicate' },
  { id: 'd7', date: '04/05/2023', tone: 'wrong' },
];
const COMPARE = [
  ['atenolol', 'copy'],
  ['allergy', 'conflict'],
  ['glucose', 'unit'],
  ['psa', 'wrong'],
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

// One screenshot per theme; CSS shows the one that matches <html data-theme>.
function Shot({ light, dark, alt, width, height }) {
  return (
    <div className="landing-shot">
      <div className="landing-shot-bar" aria-hidden="true"><span /><span /><span /></div>
      <img className="landing-shot-light" src={light} alt={alt} loading="lazy" width={width} height={height} />
      <img className="landing-shot-dark" src={dark} alt={alt} loading="lazy" width={width} height={height} />
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
        {/* ---------- hero: the pitch, next to the actual papers ---------- */}
        <section className="landing-hero">
          <div className="landing-hero-text">
            <p className="landing-kicker">{t('landing.kicker')}</p>
            <h1>
              {t('landing.title')} <em>{t('landing.titleAccent')}</em>
            </h1>
            <p className="landing-lead">{t('landing.lead')}</p>
            <div className="landing-ctas">
              <Link to="/login" className="btn btn-primary btn-lg">
                {t('landing.ctaStart')} <ArrowRight size={18} />
              </Link>
              <a href="#example" className="btn btn-ghost btn-lg">
                {t('landing.ctaHow')} <ArrowDown size={18} />
              </a>
            </div>
          </div>

          <figure className="landing-papers">
            <div className="landing-paper-stack" role="img" aria-label={t('landing.docsAlt')}>
              <img className="landing-paper landing-paper-1" src={doc2019} alt="" width="893" height="638" />
              <img className="landing-paper landing-paper-2" src={doc2022} alt="" width="893" height="911" />
              <img className="landing-paper landing-paper-3" src={doc2023} alt="" width="893" height="615" />
            </div>
            <figcaption className="landing-notes">
              <p className="landing-note landing-note-conflict">{t('landing.notes.conflict')}</p>
              <p className="landing-note landing-note-copy">{t('landing.notes.copy')}</p>
              <p className="landing-note landing-note-change">{t('landing.notes.change')}</p>
            </figcaption>
          </figure>
        </section>

        {/* ---------- the paper trail ---------- */}
        <section className="landing-section" id="example">
          <div className="landing-section-head">
            <h2>{t('landing.trail.title')}</h2>
            <p>{t('landing.trail.lead')}</p>
          </div>
          <ol className="landing-trail">
            {TRAIL.map(({ id, date, tone }) => (
              <li key={id} className="landing-trail-item">
                <span className="landing-trail-date">{date}</span>
                <span className="landing-trail-type"><FileText size={15} aria-hidden="true" />{t(`landing.trail.items.${id}.type`)}</span>
                <span className={`landing-tag landing-tone-${tone}`}>{t(`landing.trail.items.${id}.trap`)}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* ---------- summary vs Pramaan ---------- */}
        <section className="landing-section">
          <div className="landing-section-head">
            <h2>{t('landing.compare.title')}</h2>
          </div>
          <div className="landing-compare">
            <div className="landing-summary">
              <p className="landing-compare-label">{t('landing.compare.summaryLabel')}</p>
              <blockquote>{t('landing.compare.summaryText')}</blockquote>
              <p className="landing-summary-note">{t('landing.compare.summaryNote')}</p>
            </div>
            <div className="landing-pramaan">
              <p className="landing-compare-label">{t('landing.compare.pramaanLabel')}</p>
              <ul>
                {COMPARE.map(([key, tone]) => (
                  <li key={key} className={`landing-tone-${tone}`}>
                    <strong>{t(`landing.compare.rows.${key}.name`)}</strong>
                    <span>{t(`landing.compare.rows.${key}.text`)}</span>
                  </li>
                ))}
              </ul>
              <p className="landing-compare-hint">{t('landing.compare.sourceHint')}</p>
            </div>
          </div>
        </section>

        {/* ---------- screenshots ---------- */}
        <section className="landing-section">
          <div className="landing-section-head">
            <h2>{t('landing.inside.title')}</h2>
          </div>
          <div className="landing-inside">
            <figure className="landing-inside-item">
              <Shot light={timelineLight} dark={timelineDark} alt={t('landing.inside.timelineAlt')} width="1500" height="900" />
              <figcaption>
                <strong>{t('landing.inside.timeline.title')}</strong> {t('landing.inside.timeline.text')}
              </figcaption>
            </figure>
            <figure className="landing-inside-item">
              <Shot light={medicationLight} dark={medicationDark} alt={t('landing.inside.medicationAlt')} width="1500" height="705" />
              <figcaption>
                <strong>{t('landing.inside.medication.title')}</strong> {t('landing.inside.medication.text')}
              </figcaption>
            </figure>
          </div>
        </section>

        {/* ---------- privacy ---------- */}
        <section className="landing-section landing-privacy">
          <div className="landing-section-head">
            <h2>{t('landing.privacyTitle')}</h2>
            <p>{t('landing.privacyLead')}</p>
          </div>
          <ul className="landing-privacy-list">
            {PRIVACY.map(([key, Icon]) => (
              <li key={key}><Icon size={18} aria-hidden="true" /><span>{t(`landing.privacy.${key}`)}</span></li>
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
