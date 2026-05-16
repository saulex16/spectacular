import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

type Props = { content: string };

export const MarkdownMessage = memo(function MarkdownMessage({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const text = String(children).replace(/\n$/, "");
          if (match) {
            return (
              <SyntaxHighlighter
                PreTag="div"
                language={match[1]}
                style={oneDark}
                customStyle={{
                  margin: "8px 0",
                  borderRadius: 6,
                  fontSize: "13px",
                  padding: "10px 12px",
                }}
                codeTagProps={{
                  style: { fontFamily: 'ui-monospace, "JetBrains Mono", monospace' },
                }}
              >
                {text}
              </SyntaxHighlighter>
            );
          }
          return (
            <code className={className} {...props}>
              {children}
            </code>
          );
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
