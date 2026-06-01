import * as vscode from "vscode";
import { OscarClient } from "./oscarClient";
import { OscarViewProvider } from "./oscarViewProvider";
import { ProviderInfo, ProvidersResponse } from "./types";

function majorMinor(version: string): string {
    const parts = version.split(".");
    return parts.length >= 2 ? `${parts[0]}.${parts[1]}` : version;
}

function formatModelLabel(catalog: ProvidersResponse): string {
    const providerInfo = catalog.providers.find(
        (p) => p.id === catalog.current.provider
    );
    const providerLabel = providerInfo?.label ?? catalog.current.provider;
    return `$(sparkle) ${providerLabel}: ${catalog.current.model}`;
}

async function pickModelFromCatalog(
    catalog: ProvidersResponse
): Promise<void> {
    type PickItem = vscode.QuickPickItem & {
        provider: ProviderInfo;
        modelId: string;
    };

    const items: PickItem[] = [];
    for (const provider of catalog.providers) {
        for (const model of provider.models) {
            const isCurrent =
                provider.id === catalog.current.provider &&
                model.id === catalog.current.model;
            items.push({
                label: `${isCurrent ? "$(check) " : ""}${model.label}`,
                description: `${provider.label} · ${model.id}`,
                detail: model.description,
                provider,
                modelId: model.id,
            });
        }
    }

    const picked = await vscode.window.showQuickPick(items, {
        title: "OSCAR — select LLM provider/model",
        placeHolder: catalog.current.provider
            ? `Currently using ${catalog.current.provider}/${catalog.current.model}`
            : "Choose a provider and model",
        matchOnDescription: true,
        matchOnDetail: true,
    });

    if (!picked) {
        return;
    }

    // We cannot rewrite the backend's .env from inside VS Code, so show the
    // env vars the user needs to set and copy them to the clipboard.
    const lines = [
        `OSCAR_LLM_PROVIDER=${picked.provider.id}`,
        `OSCAR_LLM_MODEL=${picked.modelId}`,
    ];
    if (picked.provider.api_key_env) {
        lines.push(`# ${picked.provider.api_key_env}=...  (required)`);
    }
    if (picked.provider.requires_local_server) {
        lines.push(
            "# Make sure Ollama is running locally (default http://localhost:11434)"
        );
    }
    const envBlock = lines.join("\n");
    await vscode.env.clipboard.writeText(envBlock);
    vscode.window.showInformationMessage(
        `Copied to clipboard. Paste into your .env and restart oscar-server to switch to ${picked.provider.label} (${picked.modelId}).`
    );
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

    // Status bar item showing the active provider/model. Click to open the
    // model picker.
    const modelStatusItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    modelStatusItem.text = "$(sparkle) OSCAR";
    modelStatusItem.tooltip = "OSCAR LLM provider — click to switch";
    modelStatusItem.command = "oscar.selectModel";
    modelStatusItem.show();
    context.subscriptions.push(modelStatusItem);

    let providerCatalog: ProvidersResponse | null = null;
    const refreshProviderStatus = async (): Promise<void> => {
        providerCatalog = await client.getProviders();
        if (providerCatalog) {
            modelStatusItem.text = formatModelLabel(providerCatalog);
            modelStatusItem.tooltip = `OSCAR · ${providerCatalog.current.provider}/${providerCatalog.current.model}\nClick to switch provider/model`;
        } else {
            modelStatusItem.text = "$(sparkle) OSCAR (offline)";
            modelStatusItem.tooltip =
                "OSCAR backend is not reachable. Start it with: oscar-server";
        }
    };

    context.subscriptions.push(
        vscode.commands.registerCommand("oscar.selectModel", async () => {
            if (!providerCatalog) {
                await refreshProviderStatus();
            }
            if (!providerCatalog) {
                vscode.window.showWarningMessage(
                    "OSCAR backend is not reachable. Start it with: oscar-server"
                );
                return;
            }
            await pickModelFromCatalog(providerCatalog);
        })
    );

    // Non-blocking health check + version compatibility warning
    client.healthCheck().then(async (health) => {
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
        await refreshProviderStatus();
    });
}

export function deactivate(): void {
    // subscriptions are auto-disposed via context.subscriptions
}
