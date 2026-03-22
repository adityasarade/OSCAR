// POST /chat
export interface ChatRequest {
    message: string;
    session_id?: string;
}

export interface ChatResponse {
    response: string;
    session_id: string;
}

// POST /chat/stream — SSE event payloads
export interface StreamEvent {
    type: "step" | "tool_call" | "tool_result" | "thinking" | "response" | "error" | "done";
    data: string;
    step_number?: number;
    tool_name?: string;
}

// GET /branches
export interface BranchesResponse {
    branches: string[];
    current: string;
}

// POST /compare
export interface CompareRequest {
    base: string;
    head: string;
}

export interface CompareResponse {
    base: string;
    head: string;
    summary: string;
    commit_count: string;
    diffstat: string;
    commit_log: string;
}

// POST /review
export interface ReviewRequest {
    branch: string;
    base?: string;
}

export interface ReviewResponse {
    branch: string;
    base: string;
    summary: string;
    diffstat: string;
    diff: string;
}

// GET /history
export interface HistoryEntry {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
}

export type HistoryResponse = HistoryEntry[];

// GET /memory
export interface MemoryBlock {
    name: string;
    content: string;
    max_tokens: number;
    priority: number;
}

export interface MemoryResponse {
    blocks: MemoryBlock[];
}

// Webview ↔ Extension messages
export interface WebviewMessage {
    type: "chat" | "compare" | "getBranches" | "getHistory" | "review";
    text?: string;
    base?: string;
    head?: string;
    branch?: string;
}

export interface ExtensionMessage {
    type: "chatResponse" | "streamEvent" | "branches" | "comparison" | "review"
        | "history" | "error" | "loading" | "streamDone";
    data?: unknown;
    message?: string;
}
