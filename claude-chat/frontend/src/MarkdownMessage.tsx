import { memo, useCallback, useRef, useState, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

type Props = { content: string };

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CodeBlock({ language, text }: { language: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onCopy = useCallback(async () => {
    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    const ok = await copyText(text);
    if (!ok) return;
    setCopied(true);
    resetTimerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-lang">{language}</span>
        <button
          type="button"
          className="code-block-copy"
          onClick={() => void onCopy()}
          aria-label={copied ? "Copied" : "Copy code"}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        PreTag="div"
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: "0 0 6px 6px",
          fontSize: "13px",
          padding: "10px 12px",
        }}
        codeTagProps={{
          style: { fontFamily: 'ui-monospace, "JetBrains Mono", monospace' },
        }}
      >
        {text}
      </SyntaxHighlighter>
    </div>
  );
}

function InlineCode({
  className,
  text,
  ...props
}: ComponentPropsWithoutRef<"code"> & { text: string }) {
  const [copied, setCopied] = useState(false);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onCopy = useCallback(async () => {
    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    const ok = await copyText(text);
    if (!ok) return;
    setCopied(true);
    resetTimerRef.current = setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <code
      className={`${className ?? ""} inline-code-copyable`.trim()}
      {...props}
      title={copied ? "Copied" : "Click to copy"}
      onClick={() => void onCopy()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          void onCopy();
        }
      }}
    >
      {text}
    </code>
  );
}

export const MarkdownMessage = memo(function MarkdownMessage({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const text = String(children).replace(/\n$/, "");
          if (match) {
            return <CodeBlock language={match[1]} text={text} />;
          }
          return <InlineCode className={className} text={text} {...props} />;
        },
        a({ children, href }) {
          return (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
});
