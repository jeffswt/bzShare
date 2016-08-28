
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

/*
 * Responsive content design functions:
 *  - bzsAdaptContentToSize()
 */
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

/*
 * AJAX seamless transitions
 *  - bzsReloadMainframe() // triggered by buttons
 *  - bzsReloadMainframeSeamless(url) // No effects, triggered by scripts
 *  - bzsReloadMainframeRefresh() // No effects, reload the same page
 */
var bzsReloadMainframeWorking = false;
var bzsReloadMainframeLastAccess = '/files';

var bzsReloadMainframe = function() {
    var mainframe_body = $('#container-mainframe');
    var opt_data = $(this).data('href');
    if (bzsReloadMainframeWorking)// ||
            // $(this).data('href') == bzsReloadMainframeLastAccess)
        return ;
    bzsReloadMainframeWorking = true;
    bzsReloadMainframeLastAccess = opt_data
    // alert(bzsReloadMainframeLastAccess);
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
            bzsReloadMainframeWorking = false;
            return ;
        }
    }, 800);
    return ;
};
$('[data-href]').click(bzsReloadMainframe);

var bzsReloadMainframeSeamless = function(target) {
    // The version that requires no animation (only reload)
    var mainframe_body = $('#container-mainframe');
    if (bzsReloadMainframeWorking)
        return ;
    bzsReloadMainframeWorking = true;
    bzsReloadMainframeLastAccess = target;
    try {
        mainframe_body.load(target, function() {
            $('[data-href]').click(bzsReloadMainframe);
            bzsAdaptContentToSize();
            bzsReloadMainframeWorking = false;
        });
    } catch (exception) {
        bzsReloadMainframeWorking = false;
        return ;
    }
    return ;
};

var bzsReloadMainframeRefresh = function() {
    bzsReloadMainframeSeamless(bzsReloadMainframeLastAccess);
    return ;
}
bzsReloadMainframeRefresh();

/*
 * Form actions
 */
var bzsDialogInputStringLoad = function(title, placeholder, target, uuid) {
    document.getElementById('dialog-input-string-header').innerHTML = title;
    $('#dialog-input-string-body').attr('value', placeholder);
    $('#dialog-input-string-form').attr('action', target);
    $('#dialog-input-string-form').attr('data-uuid', uuid);
    return ;
}
