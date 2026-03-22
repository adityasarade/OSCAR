"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.OscarClient = void 0;
class OscarClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl.replace(/\/+$/, "");
    }
    updateBaseUrl(url) {
        this.baseUrl = url.replace(/\/+$/, "");
    }
    async healthCheck() {
        try {
            const res = await this.request("/health", {
                method: "GET",
            });
            return res.status === "ok";
        }
        catch {
            return false;
        }
    }
    async chat(message) {
        return this.request("/chat", {
            method: "POST",
            body: JSON.stringify({ message }),
        });
    }
    async chatStream(message, onEvent) {
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
                        const event = JSON.parse(json);
                        onEvent(event);
                    }
                    catch {
                        // skip malformed frames
                    }
                }
            }
        }
    }
    async getBranches() {
        return this.request("/branches", { method: "GET" });
    }
    async compare(base, head) {
        return this.request("/compare", {
            method: "POST",
            body: JSON.stringify({ base, head }),
        });
    }
    async review(branch, base) {
        return this.request("/review", {
            method: "POST",
            body: JSON.stringify({ branch, base }),
        });
    }
    async getHistory() {
        return this.request("/history", { method: "GET" });
    }
    async getMemory() {
        return this.request("/memory", { method: "GET" });
    }
    async request(path, options) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);
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
            return (await res.json());
        }
        finally {
            clearTimeout(timeout);
        }
    }
}
exports.OscarClient = OscarClient;
//# sourceMappingURL=oscarClient.js.map