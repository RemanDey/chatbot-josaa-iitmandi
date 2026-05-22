const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const historySidebar = document.getElementById("history-sidebar");
const menuToggle = document.getElementById("menu-toggle");
const sidebar = document.getElementById("sidebar");

const STORAGE_KEY = "gemini-conversations";
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

function addMessageToUI(text, isUser = true) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${isUser ? "user" : "assistant"}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = isUser ? "U" : "G";

    const content = document.createElement("div");
    content.className = "message-content";
    content.textContent = text;

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function clearGreeting() {
    const greeting = chatMessages.querySelector(".greeting-panel");
    if (greeting) greeting.remove();
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
        empty.style.color = "#666666";
        empty.style.fontSize = "0.85rem";
        empty.style.padding = "12px 16px";
        empty.style.textAlign = "center";
        empty.textContent = "No chat history yet";
        historySidebar.appendChild(empty);
        return;
    }
    
    conversations.slice(0, 20).forEach(conv => {
        const item = document.createElement("button");
        item.className = "history-item";
        item.textContent = conv.title;
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

// Handle window resize for responsive behavior
window.addEventListener("resize", () => {
    if (window.innerWidth > 768) {
        sidebar.classList.remove("open");
    }
});

// Initialize on page load
loadFromStorage();
startNewChat();
