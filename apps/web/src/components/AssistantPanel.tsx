import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { assistantApi, type PendingActionInfo } from "../lib/api";
import { enumLabel } from "../i18n";

type Item =
  | { kind: "text"; from: "user" | "ai"; text: string }
  | {
      kind: "action";
      pending: PendingActionInfo;
      state: "pending" | "executed" | "failed" | "cancelled" | "expired";
      outcome?: string;
    };

type AssistantOutcome = {
  status: "executed" | "failed" | "cancelled";
  result?: unknown;
  detail?: unknown;
};

// Substitutes the synthetic tool result (requires_user_confirmation) with the
// real outcome, then the next chat call lets the model summarize/chain — one
// code path for confirm and cancel (server stays stateless apart from the
// pending-action record). Thread shape: OpenAI chat format (role:"tool"
// messages correlated by tool_call_id) since the local-LLM provider switch.
function replaceToolResult(thread: unknown[], toolCallId: string, payload: unknown): unknown[] {
  return thread.map((m) => {
    const msg = m as { role?: string; tool_call_id?: string; content?: unknown };
    if (msg.role !== "tool" || msg.tool_call_id !== toolCallId) return m;
    return { ...msg, content: JSON.stringify(payload) };
  });
}

function outcomePayload(status: string, result: AssistantOutcome): unknown {
  if (status === "executed") return { status: "executed", result: result.result };
  if (status === "cancelled") return { status: "cancelled_by_user" };
  return { status: "failed", detail: result.detail };
}

