/**
 * --------------------------------------------------------------------------
 * inputCancel.js
 * input box with icon which is clickable to clear input
 * --------------------------------------------------------------------------
 */

class inputCancel {
  constructor(el) {
    this.element = el
  }

  eventSetup() {
    this.element.addEventListener('click', e => {
      e.preventDefault()
      let inputEl = this.element.querySelector('input')
      inputEl.value = ''
      inputEl.focus()
    })
  }
}
  
export default inputCancel