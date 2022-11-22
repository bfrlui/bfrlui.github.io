const ClassPrefix = 'bm-';
const LoadComponent = (name, version) => {
  let container = document.getElementById('component-container');
  let ver = 'v' + version;
  let componentHTML = document.getElementById(name + '-' + ver);
  let componentInfo = document.getElementById(name + '-' + ver + '-' + 'doc');
  if (componentHTML) container.innerHTML = componentHTML.innerText.replace(/{|}/g, '');
  currentComponent = name;

  // ui control for version buttons in navbar of parent window
  window.parent.document.querySelectorAll('.navbar-nav [data-version]').forEach(el => {
    el.parentElement.classList.toggle('d-none', el.dataset.version > Component[name].versions);
  });

  // render component info
  window.parent.document.getElementById('component-title').innerText = Component[currentComponent].title + (version > 1 ? ' ' + ver : '');
  window.parent.document.getElementById('component-info').innerHTML = componentInfo.innerText;
}
const InitComponent = (version) => {
  let v = 'v' + version;
  if (Component[currentComponent] &&
    Component[currentComponent][v] &&
    typeof Component[currentComponent][v] === 'function') {
    Component[currentComponent][v]();
  }
}
const RerunSetup = version => {
  let rerunEl = document.getElementById('rerun');
  rerunEl.addEventListener('click', e => {
    e.preventDefault();
    LoadComponent(currentComponent, version)
    InitComponent(version);
  });
  return rerunEl;
}
const SetProgress = (el, p) => {
  if (p > 100) return true;
  el.style.width=p+'%';
  el.setAttribute('aria-valuenow', p);
  return false;
}
const Component = {
  elementary: {
    versions: 0,
    title: 'Elementary',
    v1: () => {
      Component.textCollapse.v1();
    }
  },
  accordion: {
    versions: 2
  },
  alerts: {
    versions: 2,
    v2: () => {
      let rerunEl = RerunSetup(2);
      document.querySelectorAll('.progress-bar').forEach(el => {
        let p=0;
        let alertEl = el.closest('.alert');
        new bootstrap.Alert(alertEl);
        let alert = bootstrap.Alert.getInstance(alertEl);
        let loop = () => setTimeout(() => {
          if (!SetProgress(el, ++p)) loop();
        }, 10);
        // progress end handling
        el.addEventListener('transitionend', e => {
          if (p < 100) return;
          alert.close();
        });
        alertEl.addEventListener('closed.bs.alert', () => {
          rerunEl.classList.remove('d-none');
        }, { once: true });
        loop();
      });
    }
  },  
  badge: {
    versions: 2
  },
  buttons: {
    versions: 2
  },
  comment: {
    versions: 4,
    v2: () => {
      Component.textCollapse.v1();
      document.querySelectorAll(`.${ClassPrefix}comment-text-collapse-toggle`).forEach(el => {
        el.addEventListener('click', e => {
          e.preventDefault();
          if (el.parentNode.classList.contains(`${ClassPrefix}comment-text-opened`)) {
            el.parentNode.addEventListener('transitionend', e => {
              el.parentNode.classList.remove(`${ClassPrefix}comment-text-collapsing`, `${ClassPrefix}comment-text-opened`);
            }, { once: true });
            el.parentNode.classList.add(`${ClassPrefix}comment-text-collapsing`);
          } else {
            el.parentNode.classList.add(`${ClassPrefix}comment-text-opened`);
          }
        });
      })
    },
    v3: () => Component.comment.v2(),
    v4: () => Component.comment.v2()
  },
  fullSizeAnchor: {
    versions: 1,
    title: '.el-fullSizeAnchor',
    info: {
      v1: 'This atom is inherited from <code>&lt;a&gt;</code> element with atom class prefix <code>.a</code>'
    },
    danger: {
      v1: 'Its parent element must use <code>position: relative;</code> because it is using <code>position: absolute;</code>'
    }
  },
  step: {
    versions: 2,
    v1: () => {
      let stepTriggers = [];
      document.querySelectorAll('.bm-step .nav-item > .btn').forEach(el => {
        stepTriggers.push(new bootstrap.Tab(el));
        el.addEventListener('show.bs.tab', e => {
          let nextStep = e.target.dataset.bmStep; // newly activated tab
          let prevStep = e.relatedTarget.dataset.bmStep; // previous active tab
          nextStep > prevStep
            ? e.relatedTarget.parentNode.nextElementSibling.querySelector('.progress-bar').style.width = '100%'
            : e.target.parentNode.nextElementSibling.querySelector('.progress-bar').style.width = '0%';
        });
      });
      document.querySelectorAll('[data-step-target]').forEach(el => {
        el.addEventListener('click', e => {
          e.preventDefault();
          let stepEl = document.querySelector(el.dataset.stepTarget);
          if (el.dataset.passed) {
            stepTriggers[el.dataset.stepCurrent]._element.classList.add('bm-state-pass');
          }
          // el.dataset.step > el.dataset.stepCurrent
          //   ? stepEl.querySelector(`.bm-step-${el.dataset.stepCurrent}`).nextElementSibling.querySelector('.progress-bar').style.width = '100%'
          //   : stepEl.querySelector(`.bm-step-${el.dataset.stepCurrent}`).previousElementSibling.querySelector('.progress-bar').style.width = '0%';
          stepTriggers[Number(el.dataset.step)].show();
        });
      });
    }
  },
  textCollapse: {
    versions: 3,
    title: '.el-textCollapse',
    v1: () => {
      document.querySelectorAll('.el-textCollapse-toggle').forEach(el => {
        el.addEventListener('click', e => {
          // react as native anchor if click on <a>
          if (e.target.nodeName === 'A' && !e.target.classList.contains('el-textCollapse-toggle')) return;
          e.preventDefault();
          
          let componentEl = document.querySelector(el.dataset.target) || el;
          let fadeEl = componentEl.querySelector('.el-textFaded');
          let isRotateZ = el.classList.contains('el-rotateZ');

          // skip if animation in progress
          if (componentEl.classList.contains('el-textCollapse-animating')) return;

          componentEl.classList.add('el-textCollapse-animating');

          componentEl.addEventListener('transitionend', e => {
            if (componentEl.classList.contains('el-textCollapse-open')) {
              componentEl.classList.remove('el-textCollapse-closing', 'el-textCollapse-open');
              if (fadeEl) {
                fadeEl.style.background = '';
                fadeEl.style.display = '';
              }
            } else {
              componentEl.classList.add('el-textCollapse-open');
              componentEl.classList.remove('el-textCollapse-opening');
              fadeEl && (fadeEl.style.display = 'none');
            }

            componentEl.classList.remove('el-textCollapse-animating');
          }, { once: true });

          if (componentEl.classList.contains('el-textCollapse-open')) {
            componentEl.classList.add('el-textCollapse-closing');
            isRotateZ && el.style.setProperty('--angle', '0deg');
          } else {
            componentEl.classList.add('el-textCollapse-opening');
            isRotateZ && el.style.setProperty('--angle', '180deg');
            fadeEl && (fadeEl.style.background = 'none');
          }
        });
      })
    },
    v2: () => Component.textCollapse.v1(),
    v3: () => Component.textCollapse.v1()
  },
  timeline: {
    versions: 2,
    v1: () => {
      Component.textCollapse.v1();
    },
    v2: () => {
      document.querySelectorAll(`.${ClassPrefix}timeline.bm-v2 .${ClassPrefix}timeline-item-toggle`).forEach(el => {
        el.addEventListener('click', e => {
          e.preventDefault();
          let itemEl = el.closest(`.${ClassPrefix}timeline-item`);
          if (!itemEl.classList.contains(`${ClassPrefix}state-open`)) {
            itemEl.closest(`.${ClassPrefix}timeline`).querySelectorAll(`.${ClassPrefix}state-open`).forEach(el => el.classList.remove(`${ClassPrefix}state-open`));
          }
          itemEl.classList.toggle(`${ClassPrefix}state-open`);
          // itemEl.firstElementChild.classList.toggle('w-100');
          // itemEl.querySelector(`.${ClassPrefix}timeline-marker`).classList.toggle('invisible');
        });
      });
    }
  },
  toast: {
    versions: 2,
    v2: () => {
      let rerunEl = RerunSetup(2);
      document.querySelectorAll('.progress-bar').forEach(el => {
        let p=0;
        let loop = () => setTimeout(() => {
          if (!SetProgress(el, ++p)) loop();
        }, 10);
        let toastEl = el.closest('.toast');
        // progress end handling
        el.addEventListener('transitionend', e => {
          if (p < 100) return;
          let toast = bootstrap.Toast.getOrCreateInstance(toastEl);
          toast.hide();
        });
        toastEl.addEventListener('hidden.bs.toast', () => {
          rerunEl.classList.remove('d-none');
        }, { once: true });
        loop();
      });
    }
  }
}