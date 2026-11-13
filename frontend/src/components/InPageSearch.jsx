// Shared pieces of the in-page search (Medications and Records pages).
import { useTranslation } from 'react-i18next';
import { Search, X, Loader2, Quote, CalendarDays, Sparkles } from 'lucide-react';
import { splitHighlights } from '../lib/inPageSearch.js';

export function SearchBar({ value, onChange, busy, placeholder, results }) {
  const { t } = useTranslation();
  const active = value.trim() && results;
  return (
    <div className="ips-bar" role="search">
      <div className="search ips-input">
        {busy ? <Loader2 size={18} className="spin" aria-hidden="true" /> : <Search size={18} aria-hidden="true" />}
        <input
          className="input" type="search" value={value} placeholder={placeholder}
          aria-label={placeholder} onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') onChange(''); }}
        />
        {value && (
          <button type="button" className="icon-btn ips-clear" aria-label={t('search.clear')} onClick={() => onChange('')}>
            <X size={18} />
          </button>
        )}
      </div>
      <p className="muted small ips-status" aria-live="polite">
        {active && !busy && (results.error
          ? results.error
          : results.byId.size === 0 ? t('search.none', { q: results.q }) : '')}
      </p>
    </div>
  );
}

// text with the matched words marked
export function Highlight({ text, terms }) {
  return splitHighlights(text, terms).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>));
}

const REASON_ICON = { mentioned: Quote, same_visit: CalendarDays, similar: Sparkles };
const REASON_CLASS = { mentioned: 'chip-info', same_visit: 'chip-patient', similar: 'chip-neutral' };

// The ONE strongest reason an item matched. Tooltip: the source line for "Mentioned with it",
// the item it shares a visit with for "Same visit".
export function ReasonChip({ result, viaLabel }) {
  const { t } = useTranslation();
  const Icon = REASON_ICON[result.reason];
  const tip = result.reason === 'mentioned' && result.source
    ? t('search.tipMentioned', { text: result.source.text, page: result.source.page, line: result.source.line })
    : result.reason === 'same_visit'
      ? t('search.tipSameVisit', { item: viaLabel || result.via })
      : t('search.tipSimilar');
  return (
    <span className={`chip ${REASON_CLASS[result.reason] || 'chip-neutral'} ips-reason`} title={tip} tabIndex={0} aria-label={`${t(`search.reason.${result.reason}`)}: ${tip}`}>
      {Icon && <Icon size={14} aria-hidden="true" />}{t(`search.reason.${result.reason}`)}
    </span>
  );
}

// "Related to 'pneumonia' (3)" heading for the top section
export function RelatedHeading({ q, n }) {
  const { t } = useTranslation();
  return <h2 className="ips-section-title">{t('search.related', { q, n })}</h2>;
}
