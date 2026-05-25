const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const historySidebar = document.getElementById("history-sidebar");
const menuToggle = document.getElementById("menu-toggle");
const sidebar = document.getElementById("sidebar");
const sidebarCloseBtn = document.getElementById("sidebar-close");
const clearRecentsBtn = document.getElementById("clear-recents");

const STORAGE_KEY = "josaa-conversations";
let conversationHistory = [];
let conversations = [];
let currentConvId = null;

// Initialize from localStorage
function loadFromStorage() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
        try {
            conversations = JSON.parse(stored);
            renderSidebarHistory();
        } catch (e) {
            console.error("Failed to load conversations from localStorage", e);
        }
    }
}

// Save to localStorage
function saveToStorage() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
}

// Mobile menu toggle
menuToggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
});

// Close sidebar button (mobile)
if (sidebarCloseBtn) {
    sidebarCloseBtn.addEventListener("click", () => {
        sidebar.classList.remove("open");
    });
}

// Close sidebar when clicking outside on mobile
document.addEventListener("click", (e) => {
    if (window.innerWidth <= 768) {
        if (!sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
            sidebar.classList.remove("open");
        }
    }
});

function autoResizeTextarea() {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
}

chatInput.addEventListener("input", autoResizeTextarea);

function addMessageToUI(text, isUser = true, usePre = false, extraClass = "") {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${isUser ? "user" : "assistant"}${extraClass ? ` ${extraClass}` : ""}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = isUser ? "U" : "J";

    const content = document.createElement("div");
    content.className = "message-content";
    if (usePre) {
        const pre = document.createElement("pre");
        pre.textContent = text;
        content.appendChild(pre);
    } else {
        content.textContent = text;
    }

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function clearGreeting() {
    const greeting = chatMessages.querySelector(".greeting-panel");
    if (greeting) greeting.remove();
}

function typeChars(span, text, speed = 35) {
    return new Promise((resolve) => {
        let i = 0;
        const t = setInterval(() => {
            if (i < text.length) {
                span.textContent += text.charAt(i);
                chatMessages.scrollTop = chatMessages.scrollHeight;
                i += 1;
            } else {
                clearInterval(t);
                resolve();
            }
        }, speed);
    });
}

async function typeSegmentsOnPre(pre, lines, speed = 35, lineDelay = 140) {
    for (const line of lines) {
        for (const seg of line) {
            const span = document.createElement('span');
            if (seg.cls) span.className = seg.cls;
            pre.appendChild(span);
            // type the segment text char-by-char
            // small tweak: treat whitespace at start as part of text
            await typeChars(span, seg.text, speed);
        }
        // append line break
        pre.appendChild(document.createElement('br'));
        await new Promise(r => setTimeout(r, lineDelay));
    }
}

function renderInitialBootSequence() {
    const lines = [
        [ { text: '>', cls: 'tok-prompt' }, { text: ' Initializing ', cls: 'tok-action' }, { text: 'IIT Mandi Gateway', cls: 'tok-variable' }, { text: '...', cls: '' } ],
        [ { text: '>', cls: 'tok-prompt' }, { text: ' Fetching JoSAA seat matrix... ', cls: '' }, { text: ' [SUCCESS]', cls: 'tok-status' } ],
        [ { text: '>', cls: 'tok-prompt' }, { text: ' Loading closing rank datasets... ', cls: '' }, { text: ' [OK]', cls: 'tok-status' } ],
        [ { text: '>', cls: 'tok-prompt' }, { text: ' System ready. Awaiting user input...', cls: '' } ]
    ];

    const messageDiv = document.createElement("div");
        messageDiv.className = "message terminal system";


    const content = document.createElement("div");
    content.className = "message-content";

    const pre = document.createElement("pre");
    pre.className = 'terminal-pre';
    content.appendChild(pre);

    messageDiv.appendChild(content);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // start async typing (don't block)
    typeSegmentsOnPre(pre, lines, 28, 120).catch(console.error);
}

async function sendMessage(text) {
    clearGreeting();
    addMessageToUI(text, true);
    conversationHistory.push({ role: "user", content: text });

    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.disabled = true;

    // Close sidebar on mobile after sending
    if (window.innerWidth <= 768) {
        sidebar.classList.remove("open");
    }

    addMessageToUI("Thinking...", false);

    try {
        const res = await fetch("/app", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: text })
        });

        if (!res.ok) {
            const errorData = await res.json();
            const lastMsg = chatMessages.lastElementChild;
            lastMsg.querySelector(".message-content").textContent = errorData.error || "Failed to fetch reply.";
            return;
        }

        const data = await res.json();
        const reply = data.reply || "No reply returned.";
        conversationHistory.push({ role: "assistant", content: reply });

        const lastMsg = chatMessages.lastElementChild;
        lastMsg.querySelector(".message-content").textContent = reply;

        saveConversation();
    } catch (error) {
        console.error(error);
        const lastMsg = chatMessages.lastElementChild;
        lastMsg.querySelector(".message-content").textContent = "Unable to reach the server.";
    } finally {
        sendBtn.disabled = false;
    }
}

