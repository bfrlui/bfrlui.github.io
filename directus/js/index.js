(() => {
  // global constants
  // ----------------
  const TransitionTime = 400;
  const DefaultTheme = 'dark';

  // top level main
  // --------------
  document.addEventListener('DOMContentLoaded', () => {
    const ThemeStylesheet = document.querySelectorAll('link[title]');

    const ChangeTheme = themeStylesheet => {
      let bodyEl = themeStylesheet[0].closest('html').querySelector('body');
      bodyEl.style.opacity = 0;
      themeStylesheet.forEach(s => s.disabled = s.getAttribute('title') != theme);
      setTimeout(() => bodyEl.style.opacity = '', TransitionTime);
    }

    // main starts
    // -----------
    let theme = DefaultTheme;

    ChangeTheme(ThemeStylesheet);

    // events setup
    // ------------

    // theme toggles
    document.querySelectorAll('.theme').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        theme = e.currentTarget.dataset.theme;
        ChangeTheme(ThemeStylesheet);
      });
    });
  }, false);
})();