/*! bzShare bzs.js
 * ================
 * Main JS application file for bzShare. This file
 * should be included in all pages. It controls some layout
 * options and implements exclusive bzShare plugins.
 *
 * @Author    Geoffrey, Tang.
 * @Support <http://ht35268.github.io>
 * @Email     <ht35268@outlook.com>
 */

$('#container-mainframe').load('/home');
var bzsReloadMainframeWorking = false;
var bzsReloadMainframeLastAccess = '/home';

var bzsReloadMainframe = function() {
    var mainframe_body = $('#container-mainframe');
    var opt_data = $(this).data('href');
    if (bzsReloadMainframeWorking ||
            $(this).data('href') == bzsReloadMainframeLastAccess)
        return ;
    bzsReloadMainframeWorking = true;
    bzsReloadMainframeLastAccess = opt_data
    mainframe_body.removeClass('fadeInRight').addClass('fadeOutLeft');
    setTimeout(function() {
        try {
            mainframe_body.load(opt_data, function() {
                mainframe_body.removeClass('fadeOutLeft').addClass('fadeInRight');
                $('[data-href]').click(bzsReloadMainframe);
                bzsAdaptContentToSize();
                setTimeout(function() {
                    bzsReloadMainframeWorking = false;
                }, 800);
            });
        } catch (exception) {
            return ;
        }
    }, 800);
    return ;
};

var bzsAdaptContentToSize = function() {
    var small_phone_width = 350;
    var phone_width = 450;
    var tablet_width = 768;
    var current_width = $(window).width();
    // Set hide settings on tablets
    if (current_width <= tablet_width)
        $('[selective-hidden="tablets"]').attr('hidden', 'hidden');
    else
        $('[selective-hidden="tablets"]').removeAttr('hidden');
    // Set hide settings on phones
    if (current_width <= phone_width)
        $('[selective-hidden="phones"]').attr('hidden', 'hidden');
    else
        $('[selective-hidden="phones"]').removeAttr('hidden');
    // Set hide settings on very small phones
    if (current_width <= small_phone_width)
        $('[selective-hidden="small-phones"]').attr('hidden', 'hidden');
    else
        $('[selective-hidden="small-phones"]').removeAttr('hidden');
    return ;
}
bzsAdaptContentToSize();
$(window).resize(bzsAdaptContentToSize);

$('[data-href]').click(bzsReloadMainframe);
