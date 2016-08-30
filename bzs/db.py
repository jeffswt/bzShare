
import binascii
import copy
import datetime
import hashlib
import psycopg2
import pytz
import time
import uuid

from bzs import const

def get_current_time():
    """Gets the current time, in float since epoch."""
    # return datetime.datetime.now(tz=pytz.timezone(const.get_const('time-zone')))
    return float(time.time())

def get_new_uuid(uuid_, uuid_list=None):
    """Creates a new UUID that is not in 'uuid_list' if given."""
    if not uuid_:
        uuid_ = uuid.uuid4().hex
        if type(uuid_list) in [set, dict]:
            while uuid_ in uuid_list:
                uuid_ = uuid.uuid4().hex
    return uuid_

################################################################################

class DatabaseType:
    def __init__(self):
        self.connect_params = dict(
            database=const.get_const('db-name'),
            user=const.get_const('db-user'),
            password=const.get_const('db-password'),
            host=const.get_const('db-host-addr'),
            port=const.get_const('db-host-port')
        )
        self._db = psycopg2.connect(**self.connect_params)
        self._cur = None
        return

    def execute(self, command, **args):
        self._cur = self._db.cursor()
        try:
            self._cur.execute(command, **args)
            final_arr = self._cur.fetchall()
        except psycopg2.ProgrammingError:
            # We'll take this as granted... though risky.
            final_arr = None
        self._db.commit()
        self._cur.close()
        return final_arr

    def init_db(self):
        # Purge database of obsolete tables
        self.execute("""
            DROP TABLE core;
        """)
        self.execute("""
            DROP TABLE users;
        """)
        self.execute("""
            DROP TABLE file_system;
        """)
        self.execute("""
            DROP TABLE file_storage;
        """)
        # Creating new tables in order to function
        self.execute("""
            CREATE TABLE core (
                index   TEXT,
                data    BYTEA
            );
            CREATE TABLE users (
                handle          TEXT,
                password        TEXT,
                usergroups      TEXT,
                ip_address      TEXT[],
                events          TEXT[],
                usr_name        TEXT,
                usr_description TEXT,
                usr_email       TEXT,
                usr_followers   TEXT[],
                usr_friends     TEXT[]
            );
            CREATE TABLE file_system(
                uuid        TEXT,
                file_name   TEXT,
                owner       TEXT,
                upload_time DOUBLE PRECISION,
                sub_folders TEXT[],
                sub_files   TEXT[][]
            );
            CREATE TABLE file_storage (
                uuid    TEXT,
                size    BIGINT,
                count   BIGINT,
                hash    TEXT,
                content BYTEA
            );
        """)
        return
    pass

Database = DatabaseType()

################################################################################

