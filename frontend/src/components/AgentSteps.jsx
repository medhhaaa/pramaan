// "What the agent did" with one document: read, protect, extract, check, retry, classify,
// patient check, save, merge, questions (backend/agent/steps.py). Collapsed until opened.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, AlertTriangle, ShieldOff, RefreshCw } from 'lucide-react';
import { getAgentSteps } from '../api.js';

const ICON = { ok: CheckCircle2, warn: AlertTriangle, blocked: ShieldOff, retry: RefreshCw };

export default function AgentSteps({ docId }) {
  const { t } = useTranslation();
  const [steps, setSteps] = useState(null);
  const [error, setError] = useState('');

  function toggle(e) {
    if (e.target.open && steps === null) {
      getAgentSteps(docId).then((r) => setSteps(r.steps)).catch((err) => setError(err.message));
    }
  }

  return (
    <details className="agent-steps" onToggle={toggle}>
      <summary>{t('agent.title', { defaultValue: 'What the agent did' })}</summary>
      {error && <p className="error small">{error}</p>}
      {steps && steps.length === 0 && (
        <p className="muted small">{t('agent.none', { defaultValue: 'No steps recorded for this document (uploaded before the agent log existed).' })}</p>
      )}
      {steps && steps.length > 0 && (
        <ol className="agent-step-list">
          {steps.map((s, i) => {
            const Icon = ICON[s.status] || CheckCircle2;
            return (
              <li key={i} className={`agent-step agent-${s.status}`}>
                <Icon size={15} />
                <strong>{s.step}</strong>
                <span>{s.detail}</span>
                {s.ms != null && <span className="muted small mono">{s.ms} ms</span>}
              </li>
            );
          })}
        </ol>
      )}
    </details>
  );
}
