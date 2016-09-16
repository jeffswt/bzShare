
import socket
import threading
import tornado

import tornado.concurrent
import tornado.httputil
import tornado.httpserver
import tornado.gen
import tornado.ioloop
import tornado.process
import tornado.web

from . import const
from . import db
from . import utils

from . import module_error404
from . import module_files
from . import module_home
from . import module_index
from . import module_preview
from . import module_settings
from . import module_static
from . import module_user

WEB_PORT = 80

def main():
    print('Done pre-loading, snapping into main module.')
    # Creating web application
    web_app = tornado.web.Application([
            (r'^/$', module_index.MainframeHandler),
            (r'/static/(.*)$', module_static.StaticHandler),
            # (r'/static/(.*)', tornado.web.StaticFileHandler, {
            #     "path": "./static/" # Optimized static file handler with cache
            # }),
            (r'^/home/?', module_home.HomeHandler),
            (r'^/files/?()$', module_files.FilesListHandler),
            (r'^/files/list/(.*)/?', module_files.FilesListHandler),
            (r'^/files/download/(.*)/(.*)/?$', module_files.FilesDownloadHandler),
            (r'^/files/upload/(.*)/(.*)/?$', module_files.FilesUploadHandler),
            (r'^/files/operation/?', module_files.FilesOperationHandler),
            (r'^/preview/(.*?)/(.*)/?$', module_preview.PreviewHandler),
            (r'^/user/(.*)/?$', module_user.UserActivityHandler),
            (r'^/user_avatar/(.*)/?$', module_user.UserAvatarHandler),
            (r'^/settings/profile/(.*)/?$', module_settings.ProfileHandler),
            (r'^/settings/profile_edit/(.*)/?$', module_settings.ProfileEditHandler),
            (r'^/settings/usergroups/?$', module_settings.UsergroupHandler),
            (r'^/settings/usergroups_edit/(.*)/?$', module_settings.UsergroupEditHandler),
            (r'^/settings/dynamic-interface/?$', module_settings.DynamicInterfaceHandler),
            (r'^/settings/dynamic-interface_edit/(.*)/?$', module_settings.DynamicInterfaceHandler),
            (r'.*', module_error404.Error404Handler)
        ],
        xsrf_cookies=False, # True to prevent CSRF third party attacks
        compress_response=True # True to support GZIP encoding when transferring data
    )
    # Starting server
    web_sockets = tornado.netutil.bind_sockets(
        const.get_const('server-port'),
        family=socket.AF_INET)
    if const.get_const('server-threads') > 1:
        if hasattr(os, 'fork'):
            # os.fork() operation unavailable on Windows.
            tornado.process.fork_processes(const.get_const('server-threads') - 1)
    web_server = tornado.httpserver.HTTPServer(web_app,
        max_body_size=const.get_const('max-body-size'),
        xheaders=True)
    web_server.add_sockets(web_sockets)
    # Boot I/O thread for asynchronous purposes
    tornado.ioloop.IOLoop.instance().start()
    return
