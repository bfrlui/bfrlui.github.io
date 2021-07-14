var mode="development";
var currentStep = 1;
console.log(mode);

// steps and step buttons
$('#steps a, .step-btn').on('click', function(e) {
  e.preventDefault();
  var stepId = $(this).attr('href');
  if (stepId === '#form-step-' + currentStep) return;
  $('.form-step').addClass('hidden');
  $(stepId).removeClass('hidden');
  currentStep = stepId.slice(-1);
});
