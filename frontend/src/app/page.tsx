"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Conversation = {
  id: string;
  title: string | null;
  created_at: string;
};

type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

type TraceStep = {
  id: string;
  conversation_id: string;
  step_type: string;
  content: string;
  created_at: string;
};

type ToolCall = {
  id: string;
  conversation_id: string;
  tool_name: string;
  input_payload: any;
  output_payload: any;
  created_at: string;
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

export default function Page() {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [traceSteps, setTraceSteps] = useState<TraceStep[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [autoTelemetry, setAutoTelemetry] = useState(true);

  const assistantDraftRef = useRef<string>("");

  const convoId = conversation?.id;

  async function createConversation() {
    const res = await fetch(`${API}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Agent Chat" }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data: Conversation = await res.json();
    setConversation(data);
    setMessages([]);
    setTraceSteps([]);
    setToolCalls([]);
  }

  async function loadHistory(id: string) {
    const res = await fetch(`${API}/conversations/${id}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setConversation(data.conversation);
    setMessages(data.messages);
  }

  async function loadTelemetry(id: string) {
    const res = await fetch(`${API}/conversations/${id}/telemetry`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setTraceSteps(data.trace_steps || []);
    setToolCalls(data.tool_calls || []);
  }

  // Auto refresh telemetry while streaming
  useEffect(() => {
    if (!convoId || !autoTelemetry) return;
    const t = setInterval(() => loadTelemetry(convoId).catch(() => {}), 1500);
    return () => clearInterval(t);
  }, [convoId, autoTelemetry]);

  // Load telemetry when conversation changes
  useEffect(() => {
    if (!convoId) return;
    loadTelemetry(convoId).catch(() => {});
  }, [convoId]);

  const canSend = useMemo(() => !!convoId && input.trim().length > 0 && !streaming, [convoId, input, streaming]);

  async function sendStream() {
    if (!convoId) return;
    const userText = input.trim();
    if (!userText) return;

    // Optimistically add user message to UI
    const now = new Date().toISOString();
    setMessages((prev) => [
      ...prev,
      {
        id: `local-user-${now}`,
        conversation_id: convoId,
        role: "user",
        content: userText,
        created_at: now,
      },
    ]);

    // Prepare assistant draft
    assistantDraftRef.current = "";
    setMessages((prev) => [
      ...prev,
      {
        id: `local-assistant-${now}`,
        conversation_id: convoId,
        role: "assistant",
        content: "",
        created_at: now,
      },
    ]);

    setInput("");
    setStreaming(true);

    const res = await fetch(`${API}/conversations/${convoId}/run/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_message: userText }),
    });

    if (!res.ok || !res.body) {
      setStreaming(false);
      throw new Error(await res.text());
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    const applyAssistantDraft = (text: string) => {
      setMessages((prev) => {
        const copy = [...prev];
        // last message should be assistant draft
        const idx = copy.length - 1;
        if (idx >= 0 && copy[idx].role === "assistant") {
          copy[idx] = { ...copy[idx], content: text };
        }
        return copy;
      });
    };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE frames end with \n\n
        let sepIndex;
        while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sepIndex);
          buffer = buffer.slice(sepIndex + 2);

          // Parse event + data lines
          let eventName = "message";
          let dataLine = "";

          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) eventName = line.replace("event:", "").trim();
            if (line.startsWith("data:")) dataLine += line.replace("data:", "").trim();
          }

          if (!dataLine) continue;

          const payload = JSON.parse(dataLine);

          if (eventName === "token") {
            assistantDraftRef.current += payload.delta || "";
            applyAssistantDraft(assistantDraftRef.current);
          }

          if (eventName === "agent_end") {
            // refresh from DB so local IDs become real IDs
            await loadHistory(convoId);
            await loadTelemetry(convoId);
          }
        }
      }
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <div className="mx-auto max-w-6xl p-4">
        <header className="flex items-center justify-between gap-3 py-3">
          <div>
            <h1 className="text-xl font-semibold">AI Agent Orchestrator Console</h1>
            <p className="text-sm text-gray-600">
              Streaming + Telemetry (trace_steps / tool_calls)
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => createConversation().catch((e) => alert(e.message))}
              className="rounded-xl bg-black px-3 py-2 text-sm text-white"
            >
              New Conversation
            </button>
            {conversation && (
              <button
                onClick={() => {
                  loadHistory(conversation.id).catch((e) => alert(e.message));
                  loadTelemetry(conversation.id).catch((e) => alert(e.message));
                }}
                className="rounded-xl border px-3 py-2 text-sm"
              >
                Refresh
              </button>
            )}
          </div>
        </header>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {/* Chat */}
          <div className="md:col-span-2 rounded-2xl border bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm text-gray-600">
                Conversation:{" "}
                <span className="font-mono text-xs text-gray-900">
                  {conversation?.id ?? "—"}
                </span>
              </div>
              <button
                disabled={!conversation}
                onClick={() => convoId && loadHistory(convoId).catch((e) => alert(e.message))}
                className="rounded-xl border px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Load History
              </button>
            </div>

            <div className="h-[480px] overflow-auto rounded-xl border bg-gray-50 p-3">
              {messages.length === 0 ? (
                <div className="text-sm text-gray-500">
                  Create a conversation, then send a message to see streaming.
                </div>
              ) : (
                <div className="space-y-3">
                  {messages.map((m) => (
                    <div key={m.id} className="rounded-xl bg-white p-3 shadow-sm">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                          {m.role}
                        </span>
                        <span className="text-xs text-gray-400">
                          {new Date(m.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <pre className="whitespace-pre-wrap text-sm">{m.content}</pre>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-3 flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask something…"
                className="flex-1 rounded-xl border px-3 py-2 text-sm"
                disabled={!conversation || streaming}
              />
              <button
                onClick={() => sendStream().catch((e) => alert(e.message))}
                disabled={!canSend}
                className="rounded-xl bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                {streaming ? "Streaming…" : "Send"}
              </button>
            </div>
          </div>

          {/* Telemetry */}
          <div className="rounded-2xl border bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm font-semibold">Telemetry</div>
              <label className="flex items-center gap-2 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={autoTelemetry}
                  onChange={(e) => setAutoTelemetry(e.target.checked)}
                />
                Auto refresh
              </label>
            </div>

            <div className="space-y-3">
              <section className="rounded-xl border p-3">
                <div className="mb-2 text-xs font-semibold text-gray-700">Trace Steps</div>
                <div className="max-h-52 overflow-auto space-y-2">
                  {traceSteps.length === 0 ? (
                    <div className="text-xs text-gray-500">No trace steps yet.</div>
                  ) : (
                    traceSteps.map((t) => (
                      <div key={t.id} className="rounded-lg bg-gray-50 p-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-mono text-gray-700">{t.step_type}</span>
                          <span className="text-[11px] text-gray-400">
                            {new Date(t.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-gray-700 whitespace-pre-wrap">
                          {t.content}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="rounded-xl border p-3">
                <div className="mb-2 text-xs font-semibold text-gray-700">Tool Calls</div>
                <div className="max-h-52 overflow-auto space-y-2">
                  {toolCalls.length === 0 ? (
                    <div className="text-xs text-gray-500">No tool calls yet.</div>
                  ) : (
                    toolCalls.map((c) => (
                      <div key={c.id} className="rounded-lg bg-gray-50 p-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-mono text-gray-700">{c.tool_name}</span>
                          <span className="text-[11px] text-gray-400">
                            {new Date(c.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        <details className="mt-1">
                          <summary className="cursor-pointer text-xs text-gray-600">Payloads</summary>
                          <pre className="mt-2 whitespace-pre-wrap text-[11px] text-gray-700">
                            {JSON.stringify({ input: c.input_payload, output: c.output_payload }, null, 2)}
                          </pre>
                        </details>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <button
                disabled={!convoId}
                onClick={() => convoId && loadTelemetry(convoId).catch((e) => alert(e.message))}
                className="w-full rounded-xl border px-3 py-2 text-sm disabled:opacity-50"
              >
                Refresh Telemetry
              </button>
            </div>
          </div>
        </div>

        <footer className="py-6 text-xs text-gray-500">
          Tip: If browser blocks cross-origin calls, we’ll add CORS in FastAPI.
        </footer>
      </div>
    </div>
  );
}