function saveConversation() {
    if (conversationHistory.length > 0) {
        const firstUserMsg = conversationHistory.find(m => m.role === "user");
        if (firstUserMsg) {
            const title = firstUserMsg.content.substring(0, 40) + (firstUserMsg.content.length > 40 ? "..." : "");
            const convId = currentConvId || Date.now();
            
            // Update existing or add new
            const existingIndex = conversations.findIndex(c => c.id === convId);
            if (existingIndex >= 0) {
                conversations[existingIndex] = { id: convId, title, history: [...conversationHistory] };
            } else {
                conversations.unshift({ id: convId, title, history: [...conversationHistory] });
            }
            
            currentConvId = convId;
            saveToStorage();
            renderSidebarHistory();
        }
    }
}

function renderSidebarHistory() {
    historySidebar.innerHTML = "";

    if (conversations.length === 0) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        empty.textContent = "No chat history yet";
        historySidebar.appendChild(empty);
        return;
    }

    conversations.slice(0, 20).forEach(conv => {
        const item = document.createElement("button");
        item.className = "history-item";
        item.textContent = conv.title;
        item.dataset.convId = conv.id;

        if (currentConvId && conv.id === currentConvId) {
            item.classList.add("active");
            item.setAttribute("aria-current", "true");
        }

        item.addEventListener("click", () => loadConversation(conv.id));
        historySidebar.appendChild(item);

    });
}

function loadConversation(convId) {
    const conv = conversations.find(c => c.id === convId);
    if (conv) {
        conversationHistory = [...conv.history];
        currentConvId = convId;
        chatMessages.innerHTML = "";
        conversationHistory.forEach(msg => addMessageToUI(msg.content, msg.role === "user"));

        // Update active state in sidebar
        renderSidebarHistory();

        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            sidebar.classList.remove("open");
        }
    }
}

function startNewChat() {
    conversationHistory = [];
    currentConvId = null;
    chatMessages.innerHTML = '<div class="greeting-panel"><h2>Hello. How can I help you today?</h2></div>';
    renderInitialBootSequence();
    chatInput.value = "";
    chatInput.style.height = "auto";
    
    if (window.innerWidth <= 768) {
        sidebar.classList.remove("open");
    }
}

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (text) {
        sendMessage(text);
    }
});

newChatBtn.addEventListener("click", startNewChat);

// Clear recents
if (clearRecentsBtn) {
    clearRecentsBtn.addEventListener("click", () => {
        if (!conversations.length) return;

        const ok = window.confirm("Clear all chat recents from this device?");
        if (!ok) return;

        conversations = [];
        conversationHistory = [];
        currentConvId = null;
        saveToStorage();
        renderSidebarHistory();
        startNewChat();
    });
}

// Handle window resize for responsive behavior
window.addEventListener("resize", () => {
    if (window.innerWidth > 768) {
        sidebar.classList.remove("open");
    }
});

// Initialize on page load
loadFromStorage();
startNewChat();
