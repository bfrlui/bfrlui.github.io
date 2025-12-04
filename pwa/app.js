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

// Parse and handle notification trigger in note content
function parseNotificationTrigger(noteText) {
    // Match pattern: "notify X" where X is a number (delay in seconds)
    // Example: "notify 3" or "Remember to call notify 5"
    const notifyPattern = /notify\s+(\d+)/i;
    const match = noteText.match(notifyPattern);
    
    if (match) {
        const delaySeconds = parseInt(match[1], 10);
        return {
            hasNotification: true,
            delaySeconds: delaySeconds,
            cleanedText: noteText // Keep original text in note storage
        };
    }
    
    return {
        hasNotification: false,
        delaySeconds: 0,
        cleanedText: noteText
    };
}

// Send notification with scheduled delay
function sendScheduledNotification(noteText, delaySeconds) {
    // Check if notifications are supported
    if (!('Notification' in window)) {
        console.log('Notifications not supported');
        return;
    }
    
    // Check if permission is granted
    if (Notification.permission !== 'granted') {
        console.log('Notification permission not granted');
        return;
    }
    
    // Schedule notification after delay
    setTimeout(() => {
        // Try to send notification via Service Worker first (better for PWAs)
        if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({
                type: 'SHOW_NOTIFICATION',
                title: 'PWA Notification',
                options: {
                    body: noteText,
                    icon: '/pwa/images/icon-192x192.png',
                    badge: '/pwa/images/icon-192x192.png',
                    tag: 'pwa-note-notification',
                    requireInteraction: true
                }
            });
            console.log('Notification sent via Service Worker for note: ' + noteText);
        } else {
            // Fallback to direct notification API for browser
            try {
                const notification = new Notification('PWA Notification', {
                    body: noteText,
                    icon: '/pwa/images/icon-192x192.png',
                    badge: '/pwa/images/icon-192x192.png',
                    tag: 'pwa-note-notification',
                    requireInteraction: true
                });
                
                // Close notification after 10 seconds if user hasn't interacted
                const closeTimeout = setTimeout(() => {
                    notification.close();
                }, 10000);
                
                // Clear timeout if user clicks notification
                notification.addEventListener('click', () => {
                    clearTimeout(closeTimeout);
                    notification.close();
                });
                
                console.log('Notification sent via Notification API for note: ' + noteText);
            } catch (error) {
                console.error('Error sending notification:', error);
            }
        }
    }, delaySeconds * 1000);
}

function addNote() {
    const input = document.getElementById('note-input');
    const noteText = input.value.trim();
    
    if (noteText === '') {
        alert('Please enter a note!');
        return;
    }
    
    // Parse notification trigger
    const notificationInfo = parseNotificationTrigger(noteText);
    
    // Add note to storage
    notes.push(notificationInfo.cleanedText);
    saveNotes();
    input.value = '';
    renderNotes();
    
    // Send scheduled notification if triggered
    if (notificationInfo.hasNotification) {
        sendScheduledNotification(
            notificationInfo.cleanedText,
            notificationInfo.delaySeconds
        );
        
        // Show feedback to user
        const feedback = document.createElement('div');
        feedback.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 15px 20px;
            border-radius: 4px;
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
        `;
        feedback.textContent = `🔔 Notification scheduled for ${notificationInfo.delaySeconds}s`;
        document.body.appendChild(feedback);
        
        // Remove feedback after 3 seconds
        setTimeout(() => {
            feedback.remove();
        }, 3000);
    }
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
    if ('Notification' in window) {
        if (Notification.permission === 'default') {
            Notification.requestPermission().then(permission => {
                console.log('Notification permission:', permission);
                if (permission === 'granted') {
                    console.log('Notifications enabled for this PWA');
                }
            });
        } else if (Notification.permission === 'granted') {
            console.log('Notifications already enabled');
        } else {
            console.log('Notifications denied by user');
        }
    }
}

// Request notification permission when Service Worker is ready
if ('serviceWorker' in navigator) {
    window.addEventListener('load', async () => {
        try {
            const registration = await navigator.serviceWorker.ready;
            console.log('Service Worker ready for notifications');
            requestNotificationPermission();
        } catch (error) {
            console.log('Service Worker not ready:', error);
            // Fallback: request permission anyway
            requestNotificationPermission();
        }
    });
} else {
    // Fallback for browsers without service worker
    window.addEventListener('load', requestNotificationPermission);
}

console.log('App initialized successfully!');