class FileStorageType:
    st_uuid_idx = dict()
    st_hash_idx = dict()
    # Database entry
    st_db = Database
    # Hashing algorithm, could be md5, sha1, sha224, sha256, sha384, sha512
    # sha384 and sha512 are not recommended due to slow speeds on 32-bit computers
    hash_algo = hashlib.sha256

    class UniqueFile:
        def __init__(self, uuid_=None, size=0, count=1, hash_=None, master=None):
            self.master = master
            self.uuid = get_new_uuid(uuid_, self.master.st_uuid_idx)
            self.master.st_uuid_idx[self.uuid] = self
            self.size = size
            self.count = count # The number of references
            self.hash = hash_ # Either way... must specify this!
            self.master.st_hash_idx[self.hash] = self
            # Will not contain content, would be indexed in SQL.
            return
        pass

    def __init__(self, db=Database):
        return self.load_sql(db)

    def load_sql(self, db=Database):
        """Loads index of all stored UniqueFiles in database."""
        self.st_db = db
        for item in self.st_db.execute("SELECT uuid, size, count, hash FROM file_storage;"):
            s_uuid, s_size, s_count, s_hash = item
            s_fl = self.UniqueFile(s_uuid, s_size, s_count, s_hash, self)
            # Inject into indexer
            self.st_uuid_idx[s_uuid] = s_fl
            self.st_hash_idx[s_hash] = s_fl
        return

    def new_unique_file(self, content):
        """Creates a UniqueFile, and returns its UUID in string."""
        n_uuid = get_new_uuid(None, self.st_uuid_idx)
        n_size = len(content)
        n_count = 1
        n_hash = self.hash_algo(content).hexdigest()
        u_fl = self.UniqueFile(n_uuid, n_size, n_count, n_hash, master=self)
        # Done indexing, now proceeding to process content into SQL
        content = binascii.hexlify(content).decode('ascii')
        # self.st_db.execute('INSERT INTO file_storage (uuid, size, count, hash, content) VALUES ("%s", %d, %d, "%s", E"\\\\x%s");' % (n_uuid, n_size, n_count, n_hash, content))
        self.st_db.execute("INSERT INTO file_storage (uuid, size, count, hash, content) VALUES ('%s', %d, %d, '%s', E'\\x%s');" % (n_uuid, n_size, n_count, n_hash, content))
        # Injecting file into main indexer
        self.st_uuid_idx[n_uuid] = u_fl
        self.st_hash_idx[n_hash] = u_fl
        return n_uuid

    def get_content(self, uuid_):
        try:
            u_fl = self.st_uuid_idx[uuid_]
        except Exception:
            return b''
        # Got file handle, now querying file data
        content = self.st_db.execute("SELECT content FROM file_storage WHERE uuid = '%d';" % uuid_)
        return content
    pass

FileStorage = FileStorageType()

################################################################################

