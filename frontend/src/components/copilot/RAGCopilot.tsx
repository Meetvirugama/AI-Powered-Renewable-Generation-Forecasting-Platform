import { useState, useRef, useEffect, useCallback } from "react";
import type { RAGQueryResponse, RAGQueryRequest } from "../../types/api";
import { postRagQuery } from "../../api/endpoints";
import ragMock from "../../mocks/rag.json";
import { inr } from "../../lib/format";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  plantId: string;
  ruleYear?: number;
  blockNo?: number;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  response?: RAGQueryResponse;
  error?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXAMPLE_QUESTIONS = [
  "Why am I being penalised in block 54?",
  "What is the tolerance band for solar under the 2026 rules?",
  "How does portfolio pooling reduce my penalty?",
] as const;

const GUARDRAIL_LABELS: Record<string, string> = {
  numbers_stripped:
    "Figures removed — the copilot produced a number the DSM engine did not",
  fallback_template: "Template answer — live retrieval unavailable",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RAGCopilot({ plantId, ruleYear, blockNo }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Tracks the in-flight request so a second question (or an unmount) can cancel a
  // slower first one — previously there was no cancellation at all, so a fast reply
  // to question 2 could be silently overwritten when question 1's slower answer
  // landed afterward.
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Cancel any in-flight request on unmount.
  useEffect(() => () => abortRef.current?.abort(), []);

  // ------ send logic -------------------------------------------------------

  const send = useCallback(
    async (question: string) => {
      if (!question.trim() || loading) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setInput("");
      setMessages((prev) => [...prev, { role: "user", text: question }]);
      setLoading(true);

      try {
        let response: RAGQueryResponse;

        if (import.meta.env.VITE_USE_MOCKS === "true") {
          await new Promise((r) => setTimeout(r, 400));
          response = ragMock as RAGQueryResponse;
        } else {
          const body: RAGQueryRequest = {
            question,
            plant_id: plantId,
            ...(ruleYear != null ? { rule_year: ruleYear } : {}),
            ...(blockNo != null ? { block_no: blockNo } : {}),
          };
          response = await postRagQuery(body, controller.signal);
        }

        if (controller.signal.aborted) return;
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: response.answer, response },
        ]);
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const msg =
          err instanceof Error
            ? err.message
            : typeof err === "object" && err !== null && "message" in err
              ? String((err as { message: unknown }).message)
              : "An unknown error occurred";
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: "", error: msg },
        ]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          inputRef.current?.focus();
        }
      }
    },
    [loading, plantId, ruleYear, blockNo],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  // ------ idle state (example questions) -----------------------------------

  const isIdle = messages.length === 0 && !loading;

  // ------ render -----------------------------------------------------------

  return (
    <div className="flex flex-1 flex-col min-h-0">

      {/* Message list — scrolls, page does not */}
      <div className="flex-1 overflow-y-auto py-2 flex flex-col gap-4">
        {/* Idle: example questions */}
        {isIdle && (
          <div className="flex flex-col items-center gap-3 py-6">
            <p className="text-[12px] text-text-muted uppercase tracking-[0.06em] font-medium">
              Try asking
            </p>
            {EXAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => send(q)}
                className="w-full max-w-md text-left rounded-[var(--radius-control)] border border-border bg-surface-2 px-4 py-2.5 text-[14px] leading-[1.5] text-text hover:border-accent/40 transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Messages */}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col gap-2 ${
              msg.role === "user" ? "items-end" : "items-start"
            }`}
          >
            {/* Bubble */}
            {msg.role === "user" ? (
              <div className="max-w-[85%] rounded-[var(--radius-control)] bg-accent px-4 py-2.5 text-[14px] leading-[1.5] text-on-accent">
                {msg.text}
              </div>
            ) : msg.error ? (
              /* Error state */
              <div className="max-w-[85%] flex flex-col gap-2">
                <div className="rounded-[var(--radius-control)] border border-pen-4 bg-pen-1/30 px-4 py-2.5 text-[14px] leading-[1.5] text-text">
                  {msg.error}
                </div>
                <button
                  onClick={() => {
                    // Retry: find the last user message before this error
                    const userMsg = messages
                      .slice(0, idx)
                      .reverse()
                      .find((m) => m.role === "user");
                    if (userMsg) {
                      // Remove the error message and retry
                      setMessages((prev) => prev.filter((_, i) => i !== idx));
                      send(userMsg.text);
                    }
                  }}
                  className="self-start rounded-[var(--radius-chip)] border border-border bg-surface-2 px-3 py-1 text-[12px] font-medium text-text-muted hover:text-text transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg"
                >
                  Retry
                </button>
              </div>
            ) : (
              /* Assistant answer */
              <div className="max-w-[85%] flex flex-col gap-2">
                {/* Guardrail warning — prominent, never hidden */}
                {msg.response?.meta.guardrail &&
                  msg.response.meta.guardrail !== "pass" && (
                    <div className="flex items-start gap-2 rounded-[var(--radius-chip)] bg-dev-over/20 border border-dev-over/40 px-3 py-2 text-[12px] leading-[1.4] font-medium text-dev-over">
                      <span className="shrink-0">⚠</span>
                      <span>
                        {GUARDRAIL_LABELS[msg.response.meta.guardrail] ??
                          msg.response.meta.guardrail}
                      </span>
                    </div>
                  )}

                {/* Answer prose */}
                <div
                  className="rounded-[var(--radius-control)] bg-surface-2 px-4 py-2.5 text-[14px] leading-[1.6] text-text"
                  style={{ maxWidth: "70ch" }}
                >
                  {msg.text}
                </div>

                {/* Engine values — these are the ONLY numbers we trust */}
                {msg.response?.engine_values &&
                  Object.keys(msg.response.engine_values).length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(msg.response.engine_values).map(
                        ([key, val]) => (
                          <span
                            key={key}
                            className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] bg-surface-2 border border-border px-2 py-0.5 text-[11px]"
                            style={{ fontVariantNumeric: "tabular-nums" }}
                          >
                            <span className="text-text-muted">{key}:</span>
                            <span className="font-medium text-text">
                              {typeof val === "number" && key.includes("inr")
                                ? inr(val)
                                : String(val)}
                            </span>
                          </span>
                        ),
                      )}
                    </div>
                  )}

                {/* Citation badges */}
                {msg.response?.citations &&
                  msg.response.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {msg.response.citations.map((cite, cIdx) => {
                        const label = `${cite.clause} · ${cite.doc}${cite.page != null ? ` · p.${cite.page}` : ""}`;

                        if (cite.url) {
                          return (
                            <a
                              key={cIdx}
                              href={cite.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center rounded-[var(--radius-chip)] bg-surface-2 border border-border px-2 py-0.5 text-[11px] text-text-muted hover:border-accent/40 hover:text-text transition-colors"
                            >
                              {label}
                            </a>
                          );
                        }
                        return (
                          <span
                            key={cIdx}
                            className="inline-flex items-center rounded-[var(--radius-chip)] bg-surface-2 border border-border px-2 py-0.5 text-[11px] text-text-muted"
                          >
                            {label}
                          </span>
                        );
                      })}
                    </div>
                  )}

                {/* Meta footnote */}
                {msg.response?.meta && (
                  <p className="text-[11px] text-text-muted leading-[1.3]">
                    {msg.response.meta.llm_model && (
                      <span>Model: {msg.response.meta.llm_model}</span>
                    )}
                    {msg.response.meta.llm_model && " · "}
                    {msg.response.meta.retrieved_chunks != null && (
                      <span>
                        {msg.response.meta.retrieved_chunks} chunks retrieved
                      </span>
                    )}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex items-start">
            <div className="rounded-[var(--radius-control)] bg-surface-2 px-4 py-2.5 text-[14px] text-text-muted animate-pulse">
              Thinking…
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar — pinned at bottom */}
      <div className="shrink-0 pt-3 flex gap-2">
        <input
          ref={inputRef}
          id="rag-copilot-question"
          name="question"
          type="text"
          autoComplete="off"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about DSM rules…"
          disabled={loading}
          className="flex-1 h-10 rounded-[var(--radius-control)] border border-border bg-surface-2 px-3 text-[14px] text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg disabled:opacity-60"
        />
        <button
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          className="h-10 px-4 rounded-[var(--radius-control)] bg-accent text-on-accent text-[14px] font-medium transition-colors hover:bg-accent-dim focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </div>
    </div>
  );
}
