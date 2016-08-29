
import base64
import binascii
import io
import json
import re
import time
import tornado

from bzs import files
from bzs import const
from bzs import users
from bzs import preproc

# TODO: Remove this!
import os

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
        # Another concurrency blob...
        future = tornado.concurrent.Future()

        def get_final_html_async(target_path):
            # Getting file template.
            file_temp = files.get_static_data('./static/files.html')

            # Retrieving list target.
            try:
                target_path = decode_hexed_b64_to_str(target_path)
            except:
                target_path = '/'
            if not target_path:
                target_path = '/'

            # Getting parental directorial list
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
            for file_name in os.listdir(target_path):
                try: # In case of a permission error.
                    actual_path = target_path + file_name
                    attrib = dict()
                    attrib['file-name'] = file_name
                    attrib['allow-edit'] = True
                    attrib['file-size'] = files.format_file_size(os.path.getsize(actual_path))
                    attrib['owner'] = 'root'
                    attrib['date-uploaded'] = time.ctime(os.path.getctime(actual_path))
                    # Detecting whether is a folder
                    if os.path.isdir(actual_path):
                        attrib['mime-type'] = 'directory/folder'
                    else:
                        attrib['mime-type'] = files.guess_mime_type(file_name)
                    # And access links should differ between folders and files
                    if attrib['mime-type'] == 'directory/folder':
                        attrib['target-link'] = '/files/list/%s' % encode_str_to_hexed_b64(actual_path + '/')
                    else:
                        attrib['target-link'] = '/files/download/%s/%s' % (encode_str_to_hexed_b64(actual_path), file_name)
                    attrib['uuid'] = encode_str_to_hexed_b64(actual_path)
                    files_attrib_list.append(attrib)
                except Exception:
                    pass
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

        # File actually exists, sending data
        try:
            file_handle = open(file_path, 'rb')
        except Exception:
            invoke_404()
            return
        file_data = file_handle.read()
        file_handle.close()
        file_stream = io.BytesIO(file_data)

        self.set_status(200, "OK")
        self.add_header('Cache-Control', 'max-age=0')
        self.add_header('Connection', 'close')
        self.add_header('Content-Type', 'application/x-download')
        self.add_header('Content-Length', str(len(file_data)))

        # Asynchronous web request...
        file_block_size = 64 * 1024 # 64 KiB / Chunk
        file_block = bytes()

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
                    os.system('cp "D:%s" "D:%s"' % (source, target))
            elif action == 'move':
                for source in sources:
                    os.system('mv "D:%s" "D:%s"' % (source, target))
            elif action == 'delete':
                for source in sources:
                    os.system('rm "D:%s"' % source)
            elif action == 'rename':
                os.system('rename "D:%s" "%s"' % (sources, target))
            elif action == 'new-folder':
                os.system('mkdir "D:%s%s"' % (sources, target))
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
        # Another concurrency blob...
        future = tornado.concurrent.Future()

        def save_file_async(alter_ego, target_path, file_name):
            upload_data = alter_ego.request.body
            target_path = decode_hexed_b64_to_str(target_path)
            # Attempting to write to file... otherwise might try to rename until
            # File does not exist.
            def get_non_duplicate_path(file_path):
                if not os.path.exists('D:' + file_path):
                    return file_path
                duplicate = 1
                while duplicate < 101:
                    new_path = re.sub(r'\.(.*?)$', ' (%d).\\1' % duplicate, file_path)
                    if not os.path.exists('D:' + new_path):
                        return new_path
                    duplicate = duplicate + 1
                return ''
            file_path = get_non_duplicate_path(target_path + file_name)
            if not file_path:
                future.set_result('bzs_upload_failure')
                return
            # Committing changes to database
            file_stream = open(file_path, 'wb')
            file_stream.write(upload_data)
            file_stream.close()
            # Final return
            future.set_result('bzs_upload_success')
        tornado.ioloop.IOLoop.instance().add_callback(save_file_async,
            self, target_path, file_name)

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
