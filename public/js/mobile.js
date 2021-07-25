var isSmallViewport = false;
var isMediumViewport = false;
var $stepsEl = null;

(function() {
  'use strict';

  function getViewport() {
    // bootstrap layout definition
    isSmallViewport = $(window).width() < 768;
    isMediumViewport = $(window).width() < 992;
  }

  // mobile sticky menu setup
  function mobileStickyMenu() {
    getViewport();
    if (isMediumViewport) {
      $stepsEl = $('.form-layer.active .mobile-steps');
      $('.form-layer').on('scroll.mobileStickyMenu', function() {
        $stepsEl.toggleClass('sticky', $('.form-layer.active').scrollTop() > 80);
      });
    }
  }

  mobileStickyMenu();

  window.mobileStickyMenu = mobileStickyMenu;
})();