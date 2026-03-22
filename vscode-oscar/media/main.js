// @ts-nocheck
(function () {
    const vscode = acquireVsCodeApi();

    // DOM references
    let messagesContainer;
    let messageInput;
    let sendBtn;
    let baseBranchSelect;
    let headBranchSelect;
    let loadingBar;
    let statusDot;

    // Streaming state
    let currentStreamCard = null;
    let currentStepProgress = null;

    // ── Initialization ───────────────────────────────────────────────

    function init() {
        const app = document.getElementById("app");

        // Header
        const header = el("div", "header");
        const title = el("h2");
        title.textContent = "OSCAR";
        statusDot = el("div", "status-dot");
        header.append(title, statusDot);

        // Loading bar
        loadingBar = el("div", "loading-bar hidden");

        // Branch compare section
        const branchSection = el("div", "branch-compare-section");
        baseBranchSelect = el("select");
        baseBranchSelect.innerHTML = '<option value="">base branch...</option>';
        headBranchSelect = el("select");
        headBranchSelect.innerHTML = '<option value="">head branch...</option>';
        const compareBtn = el("button");
        compareBtn.textContent = "Compare";
        compareBtn.addEventListener("click", compareBranches);
        branchSection.append(baseBranchSelect, headBranchSelect, compareBtn);

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
        inputContainer.append(messageInput, sendBtn);

        app.append(header, loadingBar, branchSection, messagesContainer, inputContainer);

        // Request branches on load
        vscode.postMessage({ type: "getBranches" });
    }

    // ── Sending messages ─────────────────────────────────────────────

    function sendMessage() {
        const text = messageInput.value.trim();
        if (!text) return;

        addMessageCard("user", text);
        vscode.postMessage({ type: "chat", text: text });
        messageInput.value = "";
        messageInput.style.height = "auto";
    }

    function compareBranches() {
        const base = baseBranchSelect.value;
        const head = headBranchSelect.value;
        if (!base || !head) return;

        addMessageCard("user", "Compare " + base + " → " + head);
        vscode.postMessage({ type: "compare", base: base, head: head });
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
                ensureStepProgress();
                addStep(event.data, true);
                break;

            case "tool_call":
                ensureStepProgress();
                addStep("Calling " + (event.tool_name || "tool") + "...", true);
                break;

            case "tool_result":
                markLastStepDone();
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

            case "done":
                finalizeStream();
                break;
        }
    }

    function ensureStepProgress() {
        if (!currentStepProgress) {
            removeWelcome();
            currentStepProgress = el("div", "step-progress");
            messagesContainer.appendChild(currentStepProgress);
            scrollToBottom();
        }
    }

    function addStep(label, inProgress) {
        const item = el("div", "step-item");
        const icon = el("span", inProgress ? "spinner" : "checkmark");
        const text = el("span");
        text.textContent = label;
        item.append(icon, text);
        currentStepProgress.appendChild(item);
        scrollToBottom();
    }

    function markLastStepDone() {
        if (!currentStepProgress) return;
        const items = currentStepProgress.querySelectorAll(".step-item");
        const last = items[items.length - 1];
        if (last) {
            const icon = last.querySelector(".spinner");
            if (icon) {
                icon.className = "checkmark";
            }
        }
    }

    function finalizeStream() {
        if (currentStepProgress) {
            // Mark all remaining spinners as done
            currentStepProgress.querySelectorAll(".spinner").forEach(function (s) {
                s.className = "checkmark";
            });
        }
        currentStreamCard = null;
        currentStepProgress = null;
        setLoading(false);
    }

    // ── Branch handling ──────────────────────────────────────────────

    function handleBranches(data) {
        if (!data || !data.branches) return;

        [baseBranchSelect, headBranchSelect].forEach(function (select) {
            // Keep the placeholder option
            select.innerHTML = '<option value="">select branch...</option>';
            data.branches.forEach(function (branch) {
                const opt = document.createElement("option");
                opt.value = branch;
                opt.textContent = branch;
                if (branch === data.current) {
                    opt.textContent += " (current)";
                }
                select.appendChild(opt);
            });
        });

        // Default base to main/master if available
        var mainBranch = data.branches.find(function (b) {
            return b === "main" || b === "master";
        });
        if (mainBranch) baseBranchSelect.value = mainBranch;
        if (data.current) headBranchSelect.value = data.current;
    }

    // ── Loading state ────────────────────────────────────────────────

    function setLoading(show) {
        if (show) {
            loadingBar.classList.remove("hidden");
            sendBtn.disabled = true;
        } else {
            loadingBar.classList.add("hidden");
            sendBtn.disabled = false;
        }
    }

    // ── History restore ──────────────────────────────────────────────

    function restoreHistory(entries) {
        if (!entries || !entries.length) return;
        removeWelcome();
        entries.forEach(function (entry) {
            addMessageCard(entry.role, entry.content);
        });
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

            case "comparison":
                setLoading(false);
                addMessageCard("assistant", msg.data.summary || JSON.stringify(msg.data));
                break;

            case "review":
                setLoading(false);
                addMessageCard("assistant", msg.data.summary || JSON.stringify(msg.data));
                break;

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
        }
    });

    // ── Helpers ──────────────────────────────────────────────────────

    function el(tag, className) {
        var e = document.createElement(tag);
        if (className) e.className = className;
        return e;
    }

    // Boot
    init();
})();