export function AssistantPanel() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<unknown[] | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  function scrollToEnd() {
    requestAnimationFrame(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
    });
  }

  function appendItems(...added: Item[]) {
    setItems((prev) => [...prev, ...added]);
    scrollToEnd();
  }

  async function sendTurn(messages: unknown[]) {
    setBusy(true);
    setError(null);
    try {
      const res = await assistantApi.chat(messages, i18n.resolvedLanguage ?? "en");
      setThread(res.thread);
      appendItems(
        ...res.display
          .filter((d) => d.type === "text" && d.text)
          .map((d): Item => ({ kind: "text", from: "ai", text: d.text! })),
        ...(res.pending_action ? [{ kind: "action", pending: res.pending_action, state: "pending" } as Item] : [])
      );
    } catch (e) {
      setError(String(e).includes("503") ? t("assistant.unavailable") : t("assistant.error"));
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    appendItems({ kind: "text", from: "user", text });
    await sendTurn([...(thread ?? []), { role: "user", content: text }]);
  }

  async function resolveAction(item: Item & { kind: "action" }, action: "confirm" | "cancel") {
    const { pending } = item;
    setBusy(true);
    setError(null);
    try {
      const res = action === "confirm" ? await assistantApi.confirm(pending.action_id) : await assistantApi.cancel(pending.action_id);
      const ok = res.status === "executed" || res.status === "cancelled";
      setItems((prev) =>
        prev.map((it) =>
          it.kind === "action" && it.pending.action_id === pending.action_id
            ? {
                ...it,
                state: res.status === "executed" ? "executed" : res.status === "cancelled" ? "cancelled" : "failed",
                outcome:
                  res.status === "failed"
                    ? `${t("assistant.failedPrefix")} ${typeof res.detail === "string" ? res.detail : JSON.stringify(res.detail)}`
                    : undefined,
              }
            : it
        )
      );
      if (ok && thread) {
        // feed the outcome back so the model summarizes (and may propose more)
        const nextThread = replaceToolResult(
          thread,
          pending.tool_use_id,
          outcomePayload(res.status, res)
        );
        setThread(nextThread); // optimistic; sendTurn replaces it with the server's
        await sendTurn(nextThread);
      }
    } catch (e) {
      const msg = String(e);
      if (msg.includes("404")) {
        setItems((prev) =>
          prev.map((it) =>
            it.kind === "action" && it.pending.action_id === pending.action_id
              ? { ...it, state: "expired", outcome: t("assistant.expired") }
              : it
          )
        );
      } else if (msg.includes("403")) {
        setItems((prev) =>
          prev.map((it) =>
            it.kind === "action" && it.pending.action_id === pending.action_id
              ? { ...it, state: "failed", outcome: msg }
              : it
          )
        );
      } else {
        setError(t("assistant.error"));
      }
    } finally {
      setBusy(false);
    }
  }

  function actionTitle(pending: PendingActionInfo): string {
    const args = pending.args;
    switch (pending.tool) {
      case "open_gate":
        return t("assistant.actions.open_gate", {
          name: (args.name as string) || "Virtual Verification Complete",
          baseline_id: (args.baseline_id as string) ?? "·",
        });
      case "submit_gate":
        return t("assistant.actions.submit_gate", { gate_id: args.gate_id as string });
      case "add_gate_comment":
        return t("assistant.actions.add_gate_comment", { gate_id: args.gate_id as string });
      case "decide_gate":
        return t("assistant.actions.decide_gate", {
          gate_id: args.gate_id as string,
          decision: enumLabel(t, "decision", String(args.decision)),
        });
      default:
        return t("assistant.actions.create_baseline");
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label={t("assistant.open")}
        style={{
          position: "fixed",
          right: 20,
          bottom: 20,
          width: 52,
          height: 52,
          borderRadius: "50%",
          background: "#ff6b35",
          color: "white",
          border: "none",
          fontSize: 22,
          cursor: "pointer",
          boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
          zIndex: 1000,
        }}
      >
        ✨
      </button>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        right: 20,
        bottom: 20,
        width: 380,
        maxWidth: "calc(100vw - 32px)",
        height: "60vh",
        background: "#0f172a",
        border: "1px solid #334155",
        borderRadius: 12,
        display: "flex",
        flexDirection: "column",
        zIndex: 1000,
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", borderBottom: "1px solid #334155" }}>
        <strong style={{ fontSize: 14 }}>{t("assistant.title")}</strong>
        <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 16 }}>
          ✕
        </button>
      </div>

      <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {items.length === 0 && <div style={{ opacity: 0.5, fontSize: 13 }}>{t("assistant.placeholder")}</div>}
        {items.map((item, idx) =>
          item.kind === "text" ? (
            <div
              key={idx}
              style={{
                alignSelf: item.from === "user" ? "flex-end" : "flex-start",
                maxWidth: "85%",
                padding: "6px 10px",
                borderRadius: 10,
                fontSize: 13,
                whiteSpace: "pre-wrap",
                background: item.from === "user" ? "#1d4ed8" : "#1e293b",
                color: "#e2e8f0",
              }}
            >
              {item.text}
            </div>
          ) : (
            <div
              key={idx}
              style={{
                alignSelf: "stretch",
                border:
                  item.state === "pending" ? "1px solid #b45309" : "1px solid #334155",
                background: item.state === "pending" ? "#1c1408" : "#111c31",
                borderRadius: 10,
                padding: 10,
                fontSize: 13,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                {item.state === "pending" ? "⚠️ " : item.state === "executed" ? "✅ " : "🚫 "}
                {actionTitle(item.pending)}
              </div>
              <details>
                <summary style={{ opacity: 0.6, cursor: "pointer", fontSize: 12 }}>{t("assistant.payload")}</summary>
                <pre style={{ fontSize: 11, whiteSpace: "pre-wrap", margin: "4px 0 0" }}>{item.pending.summary_args}</pre>
              </details>
              {item.state === "pending" ? (
                <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                  <button onClick={() => resolveAction(item, "confirm")} disabled={busy} style={{ background: "#166534", padding: "4px 12px", borderRadius: 6 }}>
                    {t("assistant.approve")}
                  </button>
                  <button onClick={() => resolveAction(item, "cancel")} disabled={busy} style={{ background: "#7f1d1d", padding: "4px 12px", borderRadius: 6 }}>
                    {t("assistant.reject")}
                  </button>
                </div>
              ) : (
                item.outcome && <div style={{ marginTop: 6, fontSize: 12, color: "#fca5a5", whiteSpace: "pre-wrap" }}>{item.outcome}</div>
              )}
            </div>
          )
        )}
        {busy && <div style={{ opacity: 0.5, fontSize: 12 }}>{t("assistant.thinking")}</div>}
        {error && <div style={{ color: "#ef4444", fontSize: 12 }}>{error}</div>}
      </div>

      <div style={{ display: "flex", gap: 6, padding: 10, borderTop: "1px solid #334155" }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && send()}
          placeholder={t("assistant.placeholder")}
          style={{ flex: 1, background: "#020617", color: "white", border: "1px solid #334155", borderRadius: 6, padding: "8px 10px", fontSize: 13 }}
        />
        <button onClick={send} disabled={busy || !input.trim()} style={{ padding: "8px 14px", borderRadius: 6 }}>
          {t("assistant.send")}
        </button>
      </div>
    </div>
  );
}
