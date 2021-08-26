var env = location.hostname == 'localhost' ? 'dev' : 'prd';
var currentStep = 1;
var maxGuestNum = 8;
var agreeTnC = false;
var mode = 'new';
var currentLang =$('html').attr('lang');
var mtCaptchaLang = { en: 'en', tc: 'zh-hk', sc: 'zh' }
// 0 = dated, 1 = opendated, 2 = pass
var ticketType = '';
// Configuration to construct the captcha widget. Sitekey is a Mandatory Parameter 
var mtcaptchaConfig = { "sitekey": env == 'prd' ? "MTPublic-K5c0cwAEA" : "MTPublic-l2MBtzMdK", "lang": mtCaptchaLang[currentLang] };

(function() {
  'use strict';

  guestForm.reset();
  
  var apiUrl = {
    visitDate: function(guestNum) { 
      var apiVisitDate = '/api/' + ticketType + '/timeslots/' + guestNum;
      return env == 'dev' ? '/data/timeslots' + guestNum + '.json' : apiVisitDate
    },
    verify: function(ticketNumber, visitDate) {
      var date = '';
      if (visitDate) {
        date = visitDate.split('/');
        date = '/' + date[2] + '-' + date[1] + '-' + date[0];
      }
      var apiVerify = '/api/' + ticketType + '/verify/' + ticketNumber.replace('maskTicket', '') + date;
      return env == 'dev' ? '/data/verify.json' : apiVerify
    },
    shuttle: function(guestNum, visitDate) {
      var date = '';
      date = visitDate.split('/');
      date = date[2] + '-' + date[1] + '-' + date[0] + '/';
      var apiShuttle = '/api/' + ticketType + '/shuttleBusService/' + date + guestNum;
      return env == 'dev' ? '/data/shuttle.json' : apiShuttle
    }
  }

  // convert yyyy-mm-dd to dd/mm/yyyy
  var dateFormat = function(date) {
    var dateStr = date.split('-');
    return dateStr[2] + '/' + dateStr[1] + '/' + dateStr[0];
  }

  var api = function(url, options) {
    var $defer = $.Deferred();
    $.ajax({
        url: url,
        method: "GET",
        dataType: 'JSON',
        contentType: 'application/json; charset=UTF-8'
      })
      .done(function(resp) {
        $defer.resolve(resp, options);
      })
      .fail(function(jqXHR, textStatus, errorThrown) {
        // handle ajax error
        console.warn('ajax error: ' + textStatus);
        alert('System or network error! Please check and try again later.');
        $('[in-progress]').removeAttr('in-progress').removeClass('disabled');
      });
    return $defer;
  }

  var formValidation = {
    step2: function() {
      var $formStep2 = $('#form-step2');
      var isValidEmail = function(mail) {
        var re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
        return re.test(mail);
      }
    
      // must not empty for required fields and validate each field
      $formStep2.find(':input[required]').each(function(i, e) {
        var $e = $(e);
        var $field = $e.closest('.field-container');

        // check if empty but ignore hidden guest input
        $([e, $field[0]]).toggleClass('is-invalid',
          $e.closest('.d-none').length
            ? false
            : $e.attr('type') == 'checkbox'
              ? !e.checked
              : e.value === ''
        );

        // email
        if (e.id === 'email' && e.value && !isValidEmail(e.value)) {
          $([e, $field[0]]).addClass('is-invalid');
        }

        // set error index if more than one error messages
        if ($field.find('.invalid-feedback').length > 1) {
          $field.attr('errindex', 1);
        }
      });

      // fields cross checking
      if (guestForm.email.value != guestForm.confirmEmail.value) {
        var $input = $('input[type=email]:eq(1)').addClass('is-invalid');
        $input.closest('.field-container').addClass('is-invalid')
      }
      // contact number
      if (guestForm.contactNumber.value.length < 8) {
        $('#contact-number').addClass('is-invalid').closest('.field-container').addClass('is-invalid');
      }

      checkTicketDuplication();

      return $formStep2.find('.is-invalid').length > 0 ? $.Deferred().resolve(false) : verifyTickets();
    },
    step3: function () {
      var shuttleBusServiceError = guestForm.shuttleBusService.checked && !guestForm.shuttleBusTimeSlot.value;
      var mtState = mtcaptcha.getStatus();

      $('#captcha').toggleClass('is-invalid', !mtState.isVerified);
      $('#shuttle-bus-service').toggleClass('is-invalid', shuttleBusServiceError);

      return !shuttleBusServiceError && mtState.isVerified;
    }
  }

  function mtcaptchaInit() {
    var mt_service = document.createElement("script");
    mt_service.async = true;
    mt_service.src =
      "https://service.mtcaptcha.com/mtcv1/client/mtcaptcha.min.js";
    (
      document.getElementsByTagName("head")[0] ||
      document.getElementsByTagName("body")[0]
    ).appendChild(mt_service);
    var mt_service2 = document.createElement("script");
    mt_service2.async = true;
    mt_service2.src =
      "https://service2.mtcaptcha.com/mtcv1/client/mtcaptcha2.min.js";
    (
      document.getElementsByTagName("head")[0] ||
      document.getElementsByTagName("body")[0]
    ).appendChild(mt_service2);
  }

  function apiFail(resp) {
    console.warn('api error: ' + JSON.stringify(resp));
    alert('System error! Please try again later.');
  }

  function getUrlParameter(name) {
    name = name.replace(/[\[]/, '\\[').replace(/[\]]/, '\\]');
    var regex = new RegExp('[\\?&]' + name + '=([^&#]*)');
    var results = regex.exec(location.search);
    return results === null ? '' : decodeURIComponent(results[1].replace(/\+/g, ' '));
  };

  function loadShuttleBusTimeSlots() {
    // set state of service for ui appearance 
    $('#shuttle-bus-service').attr('require-service', guestForm.shuttleBusService.checked ? 'yes' : 'no');
    if (!guestForm.shuttleBusService.checked) return;

    var template = '<a class="_classes_" href="#" value="_time_">_time_</a>';
    var el = null;

    api(apiUrl.shuttle(guestForm.guestNum.value, guestForm.dateOfVisit.value)).then(function(resp) {
      if (!resp.success) {
        apiFail(resp);
        return;
      }
      var data = resp.data;
      var classes = '';
      $('#time-slots-pm a, #time-slots-am a').remove();
      for(var x=0; x < data.length; x++) {
        classes = 'col';
        el = template.replace(/_time_/g, data[x].time);
        // reset selected timeslot if already full or not available at this moment
        if (guestForm.shuttleBusService.checked && guestForm.shuttleBusTimeSlot.value == data[x].time && (!data[x].available || data[x].full)) {
          guestForm.shuttleBusTimeSlot.value = '';
        // set active if selected previously
        } else if (guestForm.shuttleBusService.checked && guestForm.shuttleBusTimeSlot.value == data[x].time) {
          classes += ' active';
          // better ux to show selected time slot if afternoon
          if (guestForm.shuttleBusTimeSlot.value >= '12:00') {
            $('#shuttle-bus-service').attr('time-slot', 'pm');
          }
        }
        if (!data[x].available) {
          classes += ' disabled';
        }
        if (data[x].full) {
          classes += ' full';
        }
        $('#time-slots-' + (data[x].time >= '12:00' ? 'pm' : 'am')).append(el.replace(/_classes_/, classes));
      }
  
      // show message if no available timeslots
      $('#time-slots-pm p').toggleClass('d-none', $('#time-slots-pm a').length > 0);
      $('#time-slots-am p').toggleClass('d-none', $('#time-slots-am a').length > 0);
  
      // setup event
      $('.time-slots .col')
        .on('click', function(e) {
          e.preventDefault();
          if (!guestForm.shuttleBusService.checked) return;
          $('#time-slots-container .col.active').removeClass('active');
          $(this).addClass('active');
          guestForm.shuttleBusTimeSlot.value = $(this).attr('value');
        })
        .on('mouseover', function(e) {
          $(this).addClass('hover');
        })
        .on('mouseleave', function(e) {
          $(this).removeClass('hover');
        });
    });
  }

  function labelAutoFocus() {
    $('.input-label').each(function(i, el) {
      var $el = $(el);
      $el.toggleClass('focus', $el.next('input').val() != '');
    });
  }

  // hide removed guest for user to restore it
  function renderGuestInput() {
    var $availGuest = $('.guest-input-group:lt(' + guestForm.guestNum.value + ')');
    var $unavailGuest = $('.guest-input-group:gt(' + (guestForm.guestNum.value - 1) + ')');

    // re-order the guest info
    for(var i=1; i < maxGuestNum; i++) {
      if (guestForm['guest' + i + 'Name'].value === '') {
        guestForm['guest' + i + 'Name'].value = guestForm['guest' + (i + 1) + 'Name'].value;
        guestForm['guest' + (i + 1) + 'Name'].value = '';
      }
      if (guestForm['guest' + i + 'Ticket'].value === '') {
        guestForm['guest' + i + 'Ticket'].value = guestForm['guest' + (i + 1) + 'Ticket'].value;
        guestForm['guest' + (i + 1) + 'Ticket'].value = '';
      }
    }

    // change state of ticket number and show / hide "buy ticket"
    $availGuest.each(function(i, el) {
      var $el = $(el);
      var x = i + 1;
      if (/maskTicket/.test(guestForm['guest' + x + 'Ticket'].value)) {
        $el.find('input[id*="ticket"]').attr('readonly', true).attr('type', 'password');
      } else {
        $el.find('input[id*="ticket"]').removeAttr('readonly').attr('type', 'text');
      }
      $el.find('.buy-ticket').toggleClass('d-none', guestForm['guest' + x + 'Ticket'].value != '' && guestForm['guest' + x + 'Name'].value != '');
    });
    
    // show / hide the first guest remove button
    $availGuest.eq(0).find('.remove-guest').toggleClass('d-none', guestForm.guestNum.value == 1);

    // show availabe guest input and make it required
    $availGuest.removeClass('d-none');
    $availGuest.find('input').attr('required','');
    // reset error state
    $availGuest.find('.field-container').removeAttr('errindex').removeClass('is-invalid');
    $availGuest.find('input').removeClass('is-invalid');

    // hide unavailable guest input
    $unavailGuest.addClass('d-none');
    // reset unavailable guest state and its value
    $unavailGuest.find('input').removeAttr('required disabled').removeClass('is-invalid').val('');
    $unavailGuest.find('label').removeClass('focus');
    // reset unavailable guest field state for error message
    $unavailGuest.find('.field-container').removeClass('is-invalid').removeAttr('errindex');
    // reset verify message
    $('#verify-message, #verify-message span').addClass('d-none');

    labelAutoFocus();
  }

  // fill up the range with width on dragging
  function rangeFill() {
    // var isIE = /Trident|Edge/.test(window.navigator.userAgent);
    var thumbSize = $(window).width() > 1440 ? '82px' : '58px';

    $('#range-fill').css('width',
      guestForm.guestNum.value > 1
        ? 'calc((((100% - ' + thumbSize + ') / ' + (maxGuestNum - 1) + ') * ' + (guestForm.guestNum.value - 1) + ') + ' + thumbSize + ' - (' + thumbSize + ' / 2))'
        : 0
    );
    $('#range-fill').attr('value',guestForm.guestNum.value);

    $('#guest-num-value').text(guestForm.guestNum.value);
  }

  function renderModifyData() {
    var data = $('#reservationJson').html();
    var uidPrefix = 'maskTicket';
    if (!data) {
      console.warn('modify parse json error: ' + JSON.stringify(data));
      alert('System error! Please try again later.');
      location = 'index.html';  // back to new mode
    }
    data = JSON.parse(data);
    guestForm.guestNum.value = data.guest.length;
    guestForm.email.value = data.email;
    guestForm.confirmEmail.value = data.email;
    guestForm.contactNumber.value = data.contactNumber;
    guestForm.shuttleBusTimeSlot.value = data.shuttleBusTimeSlot;
    guestForm.shuttleBusService.checked = data.shuttleBusService;
    for (var x=0; x < data.guest.length; x++) {
      guestForm['guest' + (x+1) + 'Name'].value = data.guest[x].name;
      guestForm['guest' + (x+1) + 'Ticket'].value = uidPrefix + data.guest[x].ticketNumber;
    }

    // render data
    api(apiUrl.visitDate(guestForm.guestNum.value)).then(function(resp) {
      renderCalendar(resp);
      // update selected date
      guestForm.dateOfVisit.value = data.dateOfVisit;
      $('#datepicker').datepicker('update', data.dateOfVisit);
      $('#dateOfVisit').text(guestForm.dateOfVisit.value);
      // resolve yellow selector over the text (day value)
      $('#datepicker table td').wrapInner('<label class="position-relative m-0"></label>');
    });
    rangeFill();
    renderGuestInput();
    loadShuttleBusTimeSlots();
  }

  function checkTicketDuplication() {
    var isFound = false;
    for (var x=1; x < guestForm.guestNum.value; x++) {
      if (guestForm['guest' + x + 'Ticket'].value) {
        for (var i=x+1; i <= guestForm.guestNum.value; i++) {
          if (guestForm['guest' + x + 'Ticket'].value == guestForm['guest' + i + 'Ticket'].value) {
            isFound = true;
            $('.guest-input-group').eq(i-1).find('.ticket-number')
            .attr('errindex', 3).addClass('is-invalid')
            .find('input').addClass('is-invalid');
          }
        }
      }
    }

    return isFound;
  }
  
  function verifyTickets() {
    var hasError = false;
    var dfd = [];
    var $defer = $.Deferred();
    // reset message before verify
    $('#verify-message').addClass('d-none').find('span').addClass('d-none');
    $('.ticket-number').removeClass('is-invalid').find('input').removeClass('is-invalid');

    // before call api, ensure no duplication
    if (!checkTicketDuplication()) {
      // loop to call api
      for(var i=1; i <= Number(guestForm.guestNum.value); i++) {
        if (guestForm['guest' + i + 'Ticket'].value) {
          dfd.push(
            api(apiUrl.verify(guestForm['guest' + i + 'Ticket'].value, guestForm.dateOfVisit.value), i-1).then(function (resp, guestIndex) {
              if (resp.success) {
                $('.guest-input-group').eq(guestIndex)
                  .find('.ticket-number').removeClass('is-invalid').removeAttr('errindex')
                  .find('input').removeClass('is-invalid');
              } else {
                hasError = true;
                // highlight field has error
                $('.guest-input-group').eq(guestIndex)
                  .find('.ticket-number').addClass('is-invalid').attr('errindex', 2)
                  .find('input').addClass('is-invalid');
              }
            })
          );
        } else {
          hasError = true;
          // show alert message under the button
          $('#verify-message').removeClass('d-none').find('span:nth-child(2)').removeClass('d-none');
          // highlight field has an error
          $('.guest-input-group').eq(i-1)
          .find('.ticket-number').addClass('is-invalid').attr('errindex', 1)
          .find('input').addClass('is-invalid')
        }
      }
    } else {
      hasError = true;
    }

    // all calls done and check if error to show message
    $.when.apply($, dfd).done(function() {
      if (hasError) {
        // show alert message under the button
        $('#verify-message').removeClass('d-none').find('span:nth-child(2)').removeClass('d-none');
      } else {
        $('#verify-message').removeClass('d-none').find('span:nth-child(3)').removeClass('d-none');
      }
      $('[in-progress]').removeAttr('in-progress').removeClass('disabled');
      $defer.resolve(!hasError);
    });
    return $defer;
  }

  function gotoPage(stepId) {
    var nextStep = Number(stepId.slice(-1));
    // switch to next step page
    currentStep = nextStep;
    $('.form-layer').addClass('hidden').removeClass('active');
    $(stepId).removeClass('hidden').addClass('active');
    // reset all active
    $('#steps ul > li').removeClass('active');
    $('.mobile-steps > li').removeClass('active');
    // active steps to current
    for (var x=1; x <= currentStep; x++) {
      $('#steps ul > li[step="' + x + '"]').addClass('active');
      $('.mobile-steps > li[step="' + x + '"]').addClass('active');
    }
  }

  function renderCalendar(resp) {
    if (!resp.success) {
      apiFail(resp);
      return;
    }
    var data = resp.data;
    $('#datepicker').datepicker('destroy');
    $('#datepicker').datepicker({
      startDate: dateFormat(data[0].date),
      endDate: dateFormat(data[data.length-1].date),
      format: 'dd/mm/yyyy',
      language: currentLang,
      templates: {
        leftArrow: '<i class="icon nav-arrow-left"></i>',
        rightArrow: '<i class="icon nav-arrow-right"></i>'
      },
      beforeShowDay: function(date) {
        var dataDate = null;
        // match calendar date with dates from api
        for(var i=0; i < data.length; i++) {
          dataDate = data[i].date.split('-');
          dataDate = new Date(dataDate[0], Number(dataDate[1]) - 1, dataDate[2]);
          if (date.toString() == dataDate.toString()) {
            // return 'full' class for the date styling and disable selection
            if (data[i].full) return { enabled: false, classes: 'full' };
            return data[i].available;
          }
        }
        // other calendar dates are not selectable
        return false;
      }
    });
    // clear visit date on each rendering
    guestForm.dateOfVisit.value = '';
    $('#dateOfVisit').text(guestForm.dateOfVisit.value);
    // resolve yellow selector over the text (day value)
    $('#datepicker table td').wrapInner('<label class="position-relative m-0"></label>');
    $('#datepicker')
      .on('mouseover', '.day:not(.disabled)', function(e) {
        $(this).addClass('hover');
      })
      .on('mouseleave', '.day:not(.disabled)', function(e) {
        $(this).removeClass('hover');
      });
  }

  window.addEventListener('load', function() {
    // determine ticket type
    ticketType = $('#ticket-type-container .btn-group').attr('active');
    switch (ticketType) {
      case '0': ticketType = 'dated'; break;
      case '1': ticketType = 'opendated'; break;
      case '2': ticketType = 'pass'; break;
      default:
        console.error('unhandled ticket type: ' + ticketType);
    }

    // render guest inputs based on number of guests in the form
    maxGuestNum = $('#range-container').attr('max-guests');
    maxGuestNum = Number(isNaN(maxGuestNum) ? 8 : maxGuestNum);
    guestForm.guestNum.value = $('#range-container').attr('preset') || 1;
    if (guestForm.guestNum.value > maxGuestNum) guestForm.guestNum.value = maxGuestNum;
    var template = $('#guest-input-template').html();
    for (var n=1; n <= maxGuestNum; n++) {
      $(guestForm).find('#fieldsets').append(template.replace(/_Index/g, n));
    }
    $('#guest-num').attr('max', maxGuestNum);
    renderGuestInput();
    rangeFill();

    // datepicker initialzation
    // reference: https://github.com/uxsolutions/bootstrap-datepicker
    var datepickerTCnSC = {
      days: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
      daysShort: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
      daysMin: ["日", "一", "二", "三", "四", "五", "六"],
      months: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
      monthsShort: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
      today: "Today",
      clear: "Clear",
      format: "mm/dd/yyyy",
      titleFormat: "yyyy年MM", /* Leverages same syntax as 'format' */
      weekStart: 0
    };
    $.fn.datepicker.dates['tc'] = datepickerTCnSC;
    $.fn.datepicker.dates['sc'] = datepickerTCnSC;

    // set active form for modify mode
    var reservationNumber = getUrlParameter('r');
    // skip tnc and directly goto input form
    if (reservationNumber) {
      mode = 'modify';
      currentStep = 2;
      // append reservation number to each language link
      $('.lang-switch > a').each(function(i, el) {
        el.href = el.href + '?r=' + reservationNumber;
      });
      renderModifyData();
    } else {
      mode = 'new';
      currentStep = 1;
      api(apiUrl.visitDate(guestForm.guestNum.value)).then(function(resp) {renderCalendar(resp)});
    }
    $('.form-layer').addClass('hidden').removeClass('active');
    $('#form-step' + currentStep).removeClass('hidden').addClass('active');

    // set mode for the app
    $('main').attr('mode', mode);

    // setup mobile menu based on viewport
    mobileStickyMenu();

    // -------------------------------------------
    // events setup
    // -------------------------------------------

    $('#verify').on('click', function(e) {
      e.preventDefault();
      // not to verify if visit date is not yet selected and ticket type is not 'dated'
      if (guestForm.dateOfVisit.value == '') {
        $('#verify-message').removeClass('d-none').find('span:first-child').removeClass('d-none');
      } else {
        $(this).attr('in-progress', 'true').addClass('disabled');
        console.log(this.getAttribute('in-progress'));
        verifyTickets();
      }
    });

    $('#shuttle-bus-input').on('click', function(e) {
      $('#shuttle-bus-service').attr('require-service', this.checked ? 'yes' : 'no');
      // remove selected time slot
      $('.time-slots .col.active').removeClass('active');
      if (!this.checked) {
        $('#shuttle-bus-service').removeClass('is-invalid');
      }
      guestForm.shuttleBusTimeSlot.value = '';
      loadShuttleBusTimeSlots();
    });

    // remove guest by clicking trash
    $('.remove-guest').on('click', function(e) {
      e.preventDefault();
      var $guest = $(this).closest('.guest-input-group');
      guestForm.guestNum.value--;
      // clear all value of this guest
      $guest.find('input').val('');
      // $guest.appendTo('#fieldsets');
      renderGuestInput();
      rangeFill();
      api(apiUrl.visitDate(guestForm.guestNum.value)).then(function(resp) {renderCalendar(resp)});
    });

    $('#datepicker').on('changeMonth', function() {
      // intentionally delay as here is on before trigger
      setTimeout(function() {
        $('#datepicker table td').wrapInner('<label class="position-relative m-0"></label>');
      },100);
    });

    $('#datepicker').on('changeDate', function() {
      guestForm.dateOfVisit.value = $('#datepicker').datepicker('getFormattedDate');
      $('#dateOfVisit').text(guestForm.dateOfVisit.value);
      $('#date-of-visit-input').removeClass('is-invalid');
      $('#datepicker table td').wrapInner('<label class="position-relative m-0"></label>');
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
        if (guestForm.guestNum.value < maxGuestNum) {
          $('.guest-input-group').eq(guestForm.guestNum.value).find('input').val('');
        }
        api(apiUrl.visitDate(guestForm.guestNum.value)).then(function(resp) {renderCalendar(resp)});
        renderGuestInput();
      })
      .on('input change', function(e) {
        rangeFill();
      });

    $('#form-submit').on('click',function(e) {
      e.preventDefault();
      // sessionStorage.setItem('opwwModifyReservation', 'true');
      if (formValidation.step3()) {
        for (var x=1; x <= guestForm.guestNum.value; x++) {
          guestForm['guest' + x + 'Ticket'].value = guestForm['guest' + x + 'Ticket'].value.replace('maskTicket', '');
        }
        guestForm.submit();
      }
    });

    // animation control of ticket type button
    $('#ticket-type-container .btn').on('mouseover', function(e) {
      $(this).parent('.btn-group').attr('hover', $(this).index());
    });
    $('#ticket-type-container .btn').on('mouseout', function(e) {
      $(this).parent('.btn-group').removeAttr('hover');
    });

    // mobile only: show bottom shadow of sticky steps when scroll down
    $(window).on('resize', function(e) {
      $('.form-layer').off('scroll.mobileStickyMenu');
      mobileStickyMenu();
    });

    // tnc scrolling handling
    $('#form-step1').on('scroll', function() {
      var scrollTop = $(this).scrollTop();
      var isHidden = scrollTop + $(this).height() > (this.scrollHeight - 298);  // 128 (btn row height) + 170 (reserved footer height)
      $('#fading-bg').toggleClass('d-none', isHidden);
    });
    
    // agreen tnc
    // $('#agree-tnc').on('click', function(e) {
    //   agreeTnC = true;
    //   $('#steps, .mobile-steps').removeClass('disabled');
    //   $(this).addClass('d-none');
    // });

    // steps and step buttons listener
    $('.step-btn').on('click', function(e) {
      e.preventDefault();

      var self = this;
      var stepId = $(this).attr('href');
      if (stepId === '#form-step' + currentStep) return;
      var nextStep = Number(stepId.slice(-1));

      // validation before next step
      if (currentStep > 1 && nextStep > currentStep) {
        formValidation['step' + currentStep]().done(function(isValidForm) {
          $('#check-error').toggleClass('d-none', isValidForm);
          if (!isValidForm && env != 'dev') {
            // scroll to bottom to see alert message
            if (self.id === 'step2-submit') {
              $('#form-step2')[0].scrollTo(0, 99999);
            }
            return;
          }
          
          gotoPage(stepId);

          if (currentStep == 3) {
            loadShuttleBusTimeSlots();
            if ($('#captcha .mtcaptcha').html() == '') {
              mtcaptchaInit();
            }
          }
        });
      } else {
        gotoPage(stepId);
      }
      // get the current active element for $stepEl in mobile.js
      $stepsEl = $('.form-layer.active .mobile-steps');
    });
    
    // only accept alphabets for name (remove numbers and special chars)
    $('input[id*=name]').on('keyup', function(e) {
      if (this.value.match(/[0-9_~`!@#$%\^&*()+=\-\[\]\\';,/{}|\\":<>\?]/g)) {
        this.value = this.value.replace(/[0-9_~`!@#$%\^&*()+=\-\[\]\\';,/{}|\\":<>\?]/g, '');
      }
    });  

    // only accept alphabets and number for ticket number (remove special chars)
    $('input[id*=ticket]').on('keyup', function(e) {
      if (this.value.match(/[_~`!@#$%\^&*()+=\-\[\]\\';,/{}|\\":<>\?]/g)) {
        this.value = this.value.replace(/[_~`!@#$%\^&*()+=\-\[\]\\';,/{}|\\":<>\?]/g, '');
      }
    });  

    // shuttle bus time slots navigation
    $('#time-slots-heading a').on('click', function(e) {
      e.preventDefault();
      var slot = ['am', 'pm'];
      var current = $('#shuttle-bus-service').attr('time-slot');
      var newSlot = 0;
      var inc = this.id == 'time-slot-next' ? 1 : -1

      newSlot = slot.indexOf(current) + inc;
      // recycling the slot
      if (newSlot > slot.length) newSlot = 0;
      if (newSlot < 0) newSlot = slot.length - 1;

      $('#shuttle-bus-service').attr('time-slot', slot[newSlot]);
    });

    $('#contact-number').on('keyup', function(e) {
      if (this.value.length > 8) {
        this.value = this.value.slice(0, 8);
      }
    });
  }, false);
})();