window.onload = function() {
  /* Hide the is_external flag if it's disabled
  I can't make this work in django so far.
   */
  const externalField = document.querySelector('#id_is_external');
  const externalFieldRow = document.querySelector('.form-row.field-is_external');

  if (externalField && externalFieldRow && externalField.disabled) {
    externalFieldRow.style.display = 'none';
  }
}
