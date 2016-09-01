
import copy
import re
import threading
import uuid as uuid_package

class Filesystem:
    """This is a virtual filesystem based on a relational PostgreSQL database.
    We might call it a SQLFS. Its tree-topological structure enables it to index
    files and find siblings quickly. Yet without the B-Tree optimization it
    would not be easy to maintain a high performance.
    """
    fs_uuid_idx = dict()
    fs_root     = None
    fs_db       = None
    fs_store    = None
    utils_pkg   = None
    thr_lock    = threading.Lock()

    class fsNode:
        """This is a virtual node on a virtual filesystem SQLFS. The virtual
        node contains the following data:

            uuid        - The unique identifier: This uuid would be the
                          identifier pointing to the directory or the file.
            is_dir      - Whether is a directory or not
            file_name   - The actual file / directory name given by the user
            owner       - A set() of owners in string handles.
            permissions - A dict() of allowed permissions.
            upload_time - The time uploaded / copied / moved to server
            f_uuid      - If a file them this indicates its FileStorage UUID.

        Other data designed to maintain the structure of the node includes:

            master        - The filesystem itself.
            sub_items     - Set of children.
            sub_names_idx - Dictionary of children indexed by name.

        Do process with caution, and use exported methods only.
        """

        file_name     = ''
        is_dir        = False
        owner         = 'kernel'
        permissions   = dict(
            owner_read  = True,
            owner_write = True,
            owner_pass  = False,
            other_read  = False,
            other_write = False,
            other_pass  = False
        )
        uuid          = uuid_package.UUID('00000000-0000-0000-0000-000000000000')
        upload_time   = 0.0
        f_uuid        = uuid_package.UUID('00000000-0000-0000-0000-000000000000')
        sub_items     = set()
        sub_names_idx = dict()

        def __init__(self, is_dir, file_name, owner, uuid_=None, upload_time=None, sub_folders=set(), sub_files=set(), f_uuid=None, master=None):
            """Load tree of all nodes in SQLFS filesystem."""
            # The filesystem / master of the node
            self.master = master
            # Assigning data
            self.is_dir = is_dir
            self.file_name = file_name
            self.owner = owner
            # Generate Universally Unique Identifier
            self.uuid = master.utils_pkg.get_new_uuid(uuid_, master.fs_uuid_idx)
            master.fs_uuid_idx[self.uuid] = self
            # Get upload time
            self.upload_time = upload_time or master.utils_pkg.get_current_time()
            if not self.is_dir:
                self.sub_folders = set()
                self.sub_files = set()
                self.f_uuid = f_uuid
            else:
                # Folder initialization needs to be accounted after init as whole by the main caller
                self.sub_folders = sub_folders # Temporary
                self.sub_files = sub_files # Temporary
            # This is a traversal thing...
            self.parent = None
            self.sub_items = set()
            self.sub_names_idx = dict()
            return
        pass

    def __init__(self, database=None, filestorage=None, utils_package=None):
        """Load files from database, must specify these options or will revoke
        AttributeError:

            database = The database
            filestorage = The file storage which holds handles for files

        Should return nothing elsewise."""
        if not database:
            raise AttributeError('Must provide database')
        if not filestorage:
            raise AttributeError('Must provide file storage handler')
        if not utils_package:
            raise AttributeError('Must provide bzShare utilities')
        self.fs_db     = database
        self.fs_store  = filestorage
        self.utils_pkg = utils_package
        # Testforing items in database for building tree.
        for item in self.fs_db.execute("SELECT uuid, file_name, owner, upload_time, sub_folders, sub_files FROM file_system"):
            # Splitting tuple into parts
            uuid_, file_name, owner, upload_time, sub_folders, sub_files = item
            # Getting sub files which are expensive stored separately
            n_sub_files = set()
            for fil_idx in sub_files:
                # This is where the order goes, BEAWARE
                s_uuid = fil_idx[0]
                s_file_name = fil_idx[1]
                s_owner = set(fil_idx[2].split(';'))
                try:
                    s_upload_time = float(fil_idx[3])
                except:
                    s_upload_time = self.utils_pkg.get_current_time()
                s_f_uuid = uuid_package.UUID(fil_idx[4])
                if s_f_uuid not in self.fs_store.st_uuid_idx:
                    continue
                # Pushing...
                s_file = self.fsNode(False, s_file_name, s_owner, s_uuid, s_upload_time, f_uuid=s_f_uuid, master=self)
                n_sub_files.add(s_file)
                self.fs_uuid_idx[s_uuid] = s_file
            # Getting sub folders as a set but not templating them
            n_sub_folders = set() # Since reference is passed, should not manipulate this further
            for fol_idx in sub_folders:
                n_sub_folders.add(fol_idx)
            fold_elem = self.fsNode(True, file_name, set(owner), uuid_, upload_time, n_sub_folders, n_sub_files, master=self)
            self.fs_uuid_idx[uuid_] = fold_elem
        # Done importing from SQL database, now attempting to refurbish connexions
        for uuid_ in self.fs_uuid_idx:
            item = self.fs_uuid_idx[uuid_]
            if not item.is_dir:
                continue
            # Asserted that it was a folder.
            for n_sub in item.sub_files:
                item.sub_items.add(n_sub)
                item.sub_names_idx[n_sub.file_name] = n_sub
            for n_sub_uuid in item.sub_folders:
                try:
                    n_sub = self.fs_uuid_idx[n_sub_uuid]
                    item.sub_items.add(n_sub)
                    item.sub_names_idx[n_sub.file_name] = n_sub
                except Exception:
                    pass
            del item.sub_files
            del item.sub_folders
        # Fixing parental occlusions
        def iterate_fsnode(node):
            for item in node.sub_items:
                if item.parent:
                    continue
                # Never iterated before
                item.parent = node
                iterate_fsnode(item)
            return
        for uuid_ in self.fs_uuid_idx: # This would fix all nodes...
            item = self.fs_uuid_idx[uuid_]
            iterate_fsnode(item)
        # Finding root and finishing parent connexions
        for uuid_ in self.fs_uuid_idx: # Takes the first element that ever occured to me
            item = self.fs_uuid_idx[uuid_]
            while item.parent:
                item = item.parent
            self.fs_root = item
            break
        else:
            self.__make_root()
        # Traversing root for filename indexing
        def iterate_node_fn(node):
            for item in node.sub_items:
                node.sub_names_idx[item.file_name]
        # All done, finished initialization
        self.thr_lock = threading.Lock()
        if self.thr_lock.locked():
            self.thr_lock.release()
        return

    def __sqlify_fsnode(self, item):
        """Turns a node into SQL-compatible node."""
        n_uuid = item.uuid
        n_file_name = item.file_name
        n_owner = list(item.owner)
        n_upload_time = item.upload_time
        n_sub_folders = list()
        n_sub_files = list()
        for i_sub in item.sub_items:
            if i_sub.is_dir:
                n_sub_folders.append(i_sub.uuid)
            else:
                n_sub_files.append([
                    str(i_sub.uuid),
                    str(i_sub.file_name),
                    ';'.join(i_sub.owner),
                    "%f" % i_sub.upload_time,
                    str(i_sub.f_uuid)
                ])
        # Formatting string
        return (n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files)

    def __update_in_db(self, item):
        """Push updating commit to Database for changes. Does not affect
        nonexistent nodes in Database. Otherwise please use __insert_in_db().

        Operation would not be redirected to insertion because of recursive
        risks that could potentially damage and overflow the process."""
        # This applies to items in the
        # We assert that item should be Node.
        if type(item) == str:
            item = self.__locate(item)
        if not item:
            return False
        # Giving a few but crucial assertions...
        if not item.is_dir:
            item = item.parent
            if not item.is_dir:
                return False # I should raise, by a matter of fact
        # Collecting data
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files = self.__sqlify_fsnode(item)
        # Uploading / committing data
        if not self.fs_db.execute("SELECT uuid FROM file_system WHERE uuid = %s;", (n_uuid,)):
            return False # You already stated this is an updating operation!
        self.fs_db.execute("UPDATE file_system SET file_name = %s, owner = %s, upload_time = %s, sub_folders = %s, sub_files = %s WHERE uuid = %s;", (n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files, n_uuid))
        return True

    def __insert_in_db(self, item):
        """Create filesystem record of directory 'item' inside database. You
        should not insert something that already existed. However:

        We have had a precaution for this. Update operations would be taken
        automatically instead."""
        if not item.is_dir:
            return False # Must be directory...
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders, n_sub_files = self.__sqlify_fsnode(item)
        # Uploading / committing data
        if self.fs_db.execute("SELECT uuid FROM file_system WHERE uuid = %s;", (n_uuid,)):
            return self.__update_in_db(item) # Existed, updating instead.
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES (%s, %s, %s, %s, %s, %s);", (n_uuid, n_file_name, list(n_owner), n_upload_time, n_sub_folders, n_sub_files))
        return

    def __make_root(self):
        item = self.fsNode(True, '', {'kernel'}, master=self)
        del item.sub_files
        del item.sub_folders
        item.sub_items = set()
        item.parent = None
        # Done generation, inserting.
        self.fs_root = item
        self.fs_uuid_idx[item.uuid] = item
        # Inserting to SQL.
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES (%s, %s, %s, %s, %s, %s);", (item.uuid, item.file_name, list(item.owner), item.upload_time, [], []))
        return

    def __locate(self, path, parent=None):
        """Locate the fsNode() of the location 'path'. If 'parent' is given and
        as it should be a fsNode(), the function look to the nodes directly
        under this, non-recursively."""
        # On the case it is a referring location, path should be str.
        if parent:
            try:
                item = parent.sub_names_idx[path]
            except Exception:
                return None
            return item
        # And it is not such a location.
        # We assert that path should be list().
        if type(path) == str:
            path = path.split('/')
            while '' in path:
                path.remove('')
        # Now got array, traversing...
        item = self.fs_root
        while path:
            try:
                item = item.sub_names_idx[path[0]]
            except Exception:
                return None # This object does not exist.
            path = path[1:]
        # Guranteed correctness.
        return item

    def __is_child(self, node, parent):
        """Determines whether node is a child of parent."""
        while node:
            if node == parent:
                return True
            node = node.parent
        return False

    def __make_nice_filename(self, file_name):
        """Create a HTML-friendly file name that does not support and does not
        allow cross site scripting (XSS)."""
        file_name = re.sub(r'[\\/*<>?`\'"|\r\n]', r'', file_name)
        return file_name

    def __resolve_conflict(self, file_name, parent):
        """Rename 'file_name' if necessary in order to make operations
        successful in case of confliction that disrupts the SQLFS. The renamed
        file / folder should be named like this:

        New Text Document.txt
        New Text Document (2).txt
        New Text Document (3).txt

        Et cetera."""
        if type(parent) == str:
            parent = self.__locate(parent)
        if not parent:
            return file_name
        # File path assertion complete, attempting to resolve.
        if file_name not in parent.sub_names_idx:
            return file_name
        # There must have been a conflict.
        if '.' in file_name:
            f_name = re.sub(r'^(.*)\.(.*?)$', r'\1', file_name)
            f_suffix = '.' + re.sub(r'^(.*)\.(.*?)$', r'\2', file_name)
        else:
            f_name = file_name
            f_suffix = ''
        for i in range(2, 10**18):
            n_fn = '%s (%d)%s' % (f_name, i, f_suffix)
            if n_fn not in parent.sub_names_idx:
                return n_fn
        # This should never happen!
        return file_name

    def __mkfile(self, path_parent, file_name, owner, content):
        """Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage."""
        if type(path_parent) == str:
            path_parent = self.__locate(path_parent)
        if not path_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(file_name)
        file_name = self.__resolve_conflict(file_name, path_parent)
        # Finished assertion.
        n_uuid = self.fs_store.new_unique_file(content)
        n_fl = self.fsNode(False, file_name, owner, f_uuid=n_uuid, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self.__update_in_db(path_parent)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def __mkdir(self, path_parent, file_name, owner):
        """Inject folder into filesystem."""
        if type(path_parent) == str:
            path_parent = self.__locate(path_parent)
        if not path_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(file_name)
        file_name = self.__resolve_conflict(file_name, path_parent)
        # Creating new node.
        n_fl = self.fsNode(True, file_name, owner, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self.__update_in_db(path_parent)
        self.__insert_in_db(n_fl)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def __listdir(self, path):
        """Creates a list of files in the directory 'path'. Attributes of the returned
        result contains:

            file-name   - File name
            file-size   - File size
            is-dir      - Whether is directory
            owner       - The handle of the owner
            upload-time - Time uploaded, in float since epoch.

        The result should always be a list, and please index it with your own
        habits or modify the code."""
        if type(path) == str:
            path = self.__locate(path)
            if not path:
                return []
        # List directory, given the list(dict()) result...
        dirs = list()
        for item in path.sub_items:
            attrib = dict()
            try:
                attrib['file-name'] = item.file_name
                attrib['file-size'] = 0 if item.is_dir else self.fs_store.st_uuid_idx[item.f_uuid].size
                attrib['is-dir'] = item.is_dir
                attrib['owner'] = item.owner
                attrib['upload-time'] = item.upload_time
            except:
                continue
            dirs.append(attrib)
        # Give the results to downstream
        return dirs

    def __get_content(self, item):
        """Gets binary content of the object (must be file) and returns the
        actual content in bytes."""
        if type(item) == str:
            item = self.__locate(item)
        if not item:
            return b''
        if item.is_dir:
            item = None
            return b''
        return self.fs_store.get_content(item.f_uuid)

    def __copy_recursive(self, item, target_par, new_owner):
        """Copies content of a single object and recursively call all its
        children for recursive copy, targeted as a child under target_par."""
        # We assert item, target_par are all fsNode().
        target_node = target_par.sub_names_idx[item.file_name]
        for i_sub in item.sub_items:
            i_sub.parent = item
            item.sub_names_idx[i_sub.file_name] = i_sub
            self.__copy_recursive(i_sub, target_node, new_owner)
        # Insert into SQL database
        item.uuid = self.utils_pkg.get_new_uuid(None, self.fs_uuid_idx)
        self.fs_uuid_idx[item.uuid] = item
        item.upload_time = utils.get_current_time()
        if new_owner:
            item.owner = new_owner # Assignment
        if item.is_dir:
            self.__insert_in_db(item)
        return

    def __copy(self, source, target_parent, new_owner=None):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination can be the
        same as source folder. If rename required please call the related
        functions separatedly."""
        if type(source) == str:
            source = self.__locate(source)
        if type(target_parent) == str:
            target_parent = self.__locate(target_parent)
        if not source or not target_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(source.file_name)
        file_name = self.__resolve_conflict(file_name, target_parent)
        # Done assertion, now proceed with deep copy
        target = copy.deepcopy(source)
        # Assigning and finishing tree connexions
        target.file_name = file_name
        target.parent = target_parent
        target_parent.sub_items.add(target)
        target_parent.sub_names_idx[target.file_name] = target
        self.__copy_recursive(target, target_parent, new_owner)
        # Update target_parent data and return
        self.__update_in_db(target_parent)
        return True

    def __move(self, source, target_parent):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination should not
        at all be the same as source folder, otherwise operation would not be
        executed."""
        if type(source) == str:
            source = self.__locate(source)
        if type(target_parent) == str:
            target_parent = self.__locate(target_parent)
        if not source or not target_parent:
            return False
        # It should not move itself to itself.
        if source.parent == target_parent:
            return False
        # Create an environment-friendly file name
        file_name = self.__make_nice_filename(source.file_name)
        file_name = self.__resolve_conflict(file_name, target_parent)
        source.file_name = file_name
        # Moving an re-assigning tree structures
        par = source.parent
        par.sub_items.remove(source)
        del par.sub_names_idx[source.file_name]
        source.parent = target_parent
        target_parent.sub_items.add(source)
        target_parent.sub_names_idx[source.file_name] = source
        # Updating SQL database.
        self.__update_in_db(par)
        self.__update_in_db(target_parent)
        return

    def __remove_recursive(self, item):
        """Removes content of a single object and recursively call all its
        children for recursive removal."""
        # We assert item is fsNode().
        # Remove recursively.
        for i_sub in item.sub_items:
            self.__remove_recursive(i_sub)
        # Delete itself from filesystem.
        del self.fs_uuid_idx[item.uuid]
        # Delete itself from SQL database.
        self.fs_db.execute("DELETE FROM file_system WHERE uuid = %s;", (item.uuid,))
        # Also delete occurence if is file.
        if not item.is_dir:
            self.fs_store.remove_unique_file(item.f_uuid)
        return

    def __remove(self, path):
        """Removes (recursively) all content of the folder / file itself and
        all its subdirectories."""
        if type(path) == str:
            path = self.__locate(path)
        if not path:
            return False
        # Done assertion, path is now fsNode().
        par = path.parent
        self.__remove_recursive(path)
        if par:
            par.sub_items.remove(path)
            del par.sub_names_idx[path.file_name]
            self.__update_in_db(par)
        # There always should be a root.
        if path == self.fs_root:
            self.__make_root()
        # Done removal.
        return True

    def __rename(self, item, file_name):
        """Renames object 'item' into file_name."""
        if type(item) == str:
            item = self.__locate(item)
            if not item:
                return False
        if not item.parent:
            return False # How can you rename a root?
        # Resolving conflict and nicing file name.
        file_name = self.__make_nice_filename(file_name)
        file_name = self.__resolve_conflict(file_name, item.parent)
        # Actually deleting
        del item.parent.sub_names_idx[item.file_name]
        item.file_name = file_name
        item.parent.sub_names_idx[item.file_name] = item
        if item.is_dir:
            self.__update_in_db(item)
        self.__update_in_db(item.parent) # At least there is a parent
        return True

    def __chown(self, item, owner):
        """Assign owner of 'item' to new owner, recursively."""
        if type(item) == str:
            item = self.__locate(item)
        if not item:
            return False
        def _chown_recursive(item_, owner_):
            for sub_ in item_.sub_items:
                _chown_recursive(sub_, owner_)
            item_.owner = owner_
            if item_.is_dir:
                self.__update_in_db(item_)
            return
        _chown_recursive(item, owner)
        if not item.is_dir:
            self.__update_in_db(item.parent)
        return True

    def __chmod(self, item, perm):
        """Assign permission of 'item' to new permission, non recursively. The
        available modes and representations are:

            perm = '  r    w    x    |    r    w     x  '
                         Owners |        Non-owners  |
                   Read  Write  |       Read Write   |
             Effect sub_files <-+ Effect sub_files <-+

        In 'read' mode, sub_files would not be seen if denied access at a parent
            directory.
        In 'write' mode, sub_files would not be writable if and only if it
            itself is not writable or its parent does not allow its writing."""
        if type(item) == str:
            item = self.__locate(item)
        if not item:
            return False
        # Parse permission information
        if len(perm) != 6:
            return False # Does not comply with the basics
        standard = 'rwxrwx'
        indices = ['owner_read', 'owner_write', 'owner_pass',
            'other_read', 'other_write', 'other_pass']
        for i in range(0, 6):
            item.permissions[indices[i]] = perm[i] == standard[i]
        return True

    def __chmod_recursive(self, item, perm):
        """Recursively change permissions."""
        if type(item) == str:
            item = self.__locate(item)
        if not item:
            return False
        # Done assertion.
        result = True
        def _rec_work(item_, perm_):
            for i_sub in item_.sub_items:
                _rec_work(i_sub)
            result = result and self.__chmod(item_, perm_)
        return result

    def __shell(self):
        cwd = self.fs_root
        cuser = {'kernel'}
        cwd_list = ['']
        while True:
            cwd_fl = ''.join((i + '/') for i in cwd_list)
            print('%s@%s %s$ ' % (self.fs_db.connect_params['user'], self.fs_db.connect_params['database'], cwd_fl), end='')
            cmd_input = input()
            cmd = cmd_input.split(' ')
            op = cmd[0]
            if op == 'db':
                db_cmd = cmd_input.split(' ', 1)[1] or ''
                res = self.fs_db.execute(db_cmd)
                print(res)
            elif op == 'ls':
                res = self.list_directory(cwd)
                # Prettify the result
                print('Owner       Upload Time         Size            Filename            ')
                print('--------------------------------------------------------------------')
                for item in res:
                    print('%s%s%s%s' % (str(item['owner']).ljust(12), str(int(item['upload-time'])).ljust(20), str(item['file-size'] if not item['is-dir'] else '').ljust(16), item['file-name']))
                print('Total: %d' % len(res))
                print('')
            elif op == 'cat':
                dest = self.locate(cmd[1], parent=cwd)
                print(bytes(self.get_content(dest)))
            elif op == 'cd':
                if cmd[1] == '..':
                    cwd_dest = cwd.parent
                    if cwd_dest:
                        cwd = cwd_dest
                        cwd_list = cwd_list[:-1]
                else:
                    try:
                        cwd_dest = cwd.sub_names_idx[cmd[1]]
                        if cwd_dest:
                            cwd = cwd_dest
                            cwd_list.append(cmd[1])
                    except:
                        print('Directory "%s" does not exist.' % cmd[1])
                        pass
            elif op == 'chown':
                dest = self.locate(cmd[1], parent=cwd)
                self.change_ownership(dest, {cmd[2]})
            elif op == 'rename':
                dest = self.locate(cmd[1], parent=cwd)
                self.rename(dest, cmd[2])
            elif op == 'mkdir':
                self.create_directory(cwd, cmd[1], cuser)
            elif op == 'mkfile':
                content = b''
                if len(cmd) >= 3:
                    content = cmd[2].encode('utf-8')
                self.create_file(cwd, cmd[1], cuser, content)
            elif op == 'rm':
                self.remove(self.__locate(cmd[1], parent=cwd))
            elif op == 'cp':
                src = self.locate(cmd[1], parent=cwd)
                self.copy(src, cmd[2])
            elif op == 'mv':
                src = self.locate(cmd[1], parent=cwd)
                self.move(src, cmd[2])
            elif op == 'exit':
                break
            else:
                print('Unknown command "%s".' % op)
        return

    """Exported functions that are thread-safe."""

    def locate(self, path, parent=None):
        """Locate the fsNode() of the location 'path'. If 'parent' is given and
        as it should be a fsNode(), the function look to the nodes directly
        under this, non-recursively."""
        self.thr_lock.acquire()
        ret_result = self.__locate(path, parent)
        self.thr_lock.release()
        return ret_result

    def is_child(self, node, parent):
        """Determines whether node is a child of parent."""
        self.thr_lock.acquire()
        ret_result = self.__is_child(node, parent)
        self.thr_lock.release()
        return ret_result

    def create_file(self, path_parent, file_name, owners, content):
        """Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage."""
        self.thr_lock.acquire()
        ret_result = self.__mkfile(path_parent, file_name, owners, content)
        self.thr_lock.release()
        return ret_result

    def create_directory(self, path_parent, file_name, owners):
        """Create directory under path_parent into filesystem."""
        self.thr_lock.acquire()
        ret_result = self.__mkdir(path_parent, file_name, owners)
        self.thr_lock.release()
        return ret_result

    def copy(self, source, target_parent, new_owner=None):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination can be the
        same as source folder. If rename required please call the related
        functions separatedly."""
        self.thr_lock.acquire()
        ret_result = self.__copy(source, target_parent, new_owner)
        self.thr_lock.release()
        return ret_result

    def move(self, source, target_parent):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. Destination should not
        at all be the same as source folder, otherwise operation would not be
        executed."""
        self.thr_lock.acquire()
        ret_result = self.__move(source, target_parent)
        self.thr_lock.release()
        return ret_result

    def remove(self, path):
        """Removes (recursively) all content of the folder / file itself and
        all its subdirectories."""
        self.thr_lock.acquire()
        ret_result = self.__remove(path)
        self.thr_lock.release()
        return ret_result

    def rename(self, path, file_name):
        """Renames object 'path' into file_name."""
        self.thr_lock.acquire()
        ret_result = self.__rename(path, file_name)
        self.thr_lock.release()
        return ret_result

    def change_ownership(self, path, owners):
        """Assign owners of 'path' to new owners, recursively."""
        self.thr_lock.acquire()
        ret_result = self.__chown(path, owners)
        self.thr_lock.release()
        return ret_result

    def change_permissions(self, path, permissions, recursive=False):
        """Assign permissions of 'item' to new permissions. User has the rights
        to determine whether this is done recursively. The available modes and
        representations are:

            perm = '  r    w    x    |    r    w     x  '
                         Owners |        Non-owners  |
                   Read  Write  |       Read Write   |
             Effect sub_files <-+ Effect sub_files <-+

        In 'read' mode, sub_files would not be seen if denied access at a parent
            directory.
        In 'write' mode, sub_files would not be writable if and only if it
            itself is not writable or its parent does not allow its writing."""
        self.thr_lock.acquire()
        if recursive:
            ret_result = self.__chmod(path, permissions)
        else:
            ret_result = self.__chmod_recursive(path, permissions)
        self.thr_lock.release()
        return ret_result

    def list_directory(self, path):
        """Creates a list of files in the directory 'path'. Attributes of the
        returned result contains:

            file-name   - File name
            file-size   - File size
            is-dir      - Whether is directory
            owner       - The handle of the owner
            upload-time - Time uploaded, in float since epoch.

        The result should always be a list, and please index it with your own
        habits or modify the code."""
        self.thr_lock.acquire()
        ret_result = self.__listdir(path)
        self.thr_lock.release()
        return ret_result

    def get_content(self, item):
        """Gets binary content of the object (must be file) and returns the
        actual content in bytes."""
        self.thr_lock.acquire()
        ret_result = self.__get_content()
        self.thr_lock.release()
        return ret_result

    def shell(self):
        """Interactive shell for manipulating SQLFS. May be integrated into
        other utilites in the (far) futuure. Possible commands are:

            db command     - Execute 'command' in Database.
            ls             - List content of current directory.
            cat name       - View binary content of the object 'name'.
            cd             - Change CWD into the given directory, must be
                             relative. Or use '..' to go to parent directory.
            chown src usr  - Change ownership recursively of 'src' to 'usr'.
            rename src nam - Rename file / folder 'src' to 'nam'.
            mkdir name     - Make directory of 'name' under this directory.
            mkfile name dt - Make empty file of 'name' under this directory. If
                             'dt' is specified, then its content would not be
                             empty instead of the specified data.
            rm name        - Remove (recursively) object of 'name' under this
                             directory.
            cp src dest    - Copy object 'src' to under 'dest' as destination.
            mv src dest    - Move object 'src' to under 'dest' as destination.
            exit           - Exit shell.

        This shell should not be used in production as is not safe."""
        self.thr_lock.acquire()
        self.thr_lock.release()
        ret_result = self.__shell()
        return ret_result
    pass
