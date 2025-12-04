# PWA - Images Folder

This folder contains all image assets for the PWA, including:

## Required Icons

### `icon-192x192.png` (Required)
- Size: 192x192 pixels
- Format: PNG with transparency
- Purpose: Home screen icon on Android devices
- Used in: manifest.json for "any" purpose

### `icon-512x512.png` (Required)
- Size: 512x512 pixels
- Format: PNG with transparency
- Purpose: Splash screen and store listing
- Used in: manifest.json for "any" purpose

### `apple-touch-icon.png` (Recommended)
- Size: 180x180 pixels
- Format: PNG with solid background (no transparency recommended)
- Purpose: iOS home screen icon
- Used in: HTML <link> tag for Apple devices

## Optional Icons

### `icon-96x96.png`
- Size: 96x96 pixels
- Purpose: App shortcuts in manifest

## Screenshot Files (Optional)

### `screenshot-1.png` (Narrow form factor)
- Size: 540x720 pixels
- Purpose: App store and installation experience
- Shows vertical layout

### `screenshot-2.png` (Wide form factor)
- Size: 1280x720 pixels
- Purpose: App store and installation experience
- Shows horizontal layout

## Icon Design Guidelines

1. **Use Clear, Simple Designs**
   - Icons should be recognizable at small sizes
   - Avoid thin lines or fine details

2. **Color Selection**
   - Use your brand colors
   - Ensure good contrast
   - Test on different backgrounds

3. **Padding**
   - Add 10% padding around the icon
   - Leaves safe area for different devices

4. **Consistency**
   - All icons should have same style
   - Maintain brand consistency

5. **Transparency**
   - Use alpha channel for "any" purpose icons
   - Solid backgrounds for "maskable" icons

## Tool Recommendations

- **Figma** - Design and export icons
- **Adobe Illustrator** - Professional icon design
- **Inkscape** - Free vector editor
- **ImageMagick** - CLI tool to generate sizes
- **GIMP** - Free image editor

## Generating Icons from a Single Source

### Using ImageMagick:
```bash
convert original-icon.png -resize 192x192 icon-192x192.png
convert original-icon.png -resize 512x512 icon-512x512.png
convert original-icon.png -resize 180x180 apple-touch-icon.png
```

### Using Online Tools:
- [PWA Icon Generator](https://www.pwa-icon-generator.de/)
- [IconKitchen](https://icon.kitchen/)
- [Favicon Generator](https://favicon-generator.org/)

## File Placement

```
pwa/
└── images/
    ├── icon-192x192.png
    ├── icon-512x512.png
    ├── apple-touch-icon.png
    ├── icon-96x96.png (optional)
    ├── screenshot-1.png (optional)
    └── screenshot-2.png (optional)
```

## Testing Icons

1. **DevTools Inspection:**
   - Open DevTools → Application tab
   - Check manifest.json section
   - Verify icon URLs are correct

2. **Test Installation:**
   - Try installing on Android
   - Try installing on iPhone
   - Check icon displays properly

3. **Test Different Sizes:**
   - Device home screen
   - App switcher
   - Chrome's app drawer

## Accessibility

- Use high contrast
- Avoid relying on color alone
- Include shapes/patterns
- Test with color blindness simulators

---

Replace the placeholder paths with your actual icon files before deploying to production.
