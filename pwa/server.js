const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;

// MIME types
const mimeTypes = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'text/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.webp': 'image/webp'
};

const server = http.createServer((req, res) => {
    // Log requests
    console.log(`${new Date().toLocaleTimeString()} - ${req.method} ${req.url}`);

    // Set CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    // Handle OPTIONS requests
    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    // Only handle GET and HEAD
    if (req.method !== 'GET' && req.method !== 'HEAD') {
        res.writeHead(405, { 'Content-Type': 'text/plain' });
        res.end('Method Not Allowed');
        return;
    }

    // Parse URL
    let pathname = req.url;
    if (pathname === '/') {
        pathname = '/index.html';
    }

    // Security: prevent directory traversal
    if (pathname.includes('..')) {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('Bad Request');
        return;
    }

    const filePath = path.join(__dirname, pathname);

    // Check if file exists
    fs.stat(filePath, (err, stats) => {
        if (err) {
            if (err.code === 'ENOENT') {
                // File not found - try to serve index.html for SPA routing
                const indexPath = path.join(__dirname, 'index.html');
                fs.readFile(indexPath, (err, data) => {
                    if (err) {
                        res.writeHead(404, { 'Content-Type': 'text/html' });
                        res.end('<h1>404 - File Not Found</h1>');
                    } else {
                        res.writeHead(200, {
                            'Content-Type': 'text/html',
                            'Cache-Control': 'no-cache',
                            'Service-Worker-Allowed': '/'
                        });
                        if (req.method === 'GET') {
                            res.end(data);
                        } else {
                            res.end();
                        }
                    }
                });
            } else {
                res.writeHead(500, { 'Content-Type': 'text/plain' });
                res.end('Internal Server Error');
            }
            return;
        }

        // Handle directories
        if (stats.isDirectory()) {
            const indexPath = path.join(filePath, 'index.html');
            fs.readFile(indexPath, (err, data) => {
                if (err) {
                    res.writeHead(403, { 'Content-Type': 'text/plain' });
                    res.end('Forbidden');
                } else {
                    res.writeHead(200, {
                        'Content-Type': 'text/html',
                        'Service-Worker-Allowed': '/'
                    });
                    if (req.method === 'GET') {
                        res.end(data);
                    } else {
                        res.end();
                    }
                }
            });
            return;
        }

        // Read and serve file
        fs.readFile(filePath, (err, data) => {
            if (err) {
                res.writeHead(500, { 'Content-Type': 'text/plain' });
                res.end('Internal Server Error');
                return;
            }

            const ext = path.extname(filePath).toLowerCase();
            const contentType = mimeTypes[ext] || 'application/octet-stream';

            // Set appropriate cache headers
            let cacheControl = 'public, max-age=3600'; // 1 hour default
            if (ext === '.html') {
                cacheControl = 'no-cache'; // HTML should not be cached
            } else if (ext === '.js' || ext === '.css') {
                cacheControl = 'public, max-age=31536000, immutable'; // 1 year for assets
            }

            // Headers for Service Worker
            const headers = {
                'Content-Type': contentType,
                'Content-Length': data.length,
                'Cache-Control': cacheControl,
                'Service-Worker-Allowed': '/'
            };

            res.writeHead(200, headers);
            if (req.method === 'GET') {
                res.end(data);
            } else {
                res.end();
            }
        });
    });
});

server.listen(PORT, () => {
    console.log(`\n╔════════════════════════════════════════╗`);
    console.log(`║   PWA Development Server               ║`);
    console.log(`║   Server running at:                   ║`);
    console.log(`║   http://localhost:${PORT}               ║`);
    console.log(`╚════════════════════════════════════════╝\n`);
    console.log(`📱 Open your browser and navigate to http://localhost:${PORT}`);
    console.log(`🔧 Press Ctrl+C to stop the server\n`);
});

// Handle server errors
server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(`❌ Port ${PORT} is already in use`);
        console.log(`\nTry killing the process or use a different port`);
    } else {
        console.error('Server error:', err);
    }
    process.exit(1);
});

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('\n\n👋 Server shutting down gracefully...');
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});

process.on('SIGINT', () => {
    console.log('\n\n👋 Server shutting down gracefully...');
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});
