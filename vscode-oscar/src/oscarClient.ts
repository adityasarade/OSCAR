import {
    ChatResponse,
    BranchesResponse,
    CompareResponse,
    ReviewResponse,
    HistoryResponse,
    HealthResponse,
    StreamEvent,
} from "./types";

export class OscarClient {
    private baseUrl: string;
    private repoPath: string | null = null;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl.replace(/\/+$/, "");
    }

    updateBaseUrl(url: string): void {
        this.baseUrl = url.replace(/\/+$/, "");
    }

    setRepoPath(path: string | null): void {
        this.repoPath = path && path.trim() ? path : null;
    }

    getRepoPath(): string | null {
        return this.repoPath;
    }

    async healthCheck(): Promise<HealthResponse | null> {
        try {
            const qs = this.repoPath
                ? `?repo_path=${encodeURIComponent(this.repoPath)}`
                : "";
            return await this.request<HealthResponse>(`/health${qs}`, {
                method: "GET",
            });
        } catch {
            return null;
        }
    }

    async chat(message: string): Promise<ChatResponse> {
        return this.request<ChatResponse>("/chat", {
            method: "POST",
            body: JSON.stringify({
                message,
                repo_path: this.repoPath ?? undefined,
            }),
        });
    }

    async chatStream(
        message: string,
        onEvent: (event: StreamEvent) => void
    ): Promise<void> {
        const res = await fetch(`${this.baseUrl}/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                repo_path: this.repoPath ?? undefined,
            }),
        });

        if (!res.ok) {
            const text = await res.text();
            throw new Error(`Server error ${res.status}: ${text}`);
        }

        const body = res.body;
        if (!body) {
            throw new Error("No response body for streaming");
        }

        const reader = body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split("\n\n");
            buffer = frames.pop() ?? "";

            for (const frame of frames) {
                if (!frame.trim()) {
                    continue;
                }
                const dataLine = frame
                    .split("\n")
                    .find((line) => line.startsWith("data: "));
                if (dataLine) {
                    const json = dataLine.slice(6);
                    try {
                        const event: StreamEvent = JSON.parse(json);
                        onEvent(event);
                    } catch {
                        // skip malformed frames
                    }
                }
            }
        }
    }

    async getBranches(): Promise<BranchesResponse> {
        const qs = this.repoPath
            ? `?repo_path=${encodeURIComponent(this.repoPath)}`
            : "";
        return this.request<BranchesResponse>(`/branches${qs}`, { method: "GET" });
    }

    async compare(base: string, head: string): Promise<CompareResponse> {
        return this.request<CompareResponse>("/compare", {
            method: "POST",
            body: JSON.stringify({
                base,
                head,
                repo_path: this.repoPath ?? undefined,
            }),
        });
    }

    async review(branch: string, base?: string): Promise<ReviewResponse> {
        return this.request<ReviewResponse>("/review", {
            method: "POST",
            body: JSON.stringify({
                branch,
                base,
                repo_path: this.repoPath ?? undefined,
            }),
        });
    }

    async getHistory(): Promise<HistoryResponse> {
        return this.request<HistoryResponse>("/history", { method: "GET" });
    }

    async cancelChat(): Promise<void> {
        await fetch(`${this.baseUrl}/chat/cancel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
        });
    }

    async confirmTool(requestId: string, approved: boolean): Promise<void> {
        const res = await fetch(`${this.baseUrl}/chat/confirm`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ request_id: requestId, approved }),
        });
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`Confirm failed (${res.status}): ${text}`);
        }
    }

    private async request<T>(path: string, options: RequestInit): Promise<T> {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30_000);

        try {
            const res = await fetch(`${this.baseUrl}${path}`, {
                ...options,
                signal: controller.signal,
                headers: {
                    "Content-Type": "application/json",
                    ...options.headers,
                },
            });

            if (!res.ok) {
                const text = await res.text();
                throw new Error(`Server error ${res.status}: ${text}`);
            }

            return (await res.json()) as T;
        } finally {
            clearTimeout(timeout);
        }
    }
}
