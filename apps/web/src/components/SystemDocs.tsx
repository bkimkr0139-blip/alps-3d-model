import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import docKo from "../assets/systemDoc.ko.md?raw";
import docEn from "../assets/systemDoc.en.md?raw";
import docJa from "../assets/systemDoc.ja.md?raw";

// The doc itself is authored per locale (not machine-switched at render):
// prose of this length reads properly only when written in the language.
// The download filename follows the locale so attachments file sensibly.
const DOCS: Record<string, { md: string; file: string }> = {
  ko: { md: docKo, file: "ALPS_Twin_시스템문서_v1.2.md" },
  en: { md: docEn, file: "ALPS_Twin_System_Documentation_v1.2.md" },
  ja: { md: docJa, file: "ALPS_Twin_システムドキュメント_v1.2.md" },
};

// System documentation viewer: renders the bundled markdown (a single
// build-time `?raw` import — the file is the doc, the download button hands
// out exactly the same bytes) with a small purpose-built renderer. The doc
// is authored against a known subset of markdown (headings, lists, tables,
// blockquotes, bold/inline-code), so the renderer stays ~100 lines and
// dependency-free — no new package for the parallel sessions to merge around.

// ── inline: **bold** and `code` ──
function inline(text: string, keyBase: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter((p) => p !== "");
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={`${keyBase}-${i}`}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`"))
      return (
        <code key={`${keyBase}-${i}`} style={{ background: "var(--alps-bg-raise)", border: "1px solid var(--alps-border-strong)", borderRadius: 4, padding: "1px 5px", fontSize: "0.9em" }}>
          {p.slice(1, -1)}
        </code>
      );
    return <span key={`${keyBase}-${i}`}>{p}</span>;
  });
}

type Block =
  | { kind: "h1" | "h2" | "h3"; text: string; id?: string }
  | { kind: "p"; text: string }
  | { kind: "hr" }
  | { kind: "quote"; lines: string[] }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] };

function parse(md: string): Block[] {
  const lines = md.split("\n");
  const blocks: Block[] = [];
  let i = 0;
  let h2n = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("### ")) { blocks.push({ kind: "h3", text: line.slice(4) }); i++; continue; }
    if (line.startsWith("## ")) { blocks.push({ kind: "h2", text: line.slice(3), id: `sec-${h2n++}` }); i++; continue; }
    if (line.startsWith("# ")) { blocks.push({ kind: "h1", text: line.slice(2) }); i++; continue; }
    if (line.trim() === "---") { blocks.push({ kind: "hr" }); i++; continue; }
    if (line.startsWith("> ")) {
      const q: string[] = [];
      while (i < lines.length && lines[i].startsWith("> ")) { q.push(lines[i].slice(2)); i++; }
      blocks.push({ kind: "quote", lines: q });
      continue;
    }
    if (/^\d+\. /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) { items.push(lines[i].replace(/^\d+\. /, "")); i++; }
      blocks.push({ kind: "ol", items });
      continue;
    }
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) { items.push(lines[i].slice(2)); i++; }
      blocks.push({ kind: "ul", items });
      continue;
    }
    if (line.startsWith("|")) {
      const tl: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) { tl.push(lines[i]); i++; }
      const cells = (l: string) => l.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(tl[0]);
      const rows = tl.slice(2).map(cells); // tl[1] is the |---|---| separator
      blocks.push({ kind: "table", head, rows });
      continue;
    }
    if (line.trim() === "") { i++; continue; }
    const p: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^(#|> |- |\d+\. |\|)/.test(lines[i]) && lines[i].trim() !== "---") {
      p.push(lines[i]); i++;
    }
    blocks.push({ kind: "p", text: p.join(" ") });
  }
  return blocks;
}

const cell = { padding: "7px 10px", border: "1px solid var(--alps-border-strong)", textAlign: "left" as const, verticalAlign: "top" as const };

export function SystemDocs() {
  const { t, i18n } = useTranslation();
  // resolvedLanguage (not the raw code) so e.g. "ja-JP" still finds the ja doc;
  // the Record lookup falls back to the English doc for anything unknown.
  const doc = DOCS[i18n.resolvedLanguage ?? ""] ?? DOCS.en!;
  const blocks = useMemo(() => parse(doc.md), [doc]);
  const toc = useMemo(() => blocks.filter((b) => b.kind === "h2" && !!b.id) as { id: string; text: string }[], [blocks]);

  // Same bytes as rendered — the download can never drift from the doc.
  // Created in an effect, NOT useMemo: StrictMode's dev double-mount runs
  // useMemo once but fires the first cleanup, which revoked the URL the
  // anchor still held (observed: downloads failing with "canceled"). With
  // state+effect the last effect run always owns a live URL.
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  useEffect(() => {
    const u = URL.createObjectURL(new Blob([doc.md], { type: "text/markdown;charset=utf-8" }));
    setBlobUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [doc]);

  const [copied, setCopied] = useState(false);

  function scrollTo(id: string) {
    document.getElementById(`sysdoc-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div style={{ height: "100%", overflowY: "auto" }}>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        {/* Toolbar — actions are level with the reading area, download hands
            out the exact bytes this tab renders. */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginBottom: 8 }}>
          <button
            onClick={() => {
              void navigator.clipboard.writeText(doc.md).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); });
            }}
            style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--alps-border-strong)", background: "var(--alps-bg-raise)", color: "var(--alps-text)", fontFamily: "inherit", fontSize: 13, cursor: "pointer" }}
          >
            {copied ? t("docs.copied") : t("docs.copy")}
          </button>
          {blobUrl ? (
            <a
              href={blobUrl}
              download={doc.file}
              style={{ display: "inline-flex", alignItems: "center", padding: "6px 10px", borderRadius: 6, background: "#2563eb", color: "white", textDecoration: "none", fontSize: 13, fontWeight: 600 }}
            >
              ↓ {t("docs.download")}
            </a>
          ) : (
            <span style={{ display: "inline-flex", alignItems: "center", padding: "6px 10px", borderRadius: 6, background: "var(--alps-bg-raise)", color: "var(--alps-text-faint)", fontSize: 13 }}>…</span>
          )}
        </div>

        <article style={{ background: "var(--alps-bg-card)", border: "1px solid var(--alps-border-strong)", borderRadius: 10, padding: "28px 32px", lineHeight: 1.7, fontSize: 14 }}>
          {/* TOC from the h2 blocks — a doc this size needs jump links */}
          <nav style={{ border: "1px solid var(--alps-border-strong)", borderRadius: 8, background: "var(--alps-bg-raise)", padding: "10px 14px", marginBottom: 20, fontSize: 13 }}>
            <div style={{ color: "var(--alps-text-faint)", fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>{t("docs.toc")}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px" }}>
              {toc.map((h) => (
                <a key={h.id} href={`#${h.id}`} onClick={(e) => { e.preventDefault(); scrollTo(h.id); }} style={{ color: "var(--alps-accent-id)", textDecoration: "none" }}>
                  {h.text}
                </a>
              ))}
            </div>
          </nav>

          {blocks.map((b, bi) => {
            switch (b.kind) {
              case "h1":
                return <h1 key={bi} style={{ fontSize: 24, margin: "0 0 8px" }}>{b.text}</h1>;
              case "h2":
                return (
                  <h2 key={bi} id={`sysdoc-${b.id}`} style={{ fontSize: 19, margin: "28px 0 10px", paddingBottom: 6, borderBottom: "1px solid var(--alps-border-strong)", scrollMarginTop: 12 }}>
                    {b.text}
                  </h2>
                );
              case "h3":
                return <h3 key={bi} style={{ fontSize: 15, margin: "18px 0 8px", color: "var(--alps-accent-id)" }}>{b.text}</h3>;
              case "hr":
                return <hr key={bi} style={{ border: "none", borderTop: "1px solid var(--alps-border-strong)", margin: "20px 0" }} />;
              case "quote":
                return (
                  <blockquote key={bi} style={{ margin: "12px 0", padding: "10px 14px", borderLeft: "3px solid #fbbf24", background: "var(--alps-bg-raise)", borderRadius: "0 8px 8px 0" }}>
                    {b.lines.map((l, li) => <p key={li} style={{ margin: li ? "8px 0 0" : 0 }}>{inline(l, `q${bi}-${li}`)}</p>)}
                  </blockquote>
                );
              case "ul":
                return (
                  <ul key={bi} style={{ margin: "8px 0", paddingLeft: 22 }}>
                    {b.items.map((it, ii) => <li key={ii} style={{ margin: "4px 0" }}>{inline(it, `u${bi}-${ii}`)}</li>)}
                  </ul>
                );
              case "ol":
                return (
                  <ol key={bi} style={{ margin: "8px 0", paddingLeft: 22 }}>
                    {b.items.map((it, ii) => <li key={ii} style={{ margin: "4px 0" }}>{inline(it, `o${bi}-${ii}`)}</li>)}
                  </ol>
                );
              case "table":
                return (
                  <div key={bi} style={{ overflowX: "auto", margin: "12px 0" }}>
                    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                      <thead>
                        <tr>{b.head.map((h, hi) => <th key={hi} style={{ ...cell, background: "var(--alps-bg-raise)", fontWeight: 600 }}>{inline(h, `th${bi}-${hi}`)}</th>)}</tr>
                      </thead>
                      <tbody>
                        {b.rows.map((r, ri) => (
                          <tr key={ri}>
                            {r.map((c, ci) => <td key={ci} style={cell}>{inline(c, `td${bi}-${ri}-${ci}`)}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              case "p":
                return <p key={bi} style={{ margin: "10px 0" }}>{inline(b.text, `p${bi}`)}</p>;
            }
          })}
        </article>
      </div>
    </div>
  );
}
