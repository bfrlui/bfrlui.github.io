var isSmallViewport = false;
var isMediumViewport = false;
var $stepsEl = null;
var html5QrCode = null;

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

  function scanner(index) {
    var reader = document.getElementById("reader"); 
    var qrcodeValue = document.getElementById("qrcode-value"); 
    
    // This method will trigger user permissions
    Html5Qrcode.getCameras().then(devices => {
      /**
       * devices would be an array of objects of type:
       * { id: "id", label: "label" }
       */
      if (devices && devices.length) {
        var cameraId = devices[0].id;
        html5QrCode = new Html5Qrcode(/* element id */ "reader");
        html5QrCode.start(
          { facingMode: "environment" }, // using back camera
          {
            fps: 10,    // Optional frame per seconds for qr code scanning
            qrbox: 250  // Optional if you want bounded box UI
          },
          // success
          function(qrMessage) {
            html5QrCode.stop();
            $('#form-step2 .form-step, #reader').toggleClass('d-none');
            guestForm['guest' + index + 'Ticket'].value = qrMessage;
            $('.input-label[for=guest' + index + '-ticket]').addClass('focus');
          },
          // failure
          function(error) {
            // console.log(error);
          },
          ).catch(err => {
            // Start failed, handle it.
            alert(err);
          });
      }
    }).catch(err => {
      console.warn(err);
      alert('Cannot access camera. Please try again or input number manually.')
    });
  }

  mobileStickyMenu();

  if (isMediumViewport) {
    $('#form-step2').on('click', '.code-reader', function(e) {
      e.preventDefault();
      var index = $(this).closest('.guest-input-group').index() + 1;
      $('#form-step2 .form-step, #reader').toggleClass('d-none');
      scanner(index);
    });
  }

  window.mobileStickyMenu = mobileStickyMenu;
})();