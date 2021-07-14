var mode="development";
var currentStep = 1;
console.log(mode);

(function() {
  'use strict';
  
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
    
    // steps and step buttons listener
    $('#steps a, .step-btn').on('click', function(e) {
      e.preventDefault();
      var stepId = $(this).attr('href');
      if (stepId === '#form-step' + currentStep) return;
      $('.form-layer').addClass('hidden');
      $(stepId).removeClass('hidden');
      // inactive old step
      $('#steps ul > li').eq(currentStep-1).removeClass('active');
      currentStep = Number(stepId.slice(-1));
      // active new step
      $('#steps ul > li').eq(currentStep-1).addClass('active');
    });
    // input label handling
    $('form input').on('focus', function(e) {
      $(this).prev('.input-label').addClass('focus');
    });
    $('form input').on('blur', function(e) {
      if (!this.value)
        $(this).prev('.input-label').removeClass('focus');
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
})();

