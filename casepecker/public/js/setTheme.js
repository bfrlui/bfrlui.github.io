(() => {
  'use strict'

  const getStoredTheme = () => localStorage.getItem('theme')
  const getStoredThemeColor = () => localStorage.getItem('themeColor')
  const getStoredThemeDevice = () => localStorage.getItem('themeDevice')
  const setStoredTheme = theme => localStorage.setItem('theme', theme)
  const setStoredThemeColor = color => localStorage.setItem('themeColor', color)
  const setStoredThemeDevice = device => localStorage.setItem('themeDevice', device)
  const defaultThemeColor = 'blue'
  const defaultThemeDevice = 'ios'
  const themeColorStylesheet = document.querySelectorAll('link[theme-color]')
  const loader = document.getElementById('loader')
  const themeToggle = document.getElementById('theme-toggle')
  const themeDeviceToggle = document.getElementById('theme-device-toggle')

  const getPreferredTheme = () => {
    const storedTheme = getStoredTheme()
    if (storedTheme) {
      return storedTheme
    }

    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  const setTheme = theme => {
    loaderIn()
    if (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-bs-theme', 'dark')
    } else {
      document.documentElement.setAttribute('data-bs-theme', theme)
    }
    setStoredTheme(theme)
    setThemeToggle()
    loaderOut()
  }

  const toggleThemeDevice = () => {
    let device = getStoredThemeDevice() == 'ios' ? 'android' : 'ios'
    document.documentElement.dataset.customDevice = device
    setStoredThemeDevice(device)
    setThemeDeviceToggle()
  }

  const setThemeToggle = () => {
    themeToggle.innerText = getStoredTheme() == 'dark' ? 'Light' : 'Dark'
  }

  const setThemeDeviceToggle = () => {
    themeDeviceToggle.innerText = getStoredThemeDevice() == 'ios' ? 'Android' : 'IOS'
  }

  const setThemeDevice = device => {
    document.documentElement.dataset.customDevice = device
    setStoredThemeDevice(device)
    setThemeDeviceToggle()
  }

  const setThemeColor = color => {
    loaderIn()
    themeColorStylesheet.forEach(s => s.disabled = s.getAttribute('theme-color') != color)
    setStoredThemeColor(color)
    loaderOut()
  }

  const toggleTheme = () => {
    loaderIn()
    let theme = getStoredTheme() == 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.bsTheme = theme
    setStoredTheme(theme)
    setThemeToggle()
    loaderOut()
  }

  const loaderIn = () => {
    document.body.classList.add('overflow-hidden')
    loader.classList.remove('d-none')
    fadeIn(loader)

    let handler = event => {
      document.body.classList.remove('overflow-hidden')
      loader.classList.add('d-none')
    }

    loader.addEventListener('transitionend', handler, {once: true})
  }

  const loaderOut = () => setTimeout(() => fadeOut(loader), 1000)

  const fadeIn = element => element.classList.add('show')
  
  const fadeOut = element => element.classList.remove('show')

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const storedTheme = getStoredTheme()
    if (storedTheme !== 'light' && storedTheme !== 'dark') {
      setTheme(getPreferredTheme())
    }
  })

  document.addEventListener('DOMContentLoaded', () => {
    let theme = getPreferredTheme()
    let color = getStoredThemeColor()
    let device = getStoredThemeDevice()
    setTheme(theme)
    setThemeColor(color ?? defaultThemeColor)
    setThemeDevice(device ?? defaultThemeDevice)
    window.setTheme = setTheme
    window.toggleTheme = toggleTheme
    window.toggleThemeDevice = toggleThemeDevice
    window.setThemeColor = setThemeColor

    document.querySelectorAll('.theme-color-select').forEach(el => {
      el.addEventListener('click', e => {
        let color = e.currentTarget.dataset.color
        e.preventDefault()
        setThemeColor(color)
      })
    })
  })
})()