import SetTheme from './component/setTheme.js'
import InputCancel from './component/inputCancel.js'

const theme = new SetTheme()

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.input-group-icon').forEach(el => {
    let inputEl = new InputCancel(el)
    theme.init()
    inputEl.eventSetup()
  })
})