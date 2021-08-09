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

  function stopScan() {
    html5QrCode && html5QrCode.stop();
    $('#form-step2, #reader-page').toggleClass('d-none');
    // reset the camera area for reentrance
    $('#reader').empty();
    $('#camera-message').attr('index', 1);
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
        $('#camera-message').attr('index', 0);
        html5QrCode.start(
          { facingMode: "environment" }, // using back camera
          {
            fps: 10,    // Optional frame per seconds for qr code scanning
            qrbox: 250  // Optional if you want bounded box UI
          },
          // success
          function(qrMessage) {
            guestForm['guest' + index + 'Ticket'].value = qrMessage;
            $('.input-label[for=guest' + index + '-ticket]').addClass('focus');
            stopScan();
          },
          // failure
          function(error) {
            // console.log(error);
          },
          ).catch(err => {
            // Start failed, handle it.
            console.warn(err);
            $('#camera-message').attr('index', 2);
          });
      }
    }).catch(err => {
      console.warn(err);
      $('#camera-message').attr('index', 2);
    });
  }

  mobileStickyMenu();

  // disabled scan function
  // if (isMediumViewport) {
  //   $('#form-step2').on('click', '.code-reader', function(e) {
  //     e.preventDefault();
  //     var index = $(this).closest('.guest-input-group').index() + 1;
  //     $('#form-step2, #reader-page').toggleClass('d-none');
  //     $('#reader-page').removeClass('hidden').scrollTop(0,0);
  //     scanner(index);
  //   });
  //   $('#cancel-scan').on('click', function(e) {
  //     e.preventDefault();
  //     stopScan();
  //   });
  // }

  window.mobileStickyMenu = mobileStickyMenu;
})();