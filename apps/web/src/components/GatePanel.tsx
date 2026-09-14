import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { enumLabel, checklistLabel } from "../i18n";
import { api, type Gate, type GateComment, type GateDecision } from "../lib/api";

/** S11: Review & Gate — submission blocked on missing evidence (§12.2),
 * comments before decision, e-signature-style approve/reject (§FR-09). */
export function GatePanel({ variantId }: { variantId: string | null }) {
  const { t } = useTranslation();
  const [gate, setGate] = useState<Gate | null>(null);
  const [comments, setComments] = useState<GateComment[]>([]);
  const [decisions, setDecisions] = useState<GateDecision[]>([]);
  const [commentText, setCommentText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (!variantId) return;
    const gates = await api.listGates(variantId);
    const current = gates[0] ?? null;
    setGate(current);
    if (current) {
      setComments(await api.listGateComments(current.id));
      setDecisions(await api.listGateDecisions(current.id));
    } else {
      setComments([]);
      setDecisions([]);
    }
  }

  useEffect(() => {
    setGate(null);
    setError(null);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variantId]);

  async function createGate() {
    if (!variantId) return;
    setError(null);
    try {
      const baseline = await api.latestActiveBaseline(variantId);
      if (!baseline) {
        setError(t("gate.noActiveBaseline"));
        return;
      }
      await api.createGate({
        business_id: `${baseline.business_id}-GATE-VV`,
        variant_id: variantId,
        baseline_id: baseline.id,
        name: "Virtual Verification Complete",
      });
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function submit() {
    if (!gate) return;
    setError(null);
    try {
      await api.submitGate(gate.id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function decide(decision: "approved" | "rejected") {
    if (!gate || !commentText.trim()) {
      setError(t("gate.decisionFirst"));
      return;
    }
    setError(null);
    try {
      await api.decideGate(gate.id, decision, commentText);
      setCommentText("");
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function addComment() {
    if (!gate || !commentText.trim()) return;
    setError(null);
    try {
      await api.addGateComment(gate.id, commentText);
      setCommentText("");
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  if (!variantId) return null;

  if (!gate) {
    return (
      <div>
        <p style={{ opacity: 0.6, fontSize: 13 }}>{t("gate.empty")}</p>
        <button onClick={createGate}>{t("gate.openGateButton")}</button>
        {error && <div style={{ color: "#ef4444", fontSize: 12, marginTop: 6 }}>{error}</div>}
      </div>
    );
  }

  return (
    <div style={{ fontSize: 13 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{gate.name}</strong>
        <span>{enumLabel(t, "gateStatus", gate.status)}</span>
      </div>
      <div style={{ opacity: 0.6, fontSize: 12 }}>{gate.business_id}</div>

      {gate.status === "draft" && <button onClick={submit} style={{ marginTop: 8 }}>{t("gate.submitForReview")}</button>}

      {gate.evidence_checklist && (
        <div style={{ marginTop: 8 }}>
          <div style={{ opacity: 0.7, fontSize: 12 }}>{t("gate.evidenceChecklist")}</div>
          <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
            {Object.entries(gate.evidence_checklist.checklist).map(([k, ok]) => (
              <li key={k} style={{ color: ok ? "#22c55e" : "#ef4444" }}>
                {ok ? "✓" : "✗"} {checklistLabel(t, k)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {comments.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ opacity: 0.7, fontSize: 12 }}>{t("gate.comments")}</div>
          {comments.map((c) => (
            <div key={c.id} style={{ borderLeft: "2px solid #334155", paddingLeft: 8, marginTop: 4 }}>
              <div style={{ opacity: 0.6, fontSize: 11 }}>{c.author}</div>
              <div>{c.text}</div>
            </div>
          ))}
        </div>
      )}

      {decisions.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ opacity: 0.7, fontSize: 12 }}>{t("gate.decisions")}</div>
          {decisions.map((d) => (
            <div key={d.id} style={{ borderLeft: "2px solid #22c55e", paddingLeft: 8, marginTop: 4 }}>
              <div style={{ opacity: 0.6, fontSize: 11 }}>
                {d.actor} ({d.actor_roles.join(", ")}) · {enumLabel(t, "decision", d.decision)}
              </div>
              <div>{d.comment}</div>
            </div>
          ))}
        </div>
      )}

      {gate.status === "pending_review" && (
        <div style={{ marginTop: 10 }}>
          <textarea
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder={t("gate.commentPlaceholder")}
            style={{ width: "100%", minHeight: 50, background: "#0f172a", color: "white", border: "1px solid #334155", borderRadius: 4 }}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button onClick={addComment}>{t("gate.addComment")}</button>
            <button onClick={() => decide("approved")} style={{ background: "#166534" }}>{t("gate.approve")}</button>
            <button onClick={() => decide("rejected")} style={{ background: "#7f1d1d" }}>{t("gate.reject")}</button>
          </div>
        </div>
      )}

      {error && <div style={{ color: "#ef4444", fontSize: 12, marginTop: 6 }}>{error}</div>}
    </div>
  );
}