class FilesystemType:
    """This is a virtual filesystem based on a relational PostgreSQL database.
    We might call it a SQLFS. Its tree-topological structure enables it to index
    files and find siblings quickly. Yet without the B-Tree optimization it would
    not be easy to maintain a high performance.
    """
    fs_uuid_idx = dict()
    fs_root = None
    fs_db = None

    class fsNode:
        """This is a virtual node on a virtual filesystem SQLFS. The virtual node contains
        the following data:

            uuid        - The unique identifier: if node is a directory, then this uuid
                          would be the identifier pointing to the directory; if node is
                          a file, this identifier would be pointing to the UUID among
                          the actual files instead of the filesystem.
            is_dir      - Whether is a directory or not
            filename    - The actual file / directory name given by the user
            upload_time - The time uploaded / copied / moved to server
            f_uuid      - If a file them this indicates its FileStorage UUID.

        Other data designed to maintain the structure of the node includes:

            master        - The filesystem itself.
            sub_folder    - Removed after filesystem init, temporary use only.
            sub_files     - Removed after filesystem init, temporary use only.
            sub_items     - Set of children.
            sub_names_idx - Contains same data as sub_items, but indexed by name.

        Do process with caution, and use exported methods only.
        """

        def __init__(self, is_dir, file_name, owner, uuid_=None, upload_time=None, sub_folders=set(), sub_files=set(), f_uuid=None, master=None):
            # The filesystem / master of the node
            self.master = master
            # Assigning data
            self.is_dir = is_dir
            self.file_name = file_name
            self.owner = owner
            # Generate Universally Unique Identifier
            self.uuid = get_new_uuid(uuid_, master.fs_uuid_idx)
            master.fs_uuid_idx[self.uuid] = self
            # Get upload time
            self.upload_time = upload_time or get_current_time()
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

    def __init__(self, db=Database):
        return self.load_sqlfs(db)

    def load_sqlfs(self, db=Database):
        self.fs_db = db
        for item in self.fs_db.execute("SELECT uuid, file_name, owner, upload_time, sub_folders, sub_files FROM file_system"):
            # Splitting tuple into parts
            uuid_, file_name, owner, upload_time, sub_folders, sub_files = item
            # Getting sub files which are expensive stored separately
            n_sub_files = set()
            for fil_idx in sub_files:
                # This is where the order goes, BEAWARE
                s_uuid = fil_idx[0]
                s_file_name = fil_idx[1]
                s_owner = fil_idx[2]
                try:
                    s_upload_time = float(fil_idx[3])
                except:
                    s_upload_time = get_current_time()
                s_f_uuid = fil_idx[4]
                # Pushing...
                s_file = self.fsNode(False, s_file_name, s_owner, s_uuid, s_upload_time, f_uuid=s_f_uuid, master=self)
                n_sub_files.add(s_file)
                self.fs_uuid_idx[s_uuid] = s_file
            # Getting sub folders as a set but not templating them
            n_sub_folders = set() # Since reference is passed, should not manipulate this further
            for fol_idx in sub_folders:
                n_sub_folders.add(fol_idx)
            fold_elem = self.fsNode(True, file_name, owner, uuid_, upload_time, n_sub_folders, n_sub_files, master=self)
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
            self.make_root()
        # Traversing root for filename indexing
        def iterate_node_fn(node):
            for item in node.sub_items:
                node.sub_names_idx[item.file_name]
        # All done, finished initialization
        return

    def make_root(self):
        item = self.fsNode(True, '', 'System', master=self)
        del item.sub_files
        del item.sub_folders
        item.sub_items = set()
        item.parent = None
        # Done generation, inserting.
        self.fs_root = item
        self.fs_uuid_idx[item.uuid] = item
        # Inserting to SQL.
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES ('%s', '%s', '%s', %f, '{}', '{}');" % (item.uuid, item.file_name, item.owner, item.upload_time))
        return

    def locate(self, path, parent=None):
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
        return item

    def _sqlify_fsnode(self, item):
        n_uuid = item.uuid
        n_file_name = item.file_name
        n_owner = item.owner
        n_upload_time = item.upload_time
        n_sub_folders = list()
        n_sub_files = list()
        for i_sub in item.sub_items:
            if i_sub.is_dir:
                n_sub_folders.append("\"%s\"" % i_sub.uuid)
            else:
                s_attr = "{%s, %s, %s, %s, %s}" % (
                    "\"%s\"" % i_sub.uuid,
                    "\"%s\"" % i_sub.file_name,
                    "\"%s\"" % i_sub.owner,
                    "\"%f\"" % i_sub.upload_time,
                    "\"%s\"" % i_sub.f_uuid
                )
                n_sub_files.append(s_attr)
        # Formatting string
        n_sub_folders_str = "'{" + ", ".join(i for i in n_sub_folders) + "}'"
        n_sub_files_str = "'{" + ", ".join(i for i in n_sub_files) + "}'"
        return (n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str)

    def _update_in_db(self, item):
        # This applies to items in the
        # We assert that item should be Node.
        if type(item) == str:
            item = self.locate(item)
        if not item:
            return False
        # Giving a few but crucial assertions...
        if not item.is_dir:
            item = item.parent
            if not item.is_dir:
                return False # I should raise, by a matter of fact
        # Collecting data
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str = self._sqlify_fsnode(item)
        # Uploading / committing data
        command = "UPDATE file_system SET file_name = '%s', owner = '%s', upload_time = %f, sub_folders = %s, sub_files = %s WHERE uuid = '%s';" % (n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str, n_uuid)
        self.fs_db.execute(command)
        return True

    def _insert_in_db(self, item):
        """Create filesystem record of directory 'item' inside database."""
        if not item.is_dir:
            return False # Must be directory...
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str = self._sqlify_fsnode(item)
        # Uploading / committing data
        self.fs_db.execute("INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES ('%s', '%s', '%s', %f, %s, %s);" % (n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str))
        return

    def get_content(self, item):
        """Gets binary content of the object (must be file) and returns the actual
        content in bytes."""
        if type(item) == str:
            item = self.locate(item)
        if not item:
            return b''
        if item.is_dir:
            return b''
        return FileStorage.get_content(item.f_uuid)

    def _remove_recursive(self, item):
        """Removes content of a single object and recursively call all its
        children for recursive removal."""
        # We assert item is fsNode().
        # Remove recursively.
        for i_sub in item.sub_items:
            self._remove_recursive(i_sub)
        # Delete itself from filesystem.
        del self.fs_uuid_idx[item.uuid]
        # Delete itself from SQL database.
        self.fs_db.execute("DELETE FROM file_system WHERE uuid = '%s';" % item.uuid)
        return

    def remove(self, path):
        """Removes (recursively) all content of the folder / file itself and
        all its subdirectories."""
        if type(path) == str:
            path = self.locate(path)
            if not path:
                return False
        # Done assertion, path is now fsNode().
        par = path.parent
        self._remove_recursive(path)
        if par:
            par.sub_items.remove(path)
            del par.sub_names_idx[path.file_name]
            self._update_in_db(par)
        return True

    def _copy_recursive(self, item, target_par, new_owner):
        """Copies content of a single object and recursively call all its
        children for recursive copy, targeted as a child under target_par."""
        # We assert item, target_par are all fsNode().
        target_node = target_par.sub_names_idx[item.file_name]
        for i_sub in item.sub_items:
            i_sub.parent = item
            item.sub_names_idx[i_sub.file_name] = i_sub
            self._copy_recursive(i_sub, target_node, new_owner)
        # Insert into SQL database
        item.uuid = get_new_uuid(None, self.fs_uuid_idx)
        self.fs_uuid_idx[item.uuid] = item
        item.upload_time = get_current_time()
        if new_owner:
            item.owner = new_owner # Assignment
        if item.is_dir:
            self._insert_in_db(item)
        return

    def copy(self, source, target_parent, new_owner=None):
        """Copies content of 'source' (recursively) and hang the target object
        that was copied under the node 'target_parent'. If rename required please call
        the related functions separatedly."""
        if type(source) == str:
            source = self.locate(source)
        if type(target_parent) == str:
            target_parent = self.locate(target_parent)
        if not source or not target_parent:
            return False
        # Done assertion, now proceed with deep copy
        target = copy.deepcopy(source)
        target.parent = target_parent
        target_parent.sub_items.add(target)
        target_parent.sub_names_idx[target.file_name] = target
        self._copy_recursive(target, target_parent, new_owner)
        # Update target_parent data and return
        self._update_in_db(target_parent)
        return True

    def move(self, source, target_parent):
        if type(source) == str:
            source = self.locate(source)
        if type(target_parent) == str:
            target_parent = self.locate(target_parent)
        if not source or not target_parent:
            return False
        # Moving an re-assigning tree structures
        par = source.parent
        par.sub_items.remove(source)
        del par.sub_names_idx[source.file_name]
        source.parent = target_parent
        target_parent.sub_items.add(source)
        target_parent.sub_names_idx[source.file_name] = source
        # Updating SQL database.
        self._update_in_db(par)
        self._update_in_db(target_parent)
        return

    def rename(self, item, file_name):
        """Renames object 'item' into file_name."""
        if type(item) == str:
            item = self.locate(item)
            if not item:
                return False
        if item.parent:
            del item.parent.sub_names_idx[item.file_name]
            item.file_name = file_name
            item.parent.sub_names_idx[item.file_name] = item
        if item.is_dir:
            self._update_in_db(item)
        else:
            self._update_in_db(item.parent)
        return True

    def chown(self, item, owner):
        """Assign owner of 'item' to new owner, recursively."""
        if type(item) == str:
            item = self.locate(item)
            if not item:
                return False
        def _chown_recursive(item_, owner_):
            for sub_ in item_.sub_items:
                _chown_recursive(sub_, owner_)
            item_.owner = owner_
            if item_.is_dir:
                self._update_in_db(item_)
            return
        _chown_recursive(item, owner)
        if not item.is_dir:
            self._update_in_db(item.parent)
        return True

    def mkfile(self, path_parent, file_name, owner, content):
        """Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage."""
        if type(path_parent) == str:
            path_parent = self.locate(path_parent)
            if not path_parent:
                return False
        n_uuid = FileStorage.new_unique_file(content)
        n_fl = self.fsNode(False, file_name, owner, f_uuid=n_uuid, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self._update_in_db(path_parent)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def mkdir(self, path_parent, file_name, owner):
        """Inject folder into filesystem."""
        if type(path_parent) == str:
            path_parent = self.locate(path_parent)
            if not path_parent:
                return False
        n_fl = self.fsNode(True, file_name, owner, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_items.add(n_fl)
        path_parent.sub_names_idx[file_name] = n_fl
        self._update_in_db(path_parent)
        self._insert_in_db(n_fl)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def listdir(self, path):
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
            path = self.locate(path)
            if not path:
                return []
        # List directory, given the list(dict()) result...
        dirs = list()
        for item in path.sub_items:
            attrib = dict()
            # try:
            attrib['file-name'] = item.file_name
            attrib['file-size'] = 0 if item.is_dir else FileStorage.st_uuid_idx[item.f_uuid].size
            attrib['is-dir'] = item.is_dir
            attrib['owner'] = item.owner
            attrib['upload-time'] = item.upload_time
            # except:
            #     continue
            dirs.append(attrib)
        # Give the results to downstream
        return dirs

    def shell(self):
        """Interactive shell for manipulating SQLFS. May be integrated into other
        utilites in the (far) futuure. Possible commands are:

            ls             - List content of current directory.
            cat name       - View binary content of the object 'name'.
            cd             - Change CWD into the given directory, must be relative.
                             or use '..' to go to parent directory.
            chown src usr  - Change ownership (recursively) of object 'src' to 'usr'.
            rename src nam - Rename file / folder 'src' to 'nam'.
            mkdir name     - Make directory of 'name' under this directory.
            mkfile name    - Make empty file of 'name' under this directory.
            rm name        - Remove (recursively) object of 'name' under this directory.
            cp src dest    - Copy object 'src' to under 'dest (actual)' as destination.
            mv src dest    - Move object 'src' to under 'dest (actual)' as destination.
            q              - Exit shell.

        Would be done in a infinite loop. Use 'q' to leave."""
        cwd = self.fs_root
        cuser = 'system'
        cwd_list = ['']
        while True:
            cwd_fl = ''.join((i + '/') for i in cwd_list)
            print('root@postgres %s$ ' % cwd_fl, end='')
            cmd_input = input()
            cmd = cmd_input.split(' ')
            op = cmd[0]
            if op == 'ls':
                res = self.listdir(cwd)
                # Prettify the result
                print('Owner       Upload Time         Size            Filename            ')
                print('--------------------------------------------------------------------')
                for item in res:
                    print('%s%s%s%s' % (item['owner'].ljust(12), str(int(item['upload-time'])).ljust(20), str(item['file-size'] if not item['is-dir'] else '').ljust(16), item['file-name']))
                print('Total: %d' % len(res))
                print('')
            elif op == 'cat':
                dest = self.locate(cmd[1], parent=cwd)
                print(self.get_content(dest))
            elif op == 'cd':
                if cmd[1] == '..':
                    cwd_dest = cwd.parent
                    if cwd_dest:
                        cwd = cwd_dest
                        cwd_list = cwd_list[:-1]
                else:
                    cwd_dest = cwd.sub_names_idx[cmd[1]]
                    if cwd_dest:
                        cwd = cwd_dest
                        cwd_list.append(cmd[1])
            elif op == 'chown':
                dest = self.locate(cmd[1], parent=cwd)
                self.chown(dest, cmd[2])
            elif op == 'rename':
                dest = self.locate(cmd[1], parent=cwd)
                self.rename(dest, cmd[2])
            elif op == 'mkdir':
                self.mkdir(cwd, cmd[1], cuser)
            elif op == 'mkfile':
                self.mkfile(cwd, cmd[1], cuser, b'')
            elif op == 'rm':
                self.remove(self.locate(cmd[1], parent=cwd))
            elif op == 'cp':
                src = self.locate(cmd[1], parent=cwd)
                self.copy(src, cmd[2])
            elif op == 'mv':
                src = self.locate(cmd[1], parent=cwd)
                self.move(src, cmd[2])
            elif op == 'q':
                break
            else:
                print('Unknown command "%s".' % op)
        return
    pass

Filesystem = FilesystemType()

################################################################################
