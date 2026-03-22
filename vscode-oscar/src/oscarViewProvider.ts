import * as vscode from "vscode";
import { OscarClient } from "./oscarClient";
import { WebviewMessage, ExtensionMessage } from "./types";

export class OscarViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = "oscarSidebar";
    private view?: vscode.WebviewView;

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly client: OscarClient
    ) {}

    resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ): void {
        this.view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [
                vscode.Uri.joinPath(this.extensionUri, "media"),
            ],
        };

        webviewView.webview.html = this.getHtmlForWebview(webviewView.webview);

        webviewView.webview.onDidReceiveMessage((message: WebviewMessage) =>
            this.handleMessage(message)
        );
    }

    private async handleMessage(message: WebviewMessage): Promise<void> {
        this.postMessage({ type: "loading", data: true });

        try {
            switch (message.type) {
                case "chat":
                    await this.handleChat(message.text!);
                    break;

                case "getBranches": {
                    const branches = await this.client.getBranches();
                    this.postMessage({ type: "branches", data: branches });
                    break;
                }

                case "compare": {
                    const comparison = await this.client.compare(
                        message.base!,
                        message.head!
                    );
                    this.postMessage({ type: "comparison", data: comparison });
                    break;
                }

                case "review": {
                    const review = await this.client.review(
                        message.branch!,
                        message.base
                    );
                    this.postMessage({ type: "review", data: review });
                    break;
                }

                case "getHistory": {
                    const history = await this.client.getHistory();
                    this.postMessage({ type: "history", data: history });
                    break;
                }
            }
        } catch (err: unknown) {
            const msg =
                err instanceof Error ? err.message : "Unknown error";
            this.postMessage({ type: "error", message: msg });
        }
    }

    private async handleChat(text: string): Promise<void> {
        try {
            await this.client.chatStream(text, (event) => {
                this.postMessage({ type: "streamEvent", data: event });
            });
            this.postMessage({ type: "streamDone" });
        } catch {
            // Fall back to non-streaming
            const response = await this.client.chat(text);
            this.postMessage({ type: "chatResponse", data: response });
        }
    }

    private postMessage(message: ExtensionMessage): void {
        this.view?.webview.postMessage(message);
    }

    private getHtmlForWebview(webview: vscode.Webview): string {
        const nonce = getNonce();

        const scriptUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this.extensionUri, "media", "main.js")
        );
        const styleUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this.extensionUri, "media", "main.css")
        );

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

function getNonce(): string {
    let text = "";
    const chars =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    for (let i = 0; i < 32; i++) {
        text += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return text;
}
