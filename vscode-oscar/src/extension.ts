import * as vscode from "vscode";
import { OscarClient } from "./oscarClient";
import { OscarViewProvider } from "./oscarViewProvider";

export function activate(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration("oscar");
    const serverUrl = config.get<string>(
        "serverUrl",
        "http://127.0.0.1:8420"
    );

    const client = new OscarClient(serverUrl);

    const provider = new OscarViewProvider(context.extensionUri, client);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            OscarViewProvider.viewType,
            provider
        )
    );

    // Live-update server URL when settings change
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration("oscar.serverUrl")) {
                const newUrl = vscode.workspace
                    .getConfiguration("oscar")
                    .get<string>("serverUrl", "http://127.0.0.1:8420");
                client.updateBaseUrl(newUrl);
            }
        })
    );

    // Non-blocking health check
    client.healthCheck().then((healthy) => {
        if (!healthy) {
            vscode.window.showWarningMessage(
                "OSCAR server is not running. Start it with: oscar-server"
            );
        }
    });
}

export function deactivate(): void {
    // subscriptions are auto-disposed via context.subscriptions
}
