/**
 * --------------------------------------------------------------------------
 * setTheme.js
 * - theme color setter for predefined colors
 * - theme setter and toggle for dark / light
 * - device setter and toggle for icons set
 * - page spinner and fade in/out
 * --------------------------------------------------------------------------
 */

const defaultThemeColor = 'blue'
const defaultThemeDevice = 'ios'
const themeColorStylesheet = document.querySelectorAll('link[theme-color]')
const loader = document.getElementById('loader')
const themeToggle = document.getElementById('theme-toggle')
const themeDeviceToggle = document.getElementById('theme-device-toggle')

class SetTheme{

  // public
  setter = theme => {
    this._loaderIn()
    if (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-bs-theme', 'dark')
    } else {
      document.documentElement.setAttribute('data-bs-theme', theme)
    }
    this._setStoredTheme(theme)
    this._setThemeToggle()
    // this._loaderOut()
  }

  toggleThemeDevice = () => {
    let device = this._getStoredThemeDevice() == 'ios' ? 'android' : 'ios'
    document.documentElement.dataset.customDevice = device
    this._setStoredThemeDevice(device)
    this._setThemeDeviceToggle()
  }

  setThemeColor = color => {
    this._loaderIn()
    themeColorStylesheet.forEach(s => s.disabled = s.getAttribute('theme-color') != color)
    this._setStoredThemeColor(color)
    this._loaderOut()
  }

  toggleTheme = () => {
    this._loaderIn()
    let theme = this._getStoredTheme() == 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.bsTheme = theme
    this._setStoredTheme(theme)
    this._setThemeToggle()
    this._loaderOut()
  }

  // private
  _getStoredTheme = () => localStorage.getItem('theme')
  _getStoredThemeColor = () => localStorage.getItem('themeColor')
  _getStoredThemeDevice = () => localStorage.getItem('themeDevice')
  _setStoredTheme = theme => localStorage.setItem('theme', theme)
  _setStoredThemeColor = color => localStorage.setItem('themeColor', color)
  _setStoredThemeDevice = device => localStorage.setItem('themeDevice', device)

  _setThemeDeviceToggle = () => {
    themeDeviceToggle.innerText = this._getStoredThemeDevice() == 'ios' ? 'Android' : 'IOS'
  }

  _getPreferredTheme = () => {
    const storedTheme = this._getStoredTheme()
    if (storedTheme) {
      return storedTheme
    }

    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  _setThemeToggle = () => {
    themeToggle.innerText = this._getStoredTheme() == 'dark' ? 'Light' : 'Dark'
  }

  _setThemeDevice = device => {
    document.documentElement.dataset.customDevice = device
    this._setStoredThemeDevice(device)
    this._setThemeDeviceToggle()
  }

  _loaderIn = () => {
    document.body.classList.add('overflow-hidden')
    loader.classList.remove('d-none')
    this._fadeIn(loader)

    let handler = event => {
      document.body.classList.remove('overflow-hidden')
      loader.classList.add('d-none')
    }

    loader.addEventListener('transitionend', handler, {once: true})
  }

  _loaderOut = () => setTimeout(() => this._fadeOut(loader), 1000)

  _fadeIn = element => element.classList.add('show')

  _fadeOut = element => element.classList.remove('show')

  // public
  init() {
    let theme = this._getPreferredTheme()
    let color = this._getStoredThemeColor()
    let device = this._getStoredThemeDevice()
    this.setter(theme)
    this.setThemeColor(color ?? defaultThemeColor)
    this._setThemeDevice(device ?? defaultThemeDevice)
 
    // global
    window.setTheme = this.setter
    window.toggleTheme = this.toggleTheme
    window.toggleThemeDevice = this.toggleThemeDevice
    window.setThemeColor = this.setThemeColor
  
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      const storedTheme = this._getStoredTheme()
      if (storedTheme !== 'light' && storedTheme !== 'dark') {
        this.setter(getPreferredTheme())
      }
    })
  
    document.querySelectorAll('.theme-color-select').forEach(el => {
      el.addEventListener('click', e => {
        let color = e.currentTarget.dataset.color
        e.preventDefault()
        this.setThemeColor(color)
      })
    })
  }
}

export default SetTheme