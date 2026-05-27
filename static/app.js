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
//voice button
        const startBtn = document.getElementById('voice-btn');
        const micIconPath = startBtn.querySelector('svg path');
        const textbox = document.getElementById('chat-input');

        // 2. SVG path variables for swapping states
        const MIC_ON_PATH = `M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z`;
        const MIC_OFF_PATH = `M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.41 1.41c-.64.43-1.39.67-2.06.74V21h2v-3.32c1.24-.18 2.38-.68 3.31-1.39L19.73 21 21 19.73 4.27 3zM12 16.1c-2.8 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.93L14.3 15.5c-.69.38-1.47.6-2.3.6z`;

        // 3. Keep track of status
        let isListening = false;

        // 4. Set up Web Speech API recognition
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            alert("Speech recognition is not supported in this browser. Try Chrome or Edge.");
        } else {
            const recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'en-US';

            // 5. Handle button clicks to start/stop
            startBtn.addEventListener('click', () => {
                if (!isListening) {
                    recognition.start();
                } else {
                    recognition.stop();
                }
            });

            // 6. Native event triggers
            recognition.onstart = () => {
                isListening = true;
                startBtn.classList.add('listening');
                micIconPath.setAttribute('d', MIC_OFF_PATH); // Switches to mic-slash graphic
            };

            recognition.onend = () => {
                isListening = false;
                startBtn.classList.remove('listening');
                micIconPath.setAttribute('d', MIC_ON_PATH); // Switches back to standard mic graphic
            };

            recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }
                
                // Print streaming speech to the textarea
                textbox.value = finalTranscript + interimTranscript;
            };

            recognition.onerror = (event) => {
                console.error("Speech Recognition Error: ", event.error);
                recognition.stop();
            };
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

// Send message on Enter key (Shift+Enter keeps newline behavior)
chatInput.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;

    // If Shift is held, allow newline
    if (e.shiftKey) return;

    e.preventDefault();

    // Avoid submitting while a message is in-flight
    if (sendBtn && sendBtn.disabled) return;

    const text = chatInput.value.trim();
    if (text) {
        sendMessage(text);
    }
});


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
        pre.innerHTML = text;
        content.appendChild(pre);
    } else {
        content.innerHTML = text;
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
    // const lines = [
    //     [ { text: '>', cls: 'tok-prompt' }, { text: ' Initializing ', cls: 'tok-action' }, { text: 'IIT Mandi Gateway', cls: 'tok-variable' }, { text: '...', cls: '' } ],
    //     [ { text: '>', cls: 'tok-prompt' }, { text: ' Fetching JoSAA seat matrix... ', cls: '' }, { text: ' [SUCCESS]', cls: 'tok-status' } ],
    //     [ { text: '>', cls: 'tok-prompt' }, { text: ' Loading closing rank datasets... ', cls: '' }, { text: ' [OK]', cls: 'tok-status' } ],
    //     [ { text: '>', cls: 'tok-prompt' }, { text: ' System ready. Awaiting user input...', cls: '' } ]
    // ];

    // const messageDiv = document.createElement("div");
    //     messageDiv.className = "message terminal system";


    // const content = document.createElement("div");
    // content.className = "message-content";

    // const pre = document.createElement("pre");
    // pre.className = 'terminal-pre';
    // content.appendChild(pre);

    // messageDiv.appendChild(content);
    // chatMessages.appendChild(messageDiv);
    // chatMessages.scrollTop = chatMessages.scrollHeight;

    // // start async typing (don't block)
    // typeSegmentsOnPre(pre, lines, 28, 120).catch(console.error);
    console.log("JOSAA ASSIST ACTIVE!!!\nThis is JoSAAssist, made by Reman Dey and Aryan Raj");
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
            lastMsg.querySelector(".message-content").innerHTML = errorData.error || "Failed to fetch reply.";
            return;
        }

        const data = await res.json();
        const reply = data.reply || "No reply returned.";
        conversationHistory.push({ role: "assistant", content: reply });

        const lastMsg = chatMessages.lastElementChild;
        lastMsg.querySelector(".message-content").innerHTML = reply;

        saveConversation();
    } catch (error) {
        console.error(error);
        const lastMsg = chatMessages.lastElementChild;
        lastMsg.querySelector(".message-content").innerHTML = "Unable to reach the server.";
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
