export type Session = {
  id: string;
  title: string;
  cwd: string;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type Intercept = {
  id: string;
  session_id: string;
  tool_name: string;
  original_input: Record<string, unknown>;
  modified_input: Record<string, unknown>;
  status: "pending" | "approved" | "rejected";
};

export type Subagent = {
  id: number;
  session_id: string;
  tool_use_id: string;
  name: string;
  subagent_type: string;
  prompt: string;
  result: string;
  status: "running" | "done" | "failed";
  created_at: string;
  completed_at: string | null;
};

export type AuthStatus = {
  logged_in: boolean;
  email: string | null;
  org_name: string | null;
  auth_method: string | null;
  subscription_type: string | null;
  error?: string | null;
};

export type LoginSession = {
  login_id: string;
  status: string;
  url: string | null;
  error: string | null;
  output?: string[];
  logged_in?: boolean | null;
  email?: string | null;
};
