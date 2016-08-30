
import base64
import binascii
import cgi
import io
import json
import re
import time
import tornado
import urllib

from bzs import const
from bzs import db
from bzs import files
from bzs import preproc
from bzs import users

def encode_str_to_hexed_b64(data):
    return binascii.b2a_hex(base64.b64encode(data.encode('utf-8'))).decode('utf-8')
def decode_hexed_b64_to_str(data):
    return base64.b64decode(binascii.unhexlify(data.encode('utf-8'))).decode('utf-8')

################################################################################

class FilesListHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, target_path):
        """/files/list/HEXED_BASE64_STRING_OF_PATH/"""
        # Another concurrency blob...
        future = tornado.concurrent.Future()

        def get_final_html_async(target_path):
            # Getting file template.
            file_temp = files.get_static_data('./static/files.html')

            # Retrieving list operation target.
            try:
                target_path = decode_hexed_b64_to_str(target_path)
            except:
                target_path = '/'
            if not target_path:
                target_path = '/'

            # Getting hierarchical file path
            files_hierarchy = target_path.split('/')
            files_hierarchy_list = list()
            while '' in files_hierarchy:
                files_hierarchy.remove('')
            files_hierarchy = [''] + files_hierarchy
            files_hierarchy_cwd = ''
            for i in range(0, len(files_hierarchy)):
                files_hierarchy[i] += '/'
                files_hierarchy_cwd += files_hierarchy[i]
                files_hierarchy_list.append(dict(
                    folder_name=files_hierarchy[i],
                    href_path='/files/list/%s' % encode_str_to_hexed_b64(files_hierarchy_cwd),
                    disabled=(i == len(files_hierarchy) - 1)))
                continue

            # Getting current directory content
            files_attrib_list = list()
            for f_handle in db.Filesystem.listdir(target_path):
                # try:
                    file_name = f_handle['file-name']
                    actual_path = target_path + file_name
                    attrib = dict()
                    attrib['file-name'] = file_name
                    attrib['file-name-url'] = urllib.parse.quote(file_name)
                    attrib['file-name-escaped'] = cgi.escape(file_name)
                    attrib['size'] = f_handle['file-size']
                    attrib['size-str'] = files.format_file_size(attrib['size'])
                    attrib['owner'] = f_handle['owner'] # FIXME: DO NOT USE HANDLE, USE NAME!
                    attrib['date-uploaded'] = time.strftime(const.get_const('time-format'), time.localtime(f_handle['upload-time']))
                    # Encoding MIME types
                    if f_handle['is-dir']:
                        attrib['mime-type'] = 'directory/folder'
                    else:
                        attrib['mime-type'] = files.guess_mime_type(file_name)
                    # Encoding hyperlinks
                    if attrib['mime-type'] == 'directory/folder':
                        attrib['target-link'] = '/files/list/%s' % encode_str_to_hexed_b64(actual_path + '/')
                    else:
                        attrib['target-link'] = '/files/download/%s/%s' % (encode_str_to_hexed_b64(actual_path), attrib['file-name-url'])
                    attrib['uuid'] = encode_str_to_hexed_b64(actual_path)
                    files_attrib_list.append(attrib)
                # except Exception:
                #     pass
            cwd_uuid = encode_str_to_hexed_b64(files_hierarchy_cwd)

            # File actually exists, sending data
            working_user = users.get_user_by_cookie(
                self.get_cookie('user_active_login', default=''))
            file_temp = preproc.preprocess_webpage(file_temp, working_user,
                files_attrib_list=files_attrib_list,
                files_hierarchy_list=files_hierarchy_list,
                cwd_uuid=cwd_uuid)
            future.set_result(file_temp)
        tornado.ioloop.IOLoop.instance().add_callback(get_final_html_async,
            target_path)
        file_temp = yield future

        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_temp)))
        self.write(file_temp)
        self.flush()
        self.finish()
        return self

    head=get
    pass

################################################################################

class FilesDownloadHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'HEAD']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self, file_path, file_name):
        """/files/download/HEXED_BASE64_STRING_OF_PATH/ACTUAL_FILENAME"""
        # Something that I do not wish to write too many times..
        def invoke_404():
            self.set_status(404, "Not Found")
            self._headers = tornado.httputil.HTTPHeaders()
            self.add_header('Content-Length', '0')
            self.flush()
            return

        # Get file location (exactly...)
        try:
            file_path = decode_hexed_b64_to_str(file_path)
        except Exception:
            file_path = ''
        if not file_path:
            invoke_404()
            return

        # Asynchronous web request...
        file_block_size = 64 * 1024 # 64 KiB / Chunk
        file_block = bytes()
        file_data = None

        future = tornado.concurrent.Future()
        def inquire_data_async():
            _tf_data = db.Filesystem.get_content(file_path)
            future.set_result(_tf_data)
        tornado.ioloop.IOLoop.instance().add_callback(inquire_data_async)
        file_data = yield future
        file_stream = io.BytesIO(file_data)

        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'application/x-download')
        self.add_header('Content-Length', str(len(file_data)))

        while file_stream.tell() < len(file_data):
            byte_pos = file_stream.tell()
            # Entry to the concurrency worker
            future = tornado.concurrent.Future()
            # Concurrent worker
            def retrieve_data_async():
                block = file_stream.read(file_block_size)
                future.set_result(block)
            # Injection and pending
            tornado.ioloop.IOLoop.instance().add_callback(retrieve_data_async)
            # Reset or read
            file_block = yield future
            self.write(file_block)
            file_block = None
            self.flush()
        file_block = None
        self.finish()

        # Release memory...
        file_stream = None
        file_data = None
        return self

    head=get
    pass

################################################################################

class FilesOperationHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['POST']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self):
        """/files/operation/"""
        # Another concurrency blob...
        future = tornado.concurrent.Future()

        def get_final_html_async():
            operation_content_raw = self.request.body
            operation_content = json.loads(operation_content_raw.decode('utf-8', 'ignore'))
            action = operation_content['action']
            sources = operation_content['source']
            if type(sources) == list:
                for i in range(0, len(sources)):
                    try:
                        sources[i] = decode_hexed_b64_to_str(sources[i])
                    except:
                        pass
            else:
                sources = decode_hexed_b64_to_str(sources)
            if action in ['copy', 'move']:
                try:
                    target = decode_hexed_b64_to_str(operation_content['target'])
                except:
                    target = '/'
            elif action in ['rename', 'new-folder']:
                try:
                    target = operation_content['target']
                except:
                    target = sources # I am not handling more exceptions as this is brutal enough
            # Done assigning values, now attempting to perform operation
            if action == 'copy':
                for source in sources:
                    db.Filesystem.copy(source, target, new_owner='user-cp')
            elif action == 'move':
                for source in sources:
                    db.Filesystem.move(source, target)
            elif action == 'delete':
                for source in sources:
                    db.Filesystem.remove(source)
            elif action == 'rename':
                db.Filesystem.rename(sources, target)
            elif action == 'new-folder':
                db.Filesystem.mkdir(sources, target, 'user-nf')
            future.set_result('')
        tornado.ioloop.IOLoop.instance().add_callback(get_final_html_async)
        file_temp = yield future

        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(file_temp)))
        self.write(file_temp)
        self.flush()
        self.finish()
        return self
    pass

################################################################################

class FilesUploadHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['POST']

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self, target_path, file_name):
        """/files/upload/HEXED_BASE64_STRING_OF_PATH_OF_PARENT/ACTUAL_FILENAME"""
        # Another concurrency blob...
        future = tornado.concurrent.Future()
        working_user = users.get_user_by_cookie(
            self.get_cookie('user_active_login', default=''))

        def save_file_async(alter_ego, target_path, file_name, working_user):
            upload_data = alter_ego.request.body
            # Crucial, to release data.
            alter_ego.request.body = None
            target_path = decode_hexed_b64_to_str(target_path)
            # Committing changes to database
            db.Filesystem.mkfile(target_path, file_name, working_user.username, upload_data)
            # Final return
            future.set_result('bzs_upload_success')
        tornado.ioloop.IOLoop.instance().add_callback(save_file_async,
            self, target_path, file_name, working_user)

        response_temp = yield future
        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'text/html')
        self.add_header('Content-Length', str(len(response_temp)))
        self.write(response_temp)
        self.flush()
        self.finish()
        return self
    pass
