
import cgi
import re
import tornado
import urllib

from . import const
from . import users
from . import utils
from . import sqlfs

class PreviewHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, mode, file_hash):
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        # In case it does not exist.
        future = tornado.concurrent.Future()
        def get_index_html_async(working_user, file_hash):
            # Determine file path and file type
            # try:
            file_path = utils.decode_hexed_b64_to_str(file_hash)
            file_name = sqlfs.get_file_name(file_path)
            file_mime = utils.guess_mime_type(file_name)

            # Sorting according to MIME type
            if file_mime == 'application/pdf':
                # PDF documents using pdf.js
                if mode == 'view':
                    file_data = utils.get_static_data('./static/preview_pdf.html')
                else:
                    file_data = utils.get_static_data('./static/pdfjs/viewer.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    file_hash=file_hash,
                    file_name=file_name,
                    file_name_url=urllib.parse.quote(file_name),
                    file_mime=file_mime,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            elif 'text/' in file_mime:
                # Plain text
                file_data = '<h1>(This file is plaintext. <a href="javascript:bzsHistoryRollback()">Click here to go back.</a>)</h1>'
                pass
            elif 'video/' in file_mime or 'audio/' in file_mime:
                # Videos and audios using video.js.
                file_data = utils.get_static_data('./static/preview_video.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    file_hash=file_hash,
                    file_name=file_name,
                    file_name_url=urllib.parse.quote(file_name),
                    file_mime=file_mime,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            elif 'image/' in file_mime:
                # Images using viewer.js.
                if mode == 'view':
                    file_data = utils.get_static_data('./static/preview_image.html')
                else:
                    file_data = utils.get_static_data('./static/viewerjs/viewer.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    file_hash=file_hash,
                    file_name=file_name,
                    file_name_url=urllib.parse.quote(file_name),
                    file_name_escaped=cgi.escape(file_name),
                    file_mime=file_mime,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            else:
                # None of the provided has been detected
                file_data = utils.get_static_data('./static/preview_none.html')
                file_data = utils.preprocess_webpage(file_data, working_user,
                    xsrf_form_html=self.xsrf_form_html()
                )
                pass
            future.set_result(file_data)
        tornado.ioloop.IOLoop.instance().add_callback(
            get_index_html_async, working_user, file_hash)
        file_data = yield future

        # File actually exists, sending data
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.add_header('Content-Length', str(len(file_data)))

        # Push result to client in one blob
        self.write(file_data)
        self.flush()
        self.finish()
        return self

    head=get
    pass
