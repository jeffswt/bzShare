
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
 *  - bzsReloadMainframeCore(url, reverseDirection) // The heart of the following function(s)
 *  - bzsReloadMainframe() // triggered by buttons
 *  - bzsReloadMainframeSeamless(url) // No effects, triggered by scripts
 *  - bzsReloadMainframeRefresh() // No effects, reload the same page
 */
var bzsReloadMainframeWorking = false;
var bzsReloadMainframeLastAccess = '/files';

var bzsReloadMainframeCore = function(url, reverseDirection, noHistory) {
    var mainframe_body = $('#container-mainframe');
    if (bzsReloadMainframeWorking)// ||
            // $(this).data('href') == bzsReloadMainframeLastAccess)
        return ;
    bzsReloadMainframeWorking = true;
    bzsReloadMainframeLastAccess = url;
    // Add event to history
    if (!noHistory) {
        try {
            bzsHistoryList.push(url);
        } catch (exception) {
            bzsHistoryList = [url];
        }
        if (!reverseDirection)
            bzsHistoryAfterList = [];
    }
    // Starting to create animations and load
    if (!reverseDirection)
        mainframe_body.removeClass('fadeInLeft')
            .removeClass('fadeInRight')
            .removeClass('fadeOutRight')
            .addClass('fadeOutLeft');
    else
        mainframe_body.removeClass('fadeInLeft')
            .removeClass('fadeInRight')
            .removeClass('fadeOutLeft')
            .addClass('fadeOutRight');
    setTimeout(function() {
        try {
            mainframe_body.load(url, function() {
                if (!reverseDirection)
                    mainframe_body.removeClass('fadeOutLeft')
                        .removeClass('fadeOutRight')
                        .removeClass('fadeInLeft')
                        .addClass('fadeInRight');
                else
                    mainframe_body.removeClass('fadeOutLeft')
                        .removeClass('fadeOutRight')
                        .removeClass('fadeInRight')
                        .addClass('fadeInLeft');
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

var bzsReloadMainframe = function() {
    var url = $(this).data('href');
    bzsReloadMainframeCore(url, false, false);
}
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
 * History actions
 */
var bzsHistoryList = [bzsReloadMainframeLastAccess];
var bzsHistoryAfterList = [];
var bzsHistoryRollback = function() {
    if (bzsReloadMainframeWorking)
        return false;
    var last_access = ''
    try {
        last_access = bzsHistoryList.pop();
        if (last_access.length <= 0)
            return ;
        bzsHistoryAfterList.push(last_access)
        last_access = bzsHistoryList.pop();
        bzsHistoryList.push(last_access);
        if (last_access.length <= 0)
            return ;
        bzsReloadMainframeCore(last_access, true, true);
    } catch (exception) {
        bzsHistoryList = [bzsReloadMainframeLastAccess]
    }
    return ;
};
var bzsHistoryRollfront = function() {
    if (bzsReloadMainframeWorking)
        return false;
    var last_access = ''
    try {
        // bzsHistoryAfterList.reverse();
        last_access = bzsHistoryAfterList.pop();
        // bzsHistoryAfterList.reverse();
        if (last_access.length <= 0)
            return ;
        bzsHistoryList.push(last_access);
        bzsReloadMainframeCore(last_access, false, true);
    } catch (exception) {
        bzsHistoryList = [bzsReloadMainframeLastAccess]
    }
    return ;
}
$('#navbar-back-button').click(bzsHistoryRollback);
// Touch-devices-only functions.
$('#container-mainframe').on('swiperight', function() {
    bzsHistoryRollback();
    return ;
});
$('#container-mainframe').on('swipeleft', function() {
    bzsHistoryRollfront();
    return ;
});

/*
 * Form actions
 *  - bzsDialogInputStringLoad(title, placeholder, target, uuid): Reload the given
 *    input dialog box with given datum
 */
var bzsDialogInputStringLoadCallback_Action;
var bzsDialogInputStringLoadCallback_DataUuid;
var bzsDialogInputStringLoadCallback_Callback;
var bzsDialogInputStringLoadCallbackFunc = function(event) {
    event.preventDefault();
    bzsDialogInputStringLoadCallback_Callback(
        bzsDialogInputStringLoadCallback_Action,
        bzsDialogInputStringLoadCallback_DataUuid,
        $(this).serializeArray()
    );
    return false;
}
var bzsDialogInputStringLoad = function(title, placeholder, action, uuid, callback) {
    document.getElementById('dialog-input-string-header').innerHTML = title;
    $('#dialog-input-string-body').attr('value', placeholder);
    $('#dialog-input-string-form').attr('action', action);
    $('#dialog-input-string-form').attr('data-uuid', uuid);
    $('#dialog-input-string-form').off('submit');
    $('#dialog-input-string-form').submit(bzsDialogInputStringLoadCallbackFunc);
    bzsDialogInputStringLoadCallback_Action = action;
    bzsDialogInputStringLoadCallback_DataUuid = uuid;
    bzsDialogInputStringLoadCallback_Callback = callback;
    return true;
}

/*
 * Other various tweaks
 */
$(document).ready(function() {
    // This is only a HOTFIX.
    $('.ui-loader').remove();
});
