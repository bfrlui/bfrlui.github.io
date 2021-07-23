var mode = "development";
var currentStep = 1;
var maxGuestNum = 4;
var agreeTnC = false;
var $stepsEl = null;
var isSmallViewport = false;
var isMediumViewport = false;
console.log(mode);

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
      $('.form-layer').on('scroll', function() {
        $stepsEl.toggleClass('sticky', $stepsEl[0].offsetTop > 96)
      });
    }
  }

  // hide removed guest for user to restore it
  function renderGuestInput() {
    $('.guest-input-group:lt(' + guestForm.guestNum.value + ')').removeClass('d-none');
    $('.guest-input-group:gt(' + (guestForm.guestNum.value - 1) + ')').addClass('d-none');
    $('.guest-input-group.d-none').find('input').removeAttr('required');
    $('.guest-input-group:not(.d-none)').find('input').attr('required','');
  }

  // fill up the range with width on dragging
  function rangeFill() {
    var isIE = /Trident|Edge/.test(window.navigator.userAgent);
    var thumbSize = $(window).width() > 1366 ? '82px' : '60px';

    // if (isIE) $('#range-container').css('height', '80px');

    $('#range-fill').css('width',
      guestForm.guestNum.value > 1
        ? 'calc((((100% - ' + thumbSize + ') / 3) * ' + (guestForm.guestNum.value - 1) + ') + ' + thumbSize + ' - (' + thumbSize + ' / 2))'
        : 0
    );
    $('#guest-num-value').text(guestForm.guestNum.value);
  }

  window.addEventListener('load', function() {
    // datepicker initialzation
    // reference: https://github.com/uxsolutions/bootstrap-datepicker
    $('#datepicker').datepicker({
      format: 'dd/mm/yyyy',
      templates: {
        leftArrow: '<i class="icon nav-arrow-left"></i>',
        rightArrow: '<i class="icon nav-arrow-right"></i>'
      }
    });
    $('#datepicker').on('changeDate', function() {
      var datePicked = $('#datepicker').datepicker('getFormattedDate');
      $('#my_hidden_input').val(datePicked);
      $('#dateOfVisit').text(datePicked);
    });

    // render guest inputs based on number of guests in the form
    var template = $('#guest-input-template').html();
    for (var n=1; n <= maxGuestNum; n++) {
      $(guestForm).find('#fieldsets').append(template.replace(/_Index/g, n));
    }
    renderGuestInput();
    rangeFill();

    // steps and step buttons listener
    $('.step-btn').on('click', function(e) {
      e.preventDefault();
      if (!agreeTnC) return;
      var stepId = $(this).attr('href');
      if (stepId === '#form-step' + currentStep) return;
      $('.form-layer').addClass('hidden').removeClass('active');
      $(stepId).removeClass('hidden').addClass('active');
      // inactive old step
      $('#steps ul > li').removeClass('active');
      $('.mobile-steps > li').removeClass('active');
      // active new step
      var currentStep = Number(stepId.slice(-1));
      for (var x=1; x <= currentStep; x++) {
        $('#steps ul > li[step="' + x + '"]').addClass('active');
        $('.mobile-steps > li[step="' + x + '"]').addClass('active');
      }
      // get the current active element for mobile
      $stepsEl = $('.form-layer.active .mobile-steps');
    });

    // input label movement based on input state
    $('form input').on('focus', function(e) {
      $(this).prev('.input-label').addClass('focus');
    });
    $('form input').on('blur', function(e) {
      if (!this.value)
        $(this).prev('.input-label').removeClass('focus');
    });

    // re-render guest input based on number of guests
    // and fill up the range on dragging
    $('#guest-num')
      .on('change', function(e) {
        renderGuestInput();
      })
      .on('input change', function(e) {
        rangeFill();
      });

    $('#form-submit').on('click',function(e) {
      // e.preventDefault();
      // guestForm.submit();
    });

    // Fetch all the forms we want to apply custom Bootstrap validation styles to
    var forms = document.getElementsByClassName('needs-validation');
    // Loop over them and prevent submission
    var validation = Array.prototype.filter.call(forms, function(form) {
      form.addEventListener('submit', function(event) {
        if (form.checkValidity() === false) {
          event.preventDefault();
          event.stopPropagation();
        }
        form.classList.add('was-validated');
      }, false);
    });
  }, false);

  // setup mobile menu based on viewport
  mobileStickyMenu();

  // animation control of ticket type button
  $('#ticket-type-container .btn').on('mouseover', function(e) {
    $(this).parent('.btn-group').attr('hover', $(this).index());
  });
  $('#ticket-type-container .btn').on('mouseout', function(e) {
    $(this).parent('.btn-group').removeAttr('hover');
  });

  // timeslots
  $('#time-slots .col').on('click', function(e) {
    $(this).siblings('.active').removeClass('active');
    $(this).addClass('active');
    guestForm.shuttleBusTimeSlot.value = $(this).attr('value');
    e.preventDefault();
  });

  // mobile only: show bottom shadow of sticky steps when scroll down
  $(window).on('resize', function(e) {
    $('.form-layer').off('scroll');
    mobileStickyMenu();
  });

  // tnc scrolling handling
  $('#form-step1').on('scroll', function() {
    var isHidden = $(this).scrollTop() + $(this).height() > (this.scrollHeight - 298);  // 128 (btn row height) + 170 (reserved footer height)
    
    $('#fading-bg').toggleClass('d-none', isHidden);
  });
  
  // agreen tnc
  $('#agree-tnc').on('click', function(e) {
    agreeTnC = true;
    $('#steps, .mobile-steps').removeClass('disabled');
    $(this).addClass('d-none');
  });

  // loading completed
  setTimeout(function(e) {
    $('body').removeClass('loading');
  },500);
})();