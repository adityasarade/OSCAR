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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const oscarClient_1 = require("./oscarClient");
const oscarViewProvider_1 = require("./oscarViewProvider");
function activate(context) {
    const config = vscode.workspace.getConfiguration("oscar");
    const serverUrl = config.get("serverUrl", "http://127.0.0.1:8420");
    const client = new oscarClient_1.OscarClient(serverUrl);
    const provider = new oscarViewProvider_1.OscarViewProvider(context.extensionUri, client);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(oscarViewProvider_1.OscarViewProvider.viewType, provider));
    // Live-update server URL when settings change
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration("oscar.serverUrl")) {
            const newUrl = vscode.workspace
                .getConfiguration("oscar")
                .get("serverUrl", "http://127.0.0.1:8420");
            client.updateBaseUrl(newUrl);
        }
    }));
    // Non-blocking health check
    client.healthCheck().then((healthy) => {
        if (!healthy) {
            vscode.window.showWarningMessage("OSCAR server is not running. Start it with: oscar-server");
        }
    });
}
function deactivate() {
    // subscriptions are auto-disposed via context.subscriptions
}
//# sourceMappingURL=extension.js.map