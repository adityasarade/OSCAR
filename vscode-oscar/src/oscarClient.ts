import {
    ChatResponse,
    BranchesResponse,
    CompareResponse,
    ReviewResponse,
    HistoryResponse,
    MemoryResponse,
    StreamEvent,
} from "./types";

export class OscarClient {
    private baseUrl: string;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl.replace(/\/+$/, "");
    }

    updateBaseUrl(url: string): void {
        this.baseUrl = url.replace(/\/+$/, "");
    }

    async healthCheck(): Promise<boolean> {
        try {
            const res = await this.request<{ status: string }>("/health", {
                method: "GET",
            });
            return res.status === "ok";
        } catch {
            return false;
        }
    }

    async chat(message: string): Promise<ChatResponse> {
        return this.request<ChatResponse>("/chat", {
            method: "POST",
            body: JSON.stringify({ message }),
        });
    }

    async chatStream(
        message: string,
        onEvent: (event: StreamEvent) => void
    ): Promise<void> {
        const res = await fetch(`${this.baseUrl}/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
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
        return this.request<BranchesResponse>("/branches", { method: "GET" });
    }

    async compare(base: string, head: string): Promise<CompareResponse> {
        return this.request<CompareResponse>("/compare", {
            method: "POST",
            body: JSON.stringify({ base, head }),
        });
    }

    async review(branch: string, base?: string): Promise<ReviewResponse> {
        return this.request<ReviewResponse>("/review", {
            method: "POST",
            body: JSON.stringify({ branch, base }),
        });
    }

    async getHistory(): Promise<HistoryResponse> {
        return this.request<HistoryResponse>("/history", { method: "GET" });
    }

    async getMemory(): Promise<MemoryResponse> {
        return this.request<MemoryResponse>("/memory", { method: "GET" });
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
