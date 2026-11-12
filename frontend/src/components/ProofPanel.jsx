// Click-to-proof: show the fact's source document with the quoted line highlighted.
// The PDF (react-pdf) is shown when the backend sends pdf_base64. The text lines from
// read_pdf are always shown underneath, so the proof works even without a PDF.
import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { getDocument } from "../api";
import CorrectionForm from "./CorrectionForm";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const normalize = (s) => s.toLowerCase().replace(/\s+/g, " ").trim();

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function base64ToBytes(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// user + onCorrected are optional: without them the correction form is hidden
export default function ProofPanel({ fact, onClose, user, onCorrected }) {
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState("");
  const panelRef = useRef(null);
  const highlightRef = useRef(null);

  // TimelinePage gives this panel key={document_id}, so a new document starts with fresh state
  useEffect(() => {
    getDocument(fact.document_id).then(setDoc).catch((err) => setError(err.message));
  }, [fact.document_id]);

  // Scroll only inside the panel (scrollIntoView would also move the whole page).
  function scrollPanelTo(element) {
    const panel = panelRef.current;
    if (!panel || !element) return;
    const offset = element.getBoundingClientRect().top - panel.getBoundingClientRect().top;
    panel.scrollTop += offset - panel.clientHeight / 2;
  }

  // without a PDF, centre the highlighted text line
  useEffect(() => {
    if (doc && !doc.pdf_base64) scrollPanelTo(highlightRef.current);
  }, [doc, fact.fact_id]);

  // react-pdf wants a new object only when the PDF itself changes
  const file = useMemo(
    () => (doc?.pdf_base64 ? { data: base64ToBytes(doc.pdf_base64) } : null),
    [doc],
  );

  const quote = normalize(fact.quote);
  // Highlight PDF text pieces that are part of the quote. pdf.js splits lines into pieces,
  // so very short pieces are skipped to avoid marking stray numbers elsewhere on the page.
  const highlightText = ({ str }) => {
    const piece = normalize(str);
    const match = piece.length >= 3 && (quote.includes(piece) || piece.includes(quote));
    return match ? `<mark>${escapeHtml(str)}</mark>` : escapeHtml(str);
  };

  const pageLines = doc ? doc.lines.filter((l) => l.page === fact.page) : [];

  return (
    <aside className="proof" ref={panelRef}>
      <div className="proof-head">
        <strong>Source</strong>
        <button onClick={onClose}>Close</button>
      </div>

      <blockquote>"{fact.quote}"</blockquote>
      <p className="hint">
        {fact.document_id} · page {fact.page}, line {fact.line} ·{" "}
        {fact.quote_verified ? "quote found in document" : "quote NOT verified"}
      </p>

      {user && onCorrected && (
        <CorrectionForm key={fact.fact_id} fact={fact} user={user} onCorrected={onCorrected} />
      )}

      {error && <p className="error">{error}</p>}
      {!doc && !error && <p>Loading document...</p>}

      {doc && (
        <>
          <p>
            <strong>{doc.filename}</strong> ({doc.doc_type.replace("_", " ")}, {doc.document_date})
          </p>

          {file ? (
            <div className="pdf">
              {/* suspense={false}: react-pdf v11 otherwise needs Suspense + an error boundary,
                  and a bad PDF would blank the whole app instead of showing this error text */}
              <Document
                file={file}
                suspense={false}
                loading="Loading PDF..."
                error="Could not open the PDF."
              >
                <Page
                  pageNumber={fact.page}
                  width={440}
                  customTextRenderer={highlightText}
                  onRenderTextLayerSuccess={() =>
                    scrollPanelTo(panelRef.current?.querySelector(".pdf mark"))
                  }
                  renderAnnotationLayer={false}
                />
              </Document>
            </div>
          ) : (
            <p className="hint">PDF preview not available here; showing the document's text lines.</p>
          )}

          <h3>Page {fact.page} text</h3>
          <ol className="lines">
            {pageLines.map((l) => {
              const isQuote = l.line === fact.line;
              return (
                <li key={l.line} ref={isQuote ? highlightRef : null} className={isQuote ? "line-hit" : ""}>
                  <span className="line-no">{l.line}</span> {l.text}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </aside>
  );
}
