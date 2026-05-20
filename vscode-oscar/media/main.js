// @ts-nocheck
(function () {
    const vscode = acquireVsCodeApi();

    // DOM references
    let messagesContainer;
    let messageInput;
    let sendBtn;
    let cancelBtn;
    let baseBranchSelect;
    let headBranchSelect;
    let compareBtn;
    let reviewBtn;
    let refreshBranchesBtn;
    let branchStatus;
    let repoLabel;
    let loadingBar;
    let statusDot;

    // Streaming state
    let currentStreamCard = null;
    let currentToolGroup = null;
    let chatInFlight = false;
    let currentRepoPath = "";

    // ── Initialization ───────────────────────────────────────────────

    function init() {
        const app = document.getElementById("app");

        // Header
        const header = el("div", "header");
        const headerLeft = el("div", "header-left");
        const title = el("h2");
        title.textContent = "OSCAR";
        repoLabel = el("div", "repo-label");
        repoLabel.textContent = "(no workspace)";
        repoLabel.title = "No workspace folder";
        headerLeft.append(title, repoLabel);

        statusDot = el("div", "status-dot");
        const clearBtn = el("button", "clear-btn");
        clearBtn.type = "button";
        clearBtn.title = "Clear chat";
        clearBtn.textContent = "Clear";
        clearBtn.addEventListener("click", clearChat);
        const headerRight = el("div", "header-right");
        headerRight.append(clearBtn, statusDot);
        header.append(headerLeft, headerRight);

        // Loading bar
        loadingBar = el("div", "loading-bar hidden");

        // Branch compare section
        const branchSection = el("div", "branch-compare-section");

        const branchHeading = el("div", "branch-heading");
        const branchHeadingText = el("span");
        branchHeadingText.textContent = "Compare branches";
        refreshBranchesBtn = el("button", "icon-btn");
        refreshBranchesBtn.type = "button";
        refreshBranchesBtn.title = "Refresh branch list";
        refreshBranchesBtn.textContent = "↻";
        refreshBranchesBtn.addEventListener("click", function () {
            vscode.postMessage({ type: "refreshBranches" });
            branchStatus.textContent = "Refreshing…";
        });
        branchHeading.append(branchHeadingText, refreshBranchesBtn);

        const baseRow = el("div", "branch-row");
        const baseLabel = el("label", "branch-label");
        baseLabel.textContent = "Base";
        baseBranchSelect = el("select");
        baseBranchSelect.innerHTML = '<option value="">(none)</option>';
        baseRow.append(baseLabel, baseBranchSelect);

        const headRow = el("div", "branch-row");
        const headLabel = el("label", "branch-label");
        headLabel.textContent = "Head";
        headBranchSelect = el("select");
        headBranchSelect.innerHTML = '<option value="">(none)</option>';
        headRow.append(headLabel, headBranchSelect);

        const branchActions = el("div", "branch-actions");
        compareBtn = el("button", "primary-action");
        compareBtn.textContent = "Compare";
        compareBtn.addEventListener("click", compareBranches);
        reviewBtn = el("button", "secondary-action");
        reviewBtn.textContent = "Review";
        reviewBtn.title = "Show the full diff of head vs base";
        reviewBtn.addEventListener("click", reviewBranch);
        branchActions.append(compareBtn, reviewBtn);

        branchStatus = el("div", "branch-status");
        branchStatus.textContent = "Loading branches…";

        branchSection.append(
            branchHeading,
            baseRow,
            headRow,
            branchActions,
            branchStatus
        );

        // Messages area
        messagesContainer = el("div", "messages-container");

        // Welcome message
        const welcome = el("div", "welcome");
        welcome.innerHTML =
            "<h3>Welcome to OSCAR</h3>" +
            "<p>GitHub-specialized AI coding assistant.<br>" +
            "Ask about branches, diffs, PRs, or run commands.</p>";
        messagesContainer.appendChild(welcome);

        // Input area
        const inputContainer = el("div", "input-container");
        messageInput = document.createElement("textarea");
        messageInput.rows = 1;
        messageInput.placeholder = "Ask OSCAR something...";
        messageInput.addEventListener("keydown", onInputKeydown);
        messageInput.addEventListener("input", autoResize);
        sendBtn = el("button");
        sendBtn.textContent = "Send";
        sendBtn.addEventListener("click", sendMessage);
        cancelBtn = el("button", "cancel-btn hidden");
        cancelBtn.textContent = "Stop";
        cancelBtn.addEventListener("click", cancelChat);
        inputContainer.append(messageInput, sendBtn, cancelBtn);

        app.append(header, loadingBar, branchSection, messagesContainer, inputContainer);

        // Request branches on load
        vscode.postMessage({ type: "getBranches" });
    }

    // ── Sending messages ─────────────────────────────────────────────

    function sendMessage() {
        const text = messageInput.value.trim();
        if (!text || chatInFlight) return;

        chatInFlight = true;
        addMessageCard("user", text);
        vscode.postMessage({ type: "chat", text: text });
        messageInput.value = "";
        messageInput.style.height = "auto";
    }

    function cancelChat() {
        if (!chatInFlight) return;
        vscode.postMessage({ type: "cancel" });
    }

    function compareBranches() {
        const base = baseBranchSelect.value;
        const head = headBranchSelect.value;
        if (!base || !head) {
            branchStatus.textContent = "Select base and head branches first.";
            branchStatus.classList.add("warn");
            return;
        }
        branchStatus.classList.remove("warn");
        branchStatus.textContent = "Comparing " + base + " → " + head + "…";
        addMessageCard("user", "Compare " + base + " → " + head);
        vscode.postMessage({ type: "compare", base: base, head: head });
    }

    function reviewBranch() {
        const base = baseBranchSelect.value;
        const head = headBranchSelect.value;
        if (!head) {
            branchStatus.textContent = "Select a head branch to review.";
            branchStatus.classList.add("warn");
            return;
        }
        branchStatus.classList.remove("warn");
        branchStatus.textContent = "Reviewing " + head + "…";
        addMessageCard(
            "user",
            "Review " + head + (base ? " vs " + base : "")
        );
        vscode.postMessage({ type: "review", branch: head, base: base || undefined });
    }

    function onInputKeydown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    function autoResize() {
        messageInput.style.height = "auto";
        messageInput.style.height =
            Math.min(messageInput.scrollHeight, 120) + "px";
    }

    // ── Message rendering ────────────────────────────────────────────

    function addMessageCard(role, content) {
        removeWelcome();
        const card = el("div", "message-card " + role);
        card.innerHTML = renderMarkdown(content);
        messagesContainer.appendChild(card);
        scrollToBottom();
        return card;
    }

    function addDiffCard(title, body) {
        removeWelcome();
        const card = el("div", "message-card diff-card");
        const heading = el("div", "diff-title");
        heading.textContent = title;
        const pre = el("pre", "diff-pre");
        const code = el("code");
        code.textContent = body;
        pre.appendChild(code);
        card.append(heading, pre);
        messagesContainer.appendChild(card);
        scrollToBottom();
        return card;
    }

    function removeWelcome() {
        const w = messagesContainer.querySelector(".welcome");
        if (w) w.remove();
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // ── Minimal markdown ─────────────────────────────────────────────

    function renderMarkdown(text) {
        // Escape HTML
        let html = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Code blocks: ```...```
        html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, function (_m, _lang, code) {
            return "<pre><code>" + code.trim() + "</code></pre>";
        });

        // Inline code
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

        // Line breaks (outside pre)
        html = html.replace(/\n/g, "<br>");

        return html;
    }

    // ── Streaming handlers ───────────────────────────────────────────

    function handleStreamEvent(event) {
        switch (event.type) {
            case "thinking":
            case "step":
                ensureToolGroup();
                addToolStep("thinking", event.data || "Thinking…");
                break;

            case "tool_call": {
                ensureToolGroup();
                const label = event.tool_name || "tool";
                const args = typeof event.data === "string" ? event.data : "";
                addToolStep("tool_call", label, args, true);
                break;
            }

            case "tool_result": {
                const ok = event.ok !== false;
                const snippet = typeof event.data === "string" ? event.data : "";
                markLastStepDone(ok, snippet);
                break;
            }

            case "confirm":
                addConfirmCard(event.data);
                break;

            case "response":
                if (!currentStreamCard) {
                    currentStreamCard = addMessageCard("assistant", "");
                }
                currentStreamCard.innerHTML += renderMarkdown(event.data);
                scrollToBottom();
                break;

            case "error":
                addMessageCard("error", event.data);
                break;

            case "cancelled":
                addMessageCard("error", "Cancelled by user.");
                finalizeStream();
                break;

            case "done":
                finalizeStream();
                break;
        }
    }

    function addConfirmCard(payload) {
        if (!payload || !payload.request_id) return;
        removeWelcome();
        const card = el("div", "message-card confirm risk-" + (payload.risk || "medium"));

        const title = el("div", "confirm-title");
        title.textContent = "Approve " + (payload.risk || "medium") + " action?";

        const body = el("div", "confirm-body");
        body.textContent = (payload.tool_name || "tool") + "(" + (payload.args_summary || "") + ")";

        const actions = el("div", "confirm-actions");
        const approveBtn = el("button", "confirm-approve");
        approveBtn.textContent = "Approve";
        const rejectBtn = el("button", "confirm-reject");
        rejectBtn.textContent = "Reject";

        function disableButtons() {
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
        }

        approveBtn.addEventListener("click", function () {
            disableButtons();
            approveBtn.textContent = "Approved";
            vscode.postMessage({
                type: "confirmResponse",
                request_id: payload.request_id,
                approved: true,
            });
        });
        rejectBtn.addEventListener("click", function () {
            disableButtons();
            rejectBtn.textContent = "Rejected";
            vscode.postMessage({
                type: "confirmResponse",
                request_id: payload.request_id,
                approved: false,
            });
        });

        actions.append(approveBtn, rejectBtn);
        card.append(title, body, actions);
        messagesContainer.appendChild(card);
        scrollToBottom();
    }

    function ensureToolGroup() {
        if (!currentToolGroup) {
            removeWelcome();
            currentToolGroup = el("div", "tool-group");
            const heading = el("div", "tool-group-heading");
            heading.textContent = "Working…";
            currentToolGroup.append(heading);
            messagesContainer.appendChild(currentToolGroup);
            scrollToBottom();
        }
    }

    function addToolStep(kind, label, args, inProgress) {
        const item = el("div", "tool-step " + kind);
        const icon = el("span", inProgress ? "spinner" : "checkmark");
        const main = el("div", "tool-step-main");
        const labelEl = el("span", "tool-step-label");
        labelEl.textContent = label;
        main.append(labelEl);
        if (args) {
            const argsEl = el("span", "tool-step-args");
            argsEl.textContent = args;
            main.append(argsEl);
        }
        item.append(icon, main);
        currentToolGroup.appendChild(item);
        scrollToBottom();
    }

    function markLastStepDone(ok, snippet) {
        if (!currentToolGroup) return;
        const items = currentToolGroup.querySelectorAll(".tool-step");
        const last = items[items.length - 1];
        if (!last) return;
        const icon = last.querySelector(".spinner");
        if (icon) {
            icon.className = ok ? "checkmark" : "cross";
        }
        if (!ok) {
            last.classList.add("error");
        }
        if (snippet) {
            const main = last.querySelector(".tool-step-main");
            const result = el("div", "tool-step-result");
            result.textContent = snippet;
            main.append(result);
        }
    }

    function finalizeStream() {
        if (currentToolGroup) {
            // Mark all remaining spinners as done
            currentToolGroup.querySelectorAll(".spinner").forEach(function (s) {
                s.className = "checkmark";
            });
        }
        currentStreamCard = null;
        currentToolGroup = null;
        chatInFlight = false;
        setLoading(false);
    }

    // ── Branch handling ──────────────────────────────────────────────

    function handleBranches(data) {
        if (!data) return;

        if (data.error) {
            branchStatus.textContent = data.error;
            branchStatus.classList.add("warn");
        } else {
            branchStatus.classList.remove("warn");
        }

        const branches = Array.isArray(data.branches) ? data.branches : [];

        [baseBranchSelect, headBranchSelect].forEach(function (select) {
            const previous = select.value;
            select.innerHTML = '<option value="">(none)</option>';
            branches.forEach(function (branch) {
                const opt = document.createElement("option");
                opt.value = branch;
                opt.textContent = branch;
                if (branch === data.current) {
                    opt.textContent += " (current)";
                }
                select.appendChild(opt);
            });
            // Restore previous selection if it's still valid
            if (previous && branches.indexOf(previous) !== -1) {
                select.value = previous;
            }
        });

        // Default base to main/master if nothing else picked
        if (!baseBranchSelect.value) {
            const mainBranch = branches.find(function (b) {
                return b === "main" || b === "master";
            });
            if (mainBranch) baseBranchSelect.value = mainBranch;
        }
        // Default head to current
        if (!headBranchSelect.value && data.current) {
            headBranchSelect.value = data.current;
        }

        if (branches.length === 0 && !data.error) {
            branchStatus.textContent = currentRepoPath
                ? "No branches found in " + shortPath(currentRepoPath)
                : "No workspace folder open.";
        } else if (!data.error) {
            const count = branches.length;
            branchStatus.textContent =
                count + " branch" + (count === 1 ? "" : "es") + " loaded.";
        }
    }

    // ── Loading state ────────────────────────────────────────────────

    function setLoading(show) {
        if (show) {
            loadingBar.classList.remove("hidden");
            sendBtn.disabled = true;
            cancelBtn.classList.remove("hidden");
        } else {
            loadingBar.classList.add("hidden");
            sendBtn.disabled = false;
            cancelBtn.classList.add("hidden");
        }
    }

    function shortPath(path) {
        if (!path) return "";
        const parts = path.split(/[\\/]/);
        return parts.slice(-2).join("/");
    }

    // ── History restore ──────────────────────────────────────────────

    function restoreHistory(entries) {
        if (!entries || !entries.length) return;
        removeWelcome();
        entries.forEach(function (entry) {
            addMessageCard(entry.role, entry.content);
        });
    }

    function setWorkspace(info) {
        currentRepoPath = info && info.repoPath ? info.repoPath : "";
        if (currentRepoPath) {
            repoLabel.textContent = shortPath(currentRepoPath);
            repoLabel.title = currentRepoPath;
        } else {
            repoLabel.textContent = "(no workspace)";
            repoLabel.title = "No workspace folder";
        }
    }

    // ── Message listener ─────────────────────────────────────────────

    window.addEventListener("message", function (event) {
        var msg = event.data;
        switch (msg.type) {
            case "chatResponse":
                setLoading(false);
                addMessageCard("assistant", msg.data.response);
                break;

            case "streamEvent":
                handleStreamEvent(msg.data);
                break;

            case "streamDone":
                finalizeStream();
                break;

            case "branches":
                handleBranches(msg.data);
                statusDot.classList.add("connected");
                break;

            case "comparison": {
                setLoading(false);
                const data = msg.data || {};
                if (data.success && data.output) {
                    addDiffCard("Branch comparison", data.output);
                } else {
                    addMessageCard("error", data.error || data.output || "Compare failed");
                }
                branchStatus.textContent = "Ready.";
                branchStatus.classList.remove("warn");
                break;
            }

            case "review": {
                setLoading(false);
                const data = msg.data || {};
                if (data.success && data.output) {
                    addDiffCard("Branch review", data.output);
                } else {
                    addMessageCard("error", data.error || data.output || "Review failed");
                }
                branchStatus.textContent = "Ready.";
                branchStatus.classList.remove("warn");
                break;
            }

            case "history":
                restoreHistory(msg.data);
                break;

            case "error":
                setLoading(false);
                addMessageCard("error", msg.message || "Something went wrong");
                break;

            case "loading":
                setLoading(!!msg.data);
                break;

            case "workspaceInfo":
                setWorkspace(msg.data);
                if (msg.data && msg.data.reason) {
                    // A workspace change triggers a fresh branch fetch.
                    branchStatus.textContent = "Workspace changed — reloading branches…";
                }
                break;
        }
    });

    // ── Helpers ──────────────────────────────────────────────────────

    function el(tag, className) {
        var e = document.createElement(tag);
        if (className) e.className = className;
        return e;
    }

    function clearChat() {
        var cards = messagesContainer.querySelectorAll(".message-card, .tool-group");
        cards.forEach(function (card) { card.remove(); });
        currentToolGroup = null;
        currentStreamCard = null;
        vscode.setState({ messages: [] });
        var welcome = el("div", "welcome");
        welcome.innerHTML =
            "<h3>Welcome to OSCAR</h3>" +
            "<p>GitHub-specialized AI coding assistant.<br>" +
            "Ask about branches, diffs, PRs, or run commands.</p>";
        var existing = messagesContainer.querySelector(".welcome");
        if (!existing) messagesContainer.appendChild(welcome);
    }

    // ── State persistence (survives panel hide/show) ────────────────

    function saveState() {
        var cards = messagesContainer.querySelectorAll(".message-card");
        var messages = [];
        cards.forEach(function (card) {
            var role = card.classList.contains("user") ? "user" :
                       card.classList.contains("error") ? "error" :
                       card.classList.contains("diff-card") ? "diff" : "assistant";
            messages.push({ role: role, html: card.innerHTML });
        });
        vscode.setState({ messages: messages });
    }

    function restoreState() {
        var state = vscode.getState();
        if (state && state.messages && state.messages.length > 0) {
            removeWelcome();
            state.messages.forEach(function (m) {
                var cls = m.role === "diff" ? "message-card diff-card" : "message-card " + m.role;
                var card = el("div", cls);
                card.innerHTML = m.html;
                messagesContainer.appendChild(card);
            });
            scrollToBottom();
        }
    }

    // Save state after every message
    var _origAddMessageCard = addMessageCard;
    addMessageCard = function (role, content) {
        var card = _origAddMessageCard(role, content);
        saveState();
        return card;
    };
    var _origAddDiffCard = addDiffCard;
    addDiffCard = function (title, body) {
        var card = _origAddDiffCard(title, body);
        saveState();
        return card;
    };

    // Boot
    init();
    restoreState();
})();
