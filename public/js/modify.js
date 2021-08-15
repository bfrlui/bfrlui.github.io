(function() {
  'use strict';

  function getUrlParameter(name) {
    name = name.replace(/[\[]/, '\\[').replace(/[\]]/, '\\]');
    var regex = new RegExp('[\\?&]' + name + '=([^&#]*)');
    var results = regex.exec(location.search);
    return results === null ? '' : decodeURIComponent(results[1].replace(/\+/g, ' '));
  };
  
  var reservationNumber = getUrlParameter('r');
  var canceled = getUrlParameter('canceled') == 'true';

  if (canceled) {
    var $modal = $('.modal');
    $modal.find('.modal-content').attr('body', 'canceled-body');
    $modal.modal('show');
  } else if (reservationNumber) {
    cancelForm.reservationNumber.value = reservationNumber;
    $('a#modify').attr('href', 'index.html?r=' + reservationNumber);
    $('.lang-switch > a').each(function(i, el) {
      el.href = el.href + '?r=' + reservationNumber;
    });
  } else {
    // redirect to index page if neither modify nor canceled
    window.location = 'index.html';
  }
})();