(function() {
  'use strict';

  var reservationNumber = 'ABCDE1234567890';

  // modify reservation
  $('#modify').on('click', function(e) {
    e.preventDefault();
    window.location = './index.html?r=' + reservationNumber;
  });

  // confirm to cancel
  $('#confirm-cancel-body a:first-child').on('click', function(e) {
    e.preventDefault();
    var $modal = $(this).closest('.modal');
    
    $modal.removeClass('show');
    // todo: call api to cancel
    setTimeout(function() {
      $modal.find('.modal-content').attr('body', 'canceled-body');
      $modal.addClass('show');
    },500);
  })
})();