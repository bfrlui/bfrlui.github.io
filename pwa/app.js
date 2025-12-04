// Application State
let counterValue = localStorage.getItem('counter') ? parseInt(localStorage.getItem('counter')) : 0;
let notes = JSON.parse(localStorage.getItem('notes')) || [];

// Register Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/pwa/service-worker.js', { scope: '/pwa/' })
            .then(registration => {
                console.log('Service Worker registered successfully:', registration);
            })
            .catch(error => {
                console.log('Service Worker registration failed:', error);
            });
    });
}

// Handle PWA Install Prompt
let deferredPrompt;
const installBtn = document.getElementById('install-btn');

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    installBtn.style.display = 'block';
});

installBtn.addEventListener('click', async () => {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        console.log(`User response to the install prompt: ${outcome}`);
        deferredPrompt = null;
        installBtn.style.display = 'none';
    }
});

window.addEventListener('appinstalled', () => {
    console.log('PWA was installed');
    deferredPrompt = null;
});

// Online/Offline Status
function updateOnlineStatus() {
    const statusElement = document.getElementById('status');
    if (navigator.onLine) {
        statusElement.textContent = '🟢 You are online';
        statusElement.classList.add('online');
        statusElement.classList.remove('offline');
    } else {
        statusElement.textContent = '🔴 You are offline - but the app still works!';
        statusElement.classList.add('offline');
        statusElement.classList.remove('online');
    }
}

window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
document.addEventListener('DOMContentLoaded', updateOnlineStatus);

// Counter Functionality
function updateCounterDisplay() {
    document.getElementById('counter-value').textContent = counterValue;
    localStorage.setItem('counter', counterValue);
}

document.getElementById('increment-btn').addEventListener('click', () => {
    counterValue++;
    updateCounterDisplay();
});

document.getElementById('decrement-btn').addEventListener('click', () => {
    counterValue--;
    updateCounterDisplay();
});

document.getElementById('reset-btn').addEventListener('click', () => {
    counterValue = 0;
    updateCounterDisplay();
});

// Notes Functionality
function renderNotes() {
    const notesList = document.getElementById('notes-list');
    notesList.innerHTML = '';
    
    notes.forEach((note, index) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${escapeHtml(note)}</span>
            <button data-index="${index}">Delete</button>
        `;
        li.querySelector('button').addEventListener('click', () => {
            notes.splice(index, 1);
            saveNotes();
            renderNotes();
        });
        notesList.appendChild(li);
    });
}

function saveNotes() {
    localStorage.setItem('notes', JSON.stringify(notes));
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

document.getElementById('add-note-btn').addEventListener('click', addNote);
document.getElementById('note-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        addNote();
    }
});

function addNote() {
    const input = document.getElementById('note-input');
    const noteText = input.value.trim();
    
    if (noteText === '') {
        alert('Please enter a note!');
        return;
    }
    
    notes.push(noteText);
    saveNotes();
    input.value = '';
    renderNotes();
}

// Initialize
updateCounterDisplay();
renderNotes();

// Periodic background sync (if supported)
if ('serviceWorker' in navigator && 'SyncManager' in window) {
    window.addEventListener('load', async () => {
        try {
            const registration = await navigator.serviceWorker.ready;
            // Example: Register a background sync tag
            await registration.sync.register('sync-notes');
            console.log('Background sync registered');
        } catch (error) {
            console.log('Background sync not supported:', error);
        }
    });
}

// Notification API
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

// Request notification permission when app loads
window.addEventListener('load', requestNotificationPermission);

console.log('App initialized successfully!');
