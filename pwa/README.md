# Progressive Web App (PWA)

A modern, feature-rich Progressive Web App built with vanilla HTML, CSS, and JavaScript.

## 🌟 Features

- **📱 Installable**: Add to home screen like a native app
- **🔌 Offline Support**: Works seamlessly without internet connection
- **⚡ Fast Loading**: Optimized caching with service workers
- **💾 Local Storage**: Data persists across sessions
- **🎯 Responsive Design**: Works on all device sizes
- **🔔 Notifications**: Push notification support
- **📊 Interactive Features**: Counter and notes application
- **🔐 Secure**: Served over HTTPS (localhost for dev)

## 📋 Project Structure

```
pwa/
├── index.html              # Main application page
├── styles.css              # Styling and responsive design
├── app.js                  # Application logic
├── service-worker.js       # Offline support and caching
├── manifest.json           # PWA configuration
├── server.js               # Development server (Node.js)
├── server-page.html        # Server information page
├── images/                 # App icons (create these)
│   ├── icon-192x192.png    # Icon for home screen
│   ├── icon-512x512.png    # Icon for splash screen
│   └── apple-touch-icon.png # iOS app icon
└── README.md               # This file
```

## 🚀 Quick Start

### Prerequisites
- Node.js and npm installed on your machine
- Modern web browser (Chrome, Firefox, Edge, Safari)

### Installation

1. **Navigate to the project directory:**
   ```bash
   cd pwa
   ```

2. **Install dependencies (if any):**
   ```bash
   npm install
   ```

3. **Start the development server:**
   ```bash
   node server.js
   ```

4. **Open your browser:**
   - Navigate to `http://localhost:3000`
   - You should see the PWA welcome page

### 5. **Install the App:**
   - Look for the "Install App" button
   - Click to install on your device
   - Or use your browser's menu: Chrome → "Install app"

## 📱 Features Guide

### Online/Offline Status
- The app automatically detects your connection status
- Works fully offline with cached content and local storage

### Counter
- Increment/decrement the counter
- Data persists in local storage
- Works offline

### Notes
- Add notes with the text input
- Notes are saved to local storage
- Delete notes individually
- Data syncs across tabs/windows

## 🔧 Customization

### Update App Name
Edit `manifest.json`:
```json
{
  "name": "My App Name",
  "short_name": "App"
}
```

### Change Theme Colors
Edit `manifest.json` and `styles.css`:
```javascript
--primary-color: #2196F3;     // Blue
--secondary-color: #FF9800;   // Orange
--success-color: #4CAF50;     // Green
```

### Add Icons
Replace the placeholder icons in the `images/` directory:
- `icon-192x192.png` - 192x192 pixels
- `icon-512x512.png` - 512x512 pixels
- `apple-touch-icon.png` - 180x180 pixels (iOS)

Icons should be PNG format with transparency.

## 🛠️ Development

### Using Chrome DevTools

1. **Test Offline Mode:**
   - Open DevTools (F12)
   - Go to Network tab
   - Check "Offline"

2. **View Service Worker:**
   - Open DevTools → Application tab
   - Check "Service Workers"

3. **Check Cache Storage:**
   - DevTools → Application → Cache Storage
   - See what files are cached

4. **Simulate Slow Network:**
   - Network tab → Throttling dropdown
   - Select "Slow 3G" or custom

### Clearing Cache

To force users to get a new version:
1. Update `CACHE_NAME` in `service-worker.js`
2. Change version: `'pwa-cache-v2'`
3. Old caches will be deleted on next load

## 📦 Building for Production

### Using a Hosting Service

#### Vercel
```bash
npm i -g vercel
vercel
```

#### Netlify
```bash
npm i -g netlify-cli
netlify deploy --prod --dir .
```

#### Firebase Hosting
```bash
npm i -g firebase-tools
firebase init hosting
firebase deploy
```

### Important for Production

1. **HTTPS Required** - All PWAs must use HTTPS
2. **Valid Icons** - Use proper PNG icons with transparency
3. **Manifest.json** - Update all URLs to your domain
4. **Service Worker Scope** - Ensure proper scope configuration
5. **Testing** - Test on real devices before deploying

## 🔐 Security Considerations

- App is served over HTTPS (required for PWA)
- Content Security Policy headers recommended
- Regular security updates for dependencies
- Validate all user inputs

## 📊 Performance Tips

1. **Minimize bundle size** - Keep assets small
2. **Optimize images** - Use WebP format when possible
3. **Cache strategically** - Don't cache everything indefinitely
4. **Lazy load** - Load images and content on demand
5. **Compress assets** - Use gzip compression

## 🌐 Browser Support

| Browser | Support | Version |
|---------|---------|---------|
| Chrome | ✅ Full | 51+ |
| Firefox | ✅ Full | 44+ |
| Safari | ✅ Partial | 11.1+ |
| Edge | ✅ Full | 79+ |
| Opera | ✅ Full | 38+ |

### iOS Limitations
- No background sync
- No Push API
- Limited to 50MB cache
- No app shortcuts

## 🐛 Troubleshooting

### Service Worker Not Installing
- Clear browser cache
- Check HTTPS is enabled
- Update `CACHE_NAME` in `service-worker.js`

### App Not Installable
- Ensure manifest.json is valid
- Check all required fields are present
- Verify icons are accessible

### Cache Not Working
- Check Network tab in DevTools
- Verify service-worker.js is registered
- Look at Application → Cache Storage

### Icons Not Showing
- Verify icon files exist in `images/` folder
- Check icon paths in manifest.json and HTML
- Ensure images are PNG format

## 📚 Resources

- [Google: Progressive Web Apps](https://web.dev/progressive-web-apps/)
- [MDN: Progressive Web Apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)
- [Web.dev: PWA Checklist](https://web.dev/pwa-checklist/)
- [Can I Use: PWA Features](https://caniuse.com/)

## 📄 License

This project is open source and available under the MIT License.

## 👨‍💻 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests
- Improve documentation

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the resources section
3. Open an issue in the repository

---

**Happy coding! 🎉**

Built with ❤️ as a Progressive Web App
