// In-page search on the Medications and Records pages (backend: GET /patients/{id}/search).
// The page keeps its normal list; a query only moves matching items into a "Related" section.
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { searchRecords } from '../api.js';

export const DEBOUNCE_MS = 300;

// query -> {q, byId: Map(item_id -> result), error} for that query, or null while there is none.
// Answers to an older query are dropped, so fast typing never shows stale results.
export function useInPageSearch(pid, page) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const latest = useRef('');

  useEffect(() => {
    const q = query.trim();
    latest.current = q;
    if (!q || !pid) { setResults(null); setBusy(false); return undefined; }
    setBusy(true);
    const timer = setTimeout(async () => {
      try {
        const list = await searchRecords(pid, q, page);
        if (latest.current === q) setResults({ q, byId: new Map(list.map((r) => [r.item_id, r])), error: null });
      } catch (e) {
        if (latest.current === q) setResults({ q, byId: new Map(), error: e.message });
      } finally {
        if (latest.current === q) setBusy(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, pid, page]);

  return { query, setQuery, results, busy };
}

// "Tab. Augmentin 625mg - for pneumonia" + ["pneumonia"] -> [{text, hit}] pieces to render
export function splitHighlights(text, terms) {
  const words = (terms || []).filter(Boolean).sort((a, b) => b.length - a.length);
  if (!text || !words.length) return [{ text: text || '', hit: false }];
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  // with one capture group, split() puts every match at an odd index
  return text.split(new RegExp(`(${escaped.join('|')})`, 'i'))
    .map((p, i) => ({ text: p, hit: i % 2 === 1 }))
    .filter((p) => p.text !== '');
}

// Smoothly move cards to their new place when the order changes (FLIP). Each moving element
// needs data-flip="<stable id>" and must sit inside containerRef. Off for reduced motion.
export function useFlip(containerRef, signature) {
  const prev = useRef(new Map());
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const next = new Map();
    el.querySelectorAll('[data-flip]').forEach((node) => {
      const rect = node.getBoundingClientRect();
      next.set(node.dataset.flip, rect);
      const before = prev.current.get(node.dataset.flip);
      if (reduce || !before) return;
      const dx = before.left - rect.left;
      const dy = before.top - rect.top;
      if (!dx && !dy) return;
      node.style.transition = 'none';
      node.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        node.style.transition = 'transform 280ms cubic-bezier(0.2, 0.7, 0.2, 1)';
        node.style.transform = '';
      });
    });
    prev.current = next;
  }, [containerRef, signature]);
}
