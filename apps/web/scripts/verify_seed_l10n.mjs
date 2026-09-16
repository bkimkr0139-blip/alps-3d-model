// seedL10n coverage verifier (R1+R2+R3). Every Korean string that can reach an
// ASIC panel — stored seed prose AND backend-composed messages (copilot
// summaries/facts/proposal texts, gate blocker details, impact-scan reasons) —
// must come out of seedTr() with no Hangul residue under both en and ja.
// A miss here is exactly how 한글 leaks into the ja/en demo UI.
// Usage: node scripts/verify_seed_l10n.mjs   (API :8000 · postgres :5433 up)
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WEB = new URL("..", import.meta.url).pathname;
const REPO = new URL("../../..", import.meta.url).pathname;
const HANGUL = /[가-힣]/;

// 1) load seedL10n.ts — Node ≥22.6 type-strips TS natively (vite 8 is
// rolldown-based, so there is no esbuild to bundle with). Node ESM needs
// explicit extensions, so copy the pair to a tmp dir with a fixed specifier.
const tmp = mkdtempSync(join(tmpdir(), "l10n-"));
for (const f of ["lstr.ts", "seedL10n.ts"]) {
  let src = readFileSync(join(WEB, "src/lib", f), "utf8");
  if (f === "seedL10n.ts") src = src.replace(`from "./lstr"`, `from "./lstr.ts"`);
  writeFileSync(join(tmp, f), src);
}
const { seedTr } = await import(join(tmp, "seedL10n.ts"));

// 2) DB candidates (stored Korean prose + composed messages in JSONB columns)
const pw = execFileSync("grep", ["^POSTGRES_PASSWORD=", join(REPO, ".env")], { encoding: "utf8" })
  .split("=")[1].trim().replace(/^"|"$/g, "");
const psql = (sql) =>
  execFileSync("psql", ["-h", "localhost", "-p", "5433", "-U", "alps", "-d", "alps_twin", "-tAc", sql],
    { encoding: "utf8", env: { ...process.env, PGPASSWORD: pw } }).split("\n").filter(Boolean);

// every string value anywhere inside a jsonb column (any depth)
const deep = (col, tbl) =>
  `SELECT DISTINCT q #>> '{}' FROM ${tbl} t, jsonb_path_query(t.${col}, 'lax $.**') q` +
  ` WHERE jsonb_typeof(q) = 'string' AND q #>> '{}' ~ '[가-힣]'`;

const db = new Set();
const add = (rows) => rows.forEach((r) => HANGUL.test(r) && db.add(r));
const addDeep = (col, tbl) => add(psql(deep(col, tbl)));
const addCol = (col, tbl) => add(psql(`SELECT DISTINCT ${col} FROM ${tbl} WHERE ${col} ~ '[가-힣]'`));

addCol("title", "asic_assumptions");
addCol("detail", "asic_assumptions");
addCol("note", "asic_assumptions");
addDeep("downstream", "asic_assumptions");
addDeep("resolved_evidence", "asic_assumptions");
addDeep("findings", "asic_impact_scans");
addCol("note", "asic_impact_scans");
addDeep("skipped", "asic_deviations");
addCol("rationale", "asic_deviations");
addCol("residual_risk", "asic_deviations");
addCol("note", "asic_deviations");
addDeep("result", "asic_copilot_interactions");
addDeep("payload", "asic_assumption_events");
// R2 stored prose (same panels share seedTr)
addDeep("blocks", "asic_signal_chains");
addCol("note", "asic_signal_chains");
addDeep("result", "asic_trade_studies");
addDeep("decision", "asic_trade_studies");
addCol("note", "asic_tool_runs");
addCol("note", "asic_test_flows");
addCol("symptom", "asic_fa_cases");
addCol("root_cause", "asic_fa_cases");
addDeep("observations", "asic_fa_cases");
addDeep("hypotheses", "asic_fa_cases");

// 3) live-composed gate blocker details (exist only in the API response)
try {
  const tokBody = "client_id=alps-twin-web&grant_type=password&username=demo.architect&password=demo1234";
  const tok = (await (await fetch("http://localhost:8081/realms/alps-twin/protocol/openid-connect/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: tokBody,
  })).json()).access_token;
  const get = async (path) => (await fetch(`http://localhost:8000/api/v1${path}`, {
    headers: { Authorization: `Bearer ${tok}` },
  })).json();
  for (const { template_id: t } of psql("SELECT DISTINCT template_id FROM asic_assumptions")) {
    const rep = await get(`/asic/gate-report/${t}`);
    for (const b of rep.blockers ?? []) {
      add([b.detail]);
      for (const e of b.evidence ?? []) HANGUL.test(e) && db.add(e);
    }
  }
} catch (e) {
  console.warn(`warn: live gate-report strings skipped (${String(e).slice(0, 100)})`);
}

// 4) every candidate must come out of seedTr without Hangul under en AND ja
const miss = [];
for (const s of [...db].sort()) {
  for (const lang of ["en", "ja"]) {
    const got = seedTr(s, lang);
    if (HANGUL.test(got)) { miss.push([lang, s, got]); break; }
  }
}
console.log(`candidates: ${db.size}  uncovered: ${miss.length}`);
for (const [lang, s, got] of miss) console.log(`MISS[${lang}] ${JSON.stringify(s)}\n  -> ${JSON.stringify(got)}`);
process.exit(miss.length ? 1 : 0);
