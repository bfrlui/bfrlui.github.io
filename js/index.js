var mode = "development";
var currentStep = 1;
var maxGuestNum = 4;
console.log(mode);

(function() {
  'use strict';

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
  }

  window.addEventListener('load', function() {
    // datepicker initialzation
    $('#datepicker').datepicker({
      format: 'dd/mm/yyyy'
    });
    $('#datepicker').on('changeDate', function() {
      var datePicked = $('#datepicker').datepicker('getFormattedDate');
      $('#my_hidden_input').val(datePicked);
      $('#dateOfVisit').text(datePicked);
    });

    // render guest inputs based on number of guests in the form
    var template = $('#guest-input-template').html();
    for (var n=0; n < maxGuestNum; n++) {
      $(guestForm).children('#fieldsets').append(template.replace(/_Index/g, n));
    }
    renderGuestInput();
    rangeFill();

    // steps and step buttons listener
    $('#steps a, .step-btn').on('click', function(e) {
      e.preventDefault();
      var stepId = $(this).attr('href');
      if (stepId === '#form-step' + currentStep) return;
      $('.form-layer').addClass('hidden');
      $(stepId).removeClass('hidden');
      // inactive old step
      $('#steps ul > li.active').removeClass('active');
      // active new step
      var currentStep = Number(stepId.slice(-1));
      $('#steps ul > li[step="' + currentStep + '"]').addClass('active');
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
      guestForm.submit();
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
  })
})();