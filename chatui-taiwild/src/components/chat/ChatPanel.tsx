"use client";

import AppButton from "@/components/ui/AppButton";

type ChatRole = "user" | "assistant";

type ChatMessage = {
  role: ChatRole;
  content: string;
};

type Props = {
  messages: ChatMessage[];
  loading: boolean;
  error: string | null;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void | Promise<void>;
};

export default function ChatPanel(props: Props) {
  const canSend = !props.loading && props.input.trim().length > 0;

  return (
    <>
      <section className="flex-1 border border-zinc-200 dark:border-zinc-800 rounded bg-white dark:bg-zinc-900 p-4 overflow-auto min-h-[320px] max-h-[calc(100vh-320px)]">
        {props.messages.length === 0 ? (
          <div className="text-zinc-500">输入问题开始聊天。默认 strategy=auto。</div>
        ) : (
          <div className="flex flex-col gap-3">
            {props.messages.map((m, idx) => (
              <div key={idx} className={m.role === "user" ? "text-right" : "text-left"}>
                <div
                  className={
                    "inline-block max-w-[85%] rounded px-3 py-2 whitespace-pre-wrap break-words " +
                    (m.role === "user" ? "bg-zinc-200 dark:bg-zinc-700" : "bg-zinc-100 dark:bg-zinc-800")
                  }
                >
                  <div className="text-xs text-zinc-600 dark:text-zinc-400 mb-1">{m.role}</div>
                  <div>{m.content}</div>
                </div>
              </div>
            ))}
            {props.loading ? <div className="text-zinc-500">Thinking...</div> : null}
          </div>
        )}
      </section>

      {props.error ? <div className="text-sm text-red-600 dark:text-red-400">Error: {props.error}</div> : null}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) void props.onSend();
        }}
      >
        <input
          className="flex-1 border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900"
          value={props.input}
          onChange={(e) => props.onInputChange(e.target.value)}
          placeholder="Type your message..."
        />
        <AppButton type="submit" size="md" variant="primary" disabled={!canSend}>
          Send
        </AppButton>
      </form>
    </>
  );
}
