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

var error_page_404 = "<section class=\"content\"><div class=\"error-page\"><h2 class=\"headline text-yellow\"> 404</h2><div class=\"error-content\">  <h3><i class=\"fa fa-warning text-yellow\"></i> Oops! Page not found.</h3><p>We could not find the page you were looking for. Meanwhile, you may <a href=\"javascript:bzsModifyMainFrame('/home')\">return to home</a> or try not using the search form.</p><form class=\"search-form\"><div class=\"input-group\"><input type=\"text\" disabled=true name=\"search\" class=\"form-control\" placeholder=\"Search bzShare\"><div class=\"input-group-btn\"><button type=\"submit\" name=\"\" class=\"btn btn-warning btn-flat\"><i class=\"fa fa-search\"></i></button></div></div></form></div></div></section>";

var bzsModifyMainFrame_last = ''

/* bzsModifyMainFrame
 * ==========
 * Changes the main frame into given target.
 *
 * @type Function
 * @usage: <a href="javascript:bzsModifyMainFrame(TARGET_ADDRESS)">
 */
var bzsModifyMainFrame = function(address)
{
  if (bzsModifyMainFrame_last == address) {
	return ;
  }
  var xml_request = new XMLHttpRequest();
  var mainframe_body = document.getElementById('container-mainframe')
  xml_request.open('GET', address, false, '', '');
  try {
    xml_request.send();
  } catch (except) {}
  var __container_mainframe_modify_proc_2 = function() {
    if (!xml_request.responseText || xml_request.status != 200) {
      mainframe_body.innerHTML = error_page_404;
      bzsModifyMainFrame_last = ''; // That should be cleared.
    } else {
      mainframe_body.innerHTML = xml_request.responseText;
	  bzsModifyMainFrame_last = address; // Setting for not clicking too much.
    }
	mainframe_body.setAttribute('class', 'animated fadeInRight');
  };
  mainframe_body.setAttribute('class', 'animated fadeOutLeft');
  setTimeout(__container_mainframe_modify_proc_2, 800);
};
