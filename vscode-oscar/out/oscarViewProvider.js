"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.OscarViewProvider = void 0;
const vscode = __importStar(require("vscode"));
class OscarViewProvider {
    constructor(extensionUri, client) {
        this.extensionUri = extensionUri;
        this.client = client;
    }
    resolveWebviewView(webviewView, _context, _token) {
        this.view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [
                vscode.Uri.joinPath(this.extensionUri, "media"),
            ],
        };
        webviewView.webview.html = this.getHtmlForWebview(webviewView.webview);
        webviewView.webview.onDidReceiveMessage((message) => this.handleMessage(message));
    }
    async handleMessage(message) {
        this.postMessage({ type: "loading", data: true });
        try {
            switch (message.type) {
                case "chat":
                    await this.handleChat(message.text);
                    break;
                case "getBranches": {
                    const branches = await this.client.getBranches();
                    this.postMessage({ type: "branches", data: branches });
                    break;
                }
                case "compare": {
                    const comparison = await this.client.compare(message.base, message.head);
                    this.postMessage({ type: "comparison", data: comparison });
                    break;
                }
                case "review": {
                    const review = await this.client.review(message.branch, message.base);
                    this.postMessage({ type: "review", data: review });
                    break;
                }
                case "getHistory": {
                    const history = await this.client.getHistory();
                    this.postMessage({ type: "history", data: history });
                    break;
                }
            }
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : "Unknown error";
            this.postMessage({ type: "error", message: msg });
        }
    }
    async handleChat(text) {
        try {
            await this.client.chatStream(text, (event) => {
                this.postMessage({ type: "streamEvent", data: event });
            });
            this.postMessage({ type: "streamDone" });
        }
        catch {
            // Fall back to non-streaming
            const response = await this.client.chat(text);
            this.postMessage({ type: "chatResponse", data: response });
        }
    }
    postMessage(message) {
        this.view?.webview.postMessage(message);
    }
    getHtmlForWebview(webview) {
        const nonce = getNonce();
        const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, "media", "main.js"));
        const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, "media", "main.css"));
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'none';
                   style-src ${webview.cspSource} 'unsafe-inline';
                   script-src 'nonce-${nonce}';">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="${styleUri}" rel="stylesheet">
    <title>OSCAR</title>
</head>
<body>
    <div id="app"></div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
    }
}
exports.OscarViewProvider = OscarViewProvider;
OscarViewProvider.viewType = "oscarSidebar";
function getNonce() {
    let text = "";
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    for (let i = 0; i < 32; i++) {
        text += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return text;
}
//# sourceMappingURL=oscarViewProvider.js.map