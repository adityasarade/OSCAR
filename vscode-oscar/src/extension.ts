import * as vscode from "vscode";
import { OscarClient } from "./oscarClient";
import { OscarViewProvider } from "./oscarViewProvider";

function majorMinor(version: string): string {
    const parts = version.split(".");
    return parts.length >= 2 ? `${parts[0]}.${parts[1]}` : version;
}

export function activate(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration("oscar");
    const serverUrl = config.get<string>(
        "serverUrl",
        "http://127.0.0.1:8420"
    );

    const client = new OscarClient(serverUrl);
    const extVersion: string = context.extension.packageJSON.version;

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

    // Non-blocking health check + version compatibility warning
    client.healthCheck().then((health) => {
        if (!health || health.status !== "ok") {
            vscode.window.showWarningMessage(
                "OSCAR server is not running. Start it with: oscar-server"
            );
            return;
        }
        const backendVersion = health.version;
        if (backendVersion && majorMinor(backendVersion) !== majorMinor(extVersion)) {
            vscode.window.showWarningMessage(
                `OSCAR version mismatch: extension ${extVersion} vs backend ${backendVersion}. Some features may not work.`
            );
        }
    });
}

export function deactivate(): void {
    // subscriptions are auto-disposed via context.subscriptions
}
