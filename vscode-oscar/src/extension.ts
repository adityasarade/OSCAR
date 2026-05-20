import * as vscode from "vscode";
import { OscarClient } from "./oscarClient";
import { OscarViewProvider } from "./oscarViewProvider";

function majorMinor(version: string): string {
    const parts = version.split(".");
    return parts.length >= 2 ? `${parts[0]}.${parts[1]}` : version;
}

function pickActiveRepoFolder(
    previous?: string | null
): vscode.WorkspaceFolder | undefined {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return undefined;
    }

    // Prefer the folder owning the active editor (multi-root workspaces).
    const active = vscode.window.activeTextEditor?.document.uri;
    if (active && active.scheme === "file") {
        const owning = vscode.workspace.getWorkspaceFolder(active);
        if (owning) {
            return owning;
        }
        // Active file is outside every workspace folder — keep the
        // previous selection if it's still a known folder.
        if (previous) {
            const stillValid = folders.find((f) => f.uri.fsPath === previous);
            if (stillValid) {
                return stillValid;
            }
        }
    }
    return folders[0];
}

export function activate(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration("oscar");
    const serverUrl = config.get<string>(
        "serverUrl",
        "http://127.0.0.1:8420"
    );

    const client = new OscarClient(serverUrl);
    const extVersion: string = context.extension.packageJSON.version;

    const initialFolder = pickActiveRepoFolder(null);
    if (initialFolder) {
        client.setRepoPath(initialFolder.uri.fsPath);
    }

    const provider = new OscarViewProvider(context.extensionUri, client);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            OscarViewProvider.viewType,
            provider
        )
    );

    const applyActiveFolder = (reason: string) => {
        const folder = pickActiveRepoFolder(client.getRepoPath());
        const newPath = folder?.uri.fsPath ?? null;
        if (newPath !== client.getRepoPath()) {
            client.setRepoPath(newPath);
            provider.notifyWorkspaceChange(newPath, reason);
        }
    };

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

    // Re-detect when the user opens/closes folders or switches between them.
    context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(() =>
            applyActiveFolder("workspace folders changed")
        )
    );
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(() =>
            applyActiveFolder("active editor changed")
        )
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
