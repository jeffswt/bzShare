/*! bzShare bzs.js
 * ================
 * Main JS application file for bzShare. This file
 * should be included in all pages. It controls some layout
 * options and implements exclusive bzShare plugins.
 *
 * @Author  Geoffrey, Tang.
 * @Support <http://ht35268.github.io>
 * @Email   <ht35268@outlook.com>
 */

//Make sure jQuery has been loaded before app.js
if (typeof jQuery === "undefined") {
  throw new Error("bzShare requires jQuery");
}

/* bzsModifyMainFrame
 * ==========
 * Changes the main frame into given target.
 *
 * @type Function
 * @usage: <a href="javascript:bzsModifyMainFrame(TARGET_ADDRESS)">
 */
var bzsModifyMainFrame = function(address)
{
  var xml_request = new XMLHttpRequest();
  var mainframe_body = document.getElementById('container-mainframe')
  xml_request.open('html', address, false, '', '');
  try {
    xml_request.send();
  } catch (except) {}
  var __container_mainframe_modify_proc_2 = function() {
    if (!xml_request.responseText) {
      mainframe_body.innerHTML = "404 ERROR";
    } else {
      mainframe_body.innerHTML = xml_request.responseText;
    }
    mainframe_body.setAttribute('class', 'animated fadeInRight');
  };
  mainframe_body.setAttribute('class', 'animated fadeOutLeft');
  setTimeout(__container_mainframe_modify_proc_2, 500);
};
