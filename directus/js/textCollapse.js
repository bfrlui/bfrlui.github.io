export class TextCollapse {
  constructor(el, options = {}) {
    let componentEl = document.querySelector(el.dataset.target) || el;
    this.element = componentEl;

    el.addEventListener('click', e => {
      // react as native anchor if click on <a>
      if (e.target.nodeName === 'A' && !e.target.classList.contains('el-textCollapse-toggle')) return;
      e.preventDefault();
      
      let rotateEl = document.querySelector('.el-textCollapse-toggle.el-rotateZ');

      // skip if animation in progress
      if (componentEl.classList.contains('el-textCollapse-animating')) return;

      componentEl.classList.add('el-textCollapse-animating');

      componentEl.addEventListener('transitionend', () => {
        let state;
        if (componentEl.classList.contains('el-textCollapse-open')) {
          state = 'onCollapsed';
          componentEl.classList.remove('el-textCollapse-closing', 'el-textCollapse-open');
        } else {
          state = 'onExpanded';
          componentEl.classList.add('el-textCollapse-open');
          componentEl.classList.remove('el-textCollapse-opening');
        }

        componentEl.classList.remove('el-textCollapse-animating');

        options[state] && typeof options[state] == 'function' && options[state].call(this);
      }, { once: true });

      if (componentEl.classList.contains('el-textCollapse-open')) {
        componentEl.classList.add('el-textCollapse-closing');
        rotateEl && rotateEl.style.setProperty('--angle', '0deg');
      } else {
        componentEl.classList.add('el-textCollapse-opening');
        rotateEl && rotateEl.style.setProperty('--angle', '180deg');
      }
    });
  }
}