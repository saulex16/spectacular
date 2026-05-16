import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelLogin,
  fetchAuthStatus,
  pollLogin,
  startLogin,
  submitLoginCode,
} from "./api";
import type { AuthStatus, LoginSession } from "./types";

type Props = {
  open: boolean;
  onClose: () => void;
  onLoggedIn: (status: AuthStatus) => void;
};

export function ClaudeLoginModal({ open, onClose, onLoggedIn }: Props) {
  const [step, setStep] = useState<"idle" | "loading" | "ready" | "submitting" | "error">(
    "idle",
  );
  const [login, setLogin] = useState<LoginSession | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const loginIdRef = useRef<string | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopPoll();
    setStep("idle");
    setLogin(null);
    setCode("");
    setError(null);
    setCopied(false);
    loginIdRef.current = null;
  }, [stopPoll]);

  useEffect(() => {
    if (!open) return;

    let alive = true;
    reset();
    setStep("loading");

    void (async () => {
      try {
        const session = await startLogin();
        if (!alive) return;
        loginIdRef.current = session.login_id;
        setLogin(session);
        if (session.url) {
          setStep("ready");
          return;
        }
        pollRef.current = setInterval(() => {
          void (async () => {
            const id = loginIdRef.current;
            if (!id || !alive) return;
            try {
              const next = await pollLogin(id);
              if (!alive) return;
              setLogin(next);
              if (next.url) {
                setStep("ready");
                stopPoll();
              }
              if (next.status === "failed") {
                setError(next.error ?? "Login failed");
                setStep("error");
                stopPoll();
              }
            } catch {
              /* ignore transient poll errors */
            }
          })();
        }, 600);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "Could not start login");
        setStep("error");
      }
    })();

    return () => {
      alive = false;
      stopPoll();
      const id = loginIdRef.current;
      if (id) void cancelLogin(id).catch(() => {});
    };
  }, [open, reset, stopPoll]);

  async function onCopyUrl() {
    if (!login?.url) return;
    try {
      await navigator.clipboard.writeText(login.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy — select the link and copy manually");
    }
  }

  async function onSubmitCode() {
    if (!login?.login_id || !code.trim()) return;
    setStep("submitting");
    setError(null);
    try {
      const result = await submitLoginCode(login.login_id, code.trim());
      if (result.logged_in) {
        const status = await fetchAuthStatus();
        onLoggedIn(status);
        onClose();
        return;
      }
      setError(result.error ?? "Invalid or expired code");
      setStep("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit code");
      setStep("ready");
    }
  }

  async function onCancel() {
    if (loginIdRef.current) await cancelLogin(loginIdRef.current).catch(() => {});
    onClose();
  }

  if (!open) return null;

  return (
    <div className="intercept-overlay" onClick={() => void onCancel()}>
      <div
        className="intercept-modal login-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="login-title"
      >
        <div className="intercept-header">
          <span className="intercept-badge" id="login-title">
            Sign in with Claude
          </span>
        </div>
        <p className="intercept-label">
          Same flow as <code>/login</code> in Claude Code — open the link, sign in, then paste
          the session code from your browser.
        </p>

        {step === "loading" && <p className="login-status">Starting login…</p>}

        {login?.url && (
          <div className="login-url-block">
            <label className="intercept-label">1. Open this link</label>
            <a
              className="login-url"
              href={login.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {login.url}
            </a>
            <div className="login-url-actions">
              <button type="button" className="btn" onClick={() => void onCopyUrl()}>
                {copied ? "Copied" : "Copy link"}
              </button>
              <a
                className="btn ghost"
                href={login.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open in browser
              </a>
            </div>
          </div>
        )}

        {(step === "ready" || step === "submitting") && (
          <>
            <label className="intercept-label" htmlFor="login-code">
              2. Paste the session code from Claude.ai
            </label>
            <input
              id="login-code"
              className="login-code-input"
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Paste code here"
              disabled={step === "submitting"}
              autoComplete="off"
              onKeyDown={(e) => {
                if (e.key === "Enter" && code.trim()) void onSubmitCode();
              }}
            />
          </>
        )}

        {error && <p className="login-error">{error}</p>}

        <div className="intercept-actions">
          {(step === "ready" || step === "submitting") && (
            <button
              type="button"
              className="btn"
              onClick={() => void onSubmitCode()}
              disabled={!code.trim() || step === "submitting"}
            >
              {step === "submitting" ? "Verifying…" : "Continue"}
            </button>
          )}
          <button type="button" className="btn ghost" onClick={() => void onCancel()}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
