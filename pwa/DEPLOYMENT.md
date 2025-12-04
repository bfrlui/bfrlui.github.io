# Deployment Guide for PWA

This guide covers deploying your PWA to production using GitHub and various hosting services.

## 🚀 Deployment Options

### Option 1: GitHub Pages (Free, Simple)
Best for: Static sites, portfolios, demos

**Pros:**
- Free hosting
- Easy setup with GitHub Actions
- Custom domain support
- HTTPS automatically enabled

**Cons:**
- Static files only (no Node.js backend)
- Cannot use `server.js`
- Limited to public repositories (or paid GitHub Pro)

**Setup Steps:**
1. Create repository on GitHub
2. Push code to repository
3. Enable GitHub Pages in Settings
4. Add GitHub Actions workflow (see below)

### Option 2: Vercel (Recommended)
Best for: PWAs, Next.js, modern web apps

**Pros:**
- HTTPS by default
- Automatic deployments
- Free tier available
- Excellent performance
- Environment variables support

**Setup:**
```bash
npm i -g vercel
vercel
```

### Option 3: Netlify
Best for: PWAs, JAMstack applications

**Pros:**
- Free tier
- Easy deployment
- Form handling
- Lambda functions

**Setup:**
```bash
npm i -g netlify-cli
netlify deploy --prod --dir .
```

### Option 4: Firebase Hosting
Best for: Google ecosystem, real-time databases

**Pros:**
- Free tier
- Firebase integration
- Global CDN
- Easy scaling

**Setup:**
```bash
npm i -g firebase-tools
firebase init hosting
firebase deploy
```

## ⚙️ GitHub Setup (Recommended for PWA)

### Step 1: Initialize Git Repository
```bash
git init
git add .
git commit -m "Initial PWA project"
```

### Step 2: Add Remote Repository
```bash
git remote add origin https://github.com/YOUR_USERNAME/pwa.git
git branch -M main
git push -u origin main
```

### Step 3: Create `.github/workflows/deploy.yml`

This file automates deployment whenever you push to main:

```yaml
name: Deploy PWA

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to production server
        run: |
          echo "Deploying PWA..."
          npm install --production
```

### Step 4: Enable GitHub Pages
1. Go to Settings → Pages
2. Select `main` branch as source
3. Choose root folder
4. Save

**Note:** For PWA with service workers, ensure root folder is selected.

## 🔒 HTTPS Requirement

**CRITICAL:** PWAs require HTTPS for production

GitHub Pages provides HTTPS automatically ✅

If using other hosting:
- Vercel: Automatic ✅
- Netlify: Automatic ✅
- Firebase: Automatic ✅
- Custom server: Use Let's Encrypt free certificates

## 📝 Files to Update Before Production

### 1. Update `manifest.json`
```json
{
  "start_url": "https://yourdomain.com/",
  "scope": "/",
  "icons": [
    {
      "src": "https://yourdomain.com/images/icon-192x192.png",
      "sizes": "192x192",
      "type": "image/png"
    }
  ]
}
```

### 2. Add to `index.html`
```html
<!-- Production meta tags -->
<meta property="og:title" content="My PWA App">
<meta property="og:description" content="Description here">
<meta property="og:image" content="https://yourdomain.com/images/og-image.png">
<meta name="twitter:card" content="summary_large_image">
```

### 3. Update `service-worker.js` Cache Names
```javascript
const CACHE_NAME = 'pwa-cache-v1.0.0'; // Include version
```

## 📋 Pre-Deployment Checklist

- [ ] All icons created and added to `images/` folder
- [ ] `manifest.json` updated with correct URLs
- [ ] Service worker cache names updated
- [ ] `index.html` meta tags completed
- [ ] README.md updated with your info
- [ ] No console errors in DevTools
- [ ] Tested offline mode locally
- [ ] Tested on mobile devices
- [ ] HTTPS enabled on production domain
- [ ] Security headers configured

## 🔐 Production Security Checklist

### 1. Add Security Headers (if using custom server)
```javascript
// In server.js
res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
res.setHeader('X-Content-Type-Options', 'nosniff');
res.setHeader('X-Frame-Options', 'DENY');
res.setHeader('Content-Security-Policy', "default-src 'self'");
```

### 2. Enable CORS Properly
```javascript
res.setHeader('Access-Control-Allow-Origin', 'https://yourdomain.com');
```

### 3. Add robots.txt
Create `robots.txt`:
```
User-agent: *
Allow: /
Sitemap: https://yourdomain.com/sitemap.xml
```

## 📊 Monitoring & Analytics

### Add Google Analytics
```html
<!-- In index.html head -->
<script async src="https://www.googletagmanager.com/gtag/js?id=GA_ID"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'GA_ID');
</script>
```

### Monitor Service Worker
```javascript
// Add to app.js
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.oncontroller = () => {
    console.log('Service Worker updated');
    // Notify user of app update
  };
}
```

## 🚀 Deployment Steps by Platform

### GitHub Pages + GitHub Actions
1. Push code to GitHub
2. GitHub Actions builds automatically
3. Deploys to gh-pages branch
4. Visit: `https://yourusername.github.io/pwa`

### Vercel
```bash
vercel --prod
```
Visit: `https://pwa.vercel.app`

### Netlify
```bash
netlify deploy --prod
```
Visit: Your custom domain

### Firebase
```bash
firebase deploy --only hosting
```
Visit: `https://your-project.firebaseapp.com`

## 📱 Post-Deployment Testing

### 1. Test Installation
- Visit on Chrome Android
- Look for install prompt
- Install and test offline

### 2. Test Offline
- DevTools → Network → Offline
- Navigate pages
- Verify cached content loads

### 3. Lighthouse Audit
- Chrome DevTools → Lighthouse
- Run PWA audit
- Fix any issues

### 4. Test on Real Devices
- iOS devices
- Android devices
- Different browsers

## 🔄 Continuous Deployment

### Update Service Worker Version
To push updates to users:

1. Update `CACHE_NAME` in `service-worker.js`:
   ```javascript
   const CACHE_NAME = 'pwa-cache-v2'; // Changed from v1
   ```

2. Git commit and push:
   ```bash
   git add .
   git commit -m "Update cache version"
   git push
   ```

3. Old cache automatically cleared on next visit

## ⚠️ Common Issues

### Issue: App not installable after deployment
**Solution:** Check manifest.json is served with correct MIME type

### Issue: Service worker not updating
**Solution:** Increment CACHE_NAME version

### Issue: Icons not showing
**Solution:** Verify icon paths are absolute URLs

### Issue: Offline not working
**Solution:** Check service worker is registered in DevTools

## 📚 Additional Resources

- [GitHub Pages Documentation](https://pages.github.com/)
- [Vercel Deployment Docs](https://vercel.com/docs)
- [Netlify Deploy Docs](https://docs.netlify.com/)
- [Firebase Hosting Docs](https://firebase.google.com/docs/hosting)
- [PWA Deployment Checklist](https://web.dev/pwa-checklist/)

## 📞 Support

If deployment fails:
1. Check HTTPS is enabled
2. Verify manifest.json syntax (validate with JSON Schema)
3. Check service-worker.js for errors (DevTools → Application)
4. Review deployment logs
5. Test locally with `npm start`

---

**Ready to deploy? Start with Vercel or GitHub Pages!** 🚀
