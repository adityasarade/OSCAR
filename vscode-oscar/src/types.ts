// POST /chat
export interface ChatRequest {
    message: string;
    session_id?: string;
    repo_path?: string;
}

export interface ChatResponse {
    response: string;
    session_id?: string;  // not returned by backend
}

// POST /chat/stream — SSE event payloads
export interface ConfirmPayload {
    request_id: string;
    tool_name: string;
    args_summary: string;
    risk: "medium" | "high" | "dangerous";
}

export interface StreamEvent {
    type:
        | "step"
        | "tool_call"
        | "tool_result"
        | "thinking"
        | "response"
        | "error"
        | "done"
        | "confirm"
        | "cancelled";
    data: string | ConfirmPayload | null;
    step_number?: number;
    tool_name?: string;
    risk?: string;
    ok?: boolean;
}

// GET /health
export interface HealthResponse {
    status: string;
    version?: string;
    agent_ready?: boolean;
    git_available?: boolean;
}

// GET /providers
export interface ProviderModel {
    id: string;
    label: string;
    description: string;
    recommended: boolean;
}

export interface ProviderInfo {
    id: string;
    label: string;
    description: string;
    requires_api_key: boolean;
    api_key_env: string | null;
    requires_local_server: boolean;
    default_model: string;
    models: ProviderModel[];
}

export interface ProvidersResponse {
    providers: ProviderInfo[];
    current: {
        provider: string;
        model: string;
        fallback_provider: string;
        fallback_model: string;
    };
}

// GET /branches
export interface BranchesResponse {
    branches: string[];
    current: string;
    repo_path?: string;
}

// POST /compare
export interface CompareRequest {
    base: string;
    head: string;
    repo_path?: string;
}

export interface CompareResponse {
    success: boolean;
    output: string;
    error: string | null;
}

// POST /review
export interface ReviewRequest {
    branch: string;
    base?: string;
    repo_path?: string;
}

export interface ReviewResponse {
    success: boolean;
    output: string;
    error: string | null;
}

// GET /history
export interface HistoryEntry {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
}

export type HistoryResponse = HistoryEntry[];

// Webview ↔ Extension messages
export interface WebviewMessage {
    type:
        | "chat"
        | "compare"
        | "getBranches"
        | "getHistory"
        | "review"
        | "cancel"
        | "confirmResponse"
        | "refreshBranches";
    text?: string;
    base?: string;
    head?: string;
    branch?: string;
    request_id?: string;
    approved?: boolean;
}

export interface ExtensionMessage {
    type:
        | "chatResponse"
        | "streamEvent"
        | "branches"
        | "comparison"
        | "review"
        | "history"
        | "error"
        | "loading"
        | "streamDone"
        | "versionMismatch"
        | "workspaceInfo";
    data?: unknown;
    message?: string;
}
