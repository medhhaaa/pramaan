import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getTimeline, getFlags } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import { StatusChip, BadgeChip, FlagChip, CopyChip, ConfidenceChip } from '../components/Chip.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import { EditFact, NeedsReading, Unsure } from '../components/HandwritingReview.jsx';

// a fact read from handwriting that a person should check: low score or best-guess words
const needsCheck = (f) => f.confidence != null && (f.confidence < 85 || (f.unsure || []).length > 0);
import PatientGate from '../components/PatientGate.jsx';
import LoadError from '../components/LoadError.jsx';
import { fmtDate, yearOf } from '../lib/format.js';

function TimelineInner() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [facts, setFacts] = useState([]);
  const [hideCopies, setHideCopies] = useState(true);
  const [legend, setLegend] = useState(false);
  const [src, setSrc] = useState(null);
  const [hl, setHl] = useState(null);

  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((n) => n + 1);

  useEffect(() => { setError(''); getTimeline(pid).then(setFacts).catch((e) => setError(e.message)); }, [pid, refresh]);

  const rows = useMemo(() => facts.filter((f) => !(hideCopies && f.echo_of)), [facts, hideCopies]);
  const years = useMemo(() => {
    const map = {};
    rows.forEach((f) => { (map[yearOf(f.event_date)] ||= []).push(f); });
    return Object.entries(map).sort((a, b) => b[0].localeCompare(a[0]));
  }, [rows]);

  // Echo copies point at the original fact; show the original's document id (e.g. p1_d1).
  const docName = (factId) => {
    const original = facts.find((x) => x.fact_id === factId);
    return original ? original.document_id : factId;
  };

  if (error) return <LoadError message={error} />;

  return (
    <section>
      <div className="page-head">
        <h1>{t('timeline.title')}</h1>
        <div className="btn-row">
          <label className="toggle"><input type="checkbox" checked={hideCopies} onChange={(e) => setHideCopies(e.target.checked)} />{t('timeline.hideCopies')}</label>
          <button className="btn btn-ghost btn-sm" onClick={() => setLegend(!legend)}>{t('timeline.legend')}</button>
        </div>
      </div>

      {legend && (
        <div className="card legend">
          <span className="chip chip-doc">{t('status.documented')}</span>
          <span className="chip chip-outline">{t('status.negated')}</span>
          <span className="chip chip-gap">{t('status.not_documented')}</span>
          <span className="chip chip-verified">{t('badges.doctor_verified')}</span>
          <span className="chip chip-info">{t('badges.independent_2plus')}</span>
          <span className="chip chip-neutral">{t('badges.single_document')}</span>
          <span className="chip chip-patient">{t('badges.patient_reported')}</span>
          <span className="chip chip-danger">{t('badges.conflicting')}</span>
        </div>
      )}

      <NeedsReading pid={pid} refreshKey={refresh} onChanged={reload} onView={(id) => { setHl(null); setSrc(id); }} />

      {rows.length === 0 && <div className="empty-state card"><p>{t('timeline.empty')}</p></div>}

      {years.map(([year, list]) => (
        <div key={year} className="year-block">
          <h2 className="year-head">{year}</h2>
          <div className="table-wrap card">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t('timeline.date')}</th>
                  <th scope="col">{t('timeline.type')}</th>
                  <th scope="col">{t('timeline.name')}</th>
                  <th scope="col">{t('timeline.doseValue')}</th>
                  <th scope="col">{t('timeline.status')}</th>
                  <th scope="col">{t('timeline.badge')}</th>
                  <th scope="col">{t('timeline.flags')}</th>
                  <th scope="col">{t('timeline.source')}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((f) => (
                  <tr key={f.fact_id} className={`${f.echo_of ? 'row-echo' : ''} ${needsCheck(f) ? 'row-check' : ''}`}>
                    <td>
                      <div>{fmtDate(f.event_date, i18n.language)}</div>
                      <div className="muted small mono">{f.date_raw}</div>
                    </td>
                    <td>{f.type}</td>
                    <td>
                      <Unsure text={f.name} words={f.unsure} />
                      {f.echo_of && <div><CopyChip docName={docName(f.echo_of)} /></div>}
                    </td>
                    <td className="mono">
                      <Unsure text={[f.dose, f.frequency].filter(Boolean).join(' ') || `${f.value ?? ''} ${f.unit ?? ''}`.trim()} words={f.unsure} />
                    </td>
                    <td><StatusChip status={f.status} /></td>
                    <td><BadgeChip badge={f.badge} /></td>
                    <td className="chip-stack">{f.flags.map((fl) => <FlagChip key={fl} flag={fl} />)}<ConfidenceChip value={f.confidence} /></td>
                    <td>
                      <button className="link-btn" onClick={() => { setHl(f.line); setSrc(f.document_id); }}>
                        p{f.page} · l{f.line}
                      </button>
                      {f.flags.includes('handwriting') && <div><EditFact fact={f} low={needsCheck(f)} onSaved={reload} /></div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <p className="muted small">{t('translatedNote')}</p>
      <DocDrawer docId={src} highlightLine={hl} onClose={() => setSrc(null)} />
    </section>
  );
}

export default function Timeline() {
  return <PatientGate><TimelineInner /></PatientGate>;
}
