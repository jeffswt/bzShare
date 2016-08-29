
import psycopg2
import time
import uuid

from bzs import const

def get_current_time():
    datetime.datetime.now(tz=const.get_const('time-zone')

def get_new_uuid(uuid_, uuid_list=None):
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
        self._db = None
        self._cur = None
        return

    def connect(self):
        self._db = psycopg2.connect(**self.connect_params)
        return

    def execute(self, command, **args):
        self._cur = self._db.cursor()
        try:
            self._cur.execute(command, **args)
            final_arr = self._cur.fetchall()
        except psycopg2.Error:
            # We'll take this as granted... though risky.
            final_arr = None
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
        # Create new tables that meet the limits
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
                uuid        CHARACTER VARYING(64),
                file_name   TEXT,
                owner       TEXT,
                upload_time DOUBLE PRECISION,
                sub_folders BIGINT[],
                sub_files   TEXT[][]
            );
            CREATE TABLE file_storage (
                uuid    CHARACTER VARYING(64),
                size    BIGINT,
                count   INTEGER,
                hash    TEXT,
                content BYTEA
            );
        """)
        # Ensure
        # Done!
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
        def __init__(self, uuid_=None, size=0, count=1, hash_=None, master=FileStorage):
            self.master = master
            self.uuid = get_new_uuid(uuid_, self.master.st_uuid_idx)
            self.master.st_uuid_idx[self.uuid] = self
            self.size = size
            self.count = count # The number of references
            self.hash = hash_ # Either way... must specify this!
            self.master.st_hash_list[self.hash] = self
            # Will not contain content, would be indexed in SQL.
            return
        pass

    def load_sql(self, db=Database):
        """Loads index of all stored UniqueFiles in database."""
        self.st_db = db
        for item in self.st_db.execute('SELECT uuid, size, count, hash FROM file_storage;'):
            s_uuid, s_size, s_count, s_hash = item
            s_fl = UniqueFile(s_uuid, s_size, s_count, s_hash, self)
            # Inject into indexer
            st_uuid_idx[s_uuid] = s_fl
            st_hash_idx[s_hash] = s_fl
        return

    def new_unique_file(self, content):
        """Creates a UniqueFile, and returns its UUID in string."""
        n_uuid = get_new_uuid(None, self.st_uuid_idx)
        n_size = len(content)
        n_count = 1
        n_hash = self.hash_algo(content).hexdigest()
        u_fl = UniqueFile(n_uuid, n_size, n_count, n_hash, master=self)
        # Done indexing, now proceeding to process content into SQL
        content = binascii.hexlify(content.encode('utf-8')).decode('ascii')
        self.st_db.execute('INSERT INTO file_storage (uuid, size, count, hash, content) VALUES ("%s", %d, %d, "%s", E"\\\\x%s")' % (n_uuid, n_size, n_count, n_hash, content))
        # Injecting file into main indexer
        st_uuid_idx[n_uuid] = u_fl
        st_hash_idx[n_hash] = u_fl
        return n_uuid
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
        """This is a virtual node on a virtual filesystem SQLFS. The actual node contains
        the following data:

            uuid        - The unique identifier: if node is a directory, then this uuid
                          would be the identifier pointing to the directory; if node is
                          a file, this identifier would be pointing to the UUID among
                          the actual files instead of the filesystem.
            is_dir      - Whether is a directory or not
            filename    - The actual file / directory name given by the user
            upload_time - The time uploaded / copied / moved to server
            children    - A set of fsNode-s, indicating its children

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
            self.upload_time = _upload_time or get_current_time()
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

    def load_sqlfs(self, db=Database):
        self.fs_db = db
        self.fs_db_cur = self.fs_db.cursor()
        for item in self.fs_db_cur.execute("SELECT uuid, file_name, owner, upload_time, sub_folders, sub_files FROM file_system"):
            # Splitting tuple into parts
            uuid_, file_name, owner, upload_time, sub_folders, sub_files = item
            # Getting sub files which are expensive stored separately
            n_sub_files = set()
            for fil_idx in sub_files:
                # This is where the order goes, BEAWARE
                s_uuid = int(fil_idx[0])
                s_file_name = fil_idx[1]
                s_owner = fil_idx[2]
                try:
                    s_upload_time = float(fil_idx[3])
                except:
                    s_upload_time = get_current_time()
                s_f_uuid = fil_idx[4]
                # Pushing...
                s_file = fsNode(False, s_file_name, s_owner, s_uuid, s_upload_time, f_uuid=s_f_uuid, master=self)
                n_sub_files.add(s_file)
                self.fs_uuid_idx[s_uuid] = s_file
            # Getting sub folders as a set but not templating them
            n_sub_folders = set() # Since reference is passed, should not manipulate this further
            for fol_idx in sub_folders:
                n_sub_folders.add(fol_idx)
            fold_elem = fsNode(True, file_name, owner, uuid_, upload_time, n_sub_folders, n_sub_files, master=self)
            self.fs_uuid_idx[uuid_] = fold_elem
        # Done importing from SQL database, now attempting to refurbish connexions
        for uuid_ in self.fs_uuid_idx:
            if not item.is_dir:
                continue
            item = self.fs_uuid_idx[uuid_]
            n_sub_folders = item.sub_folders
            for n_sub in item.sub_files:
                item.sub_items.add(n_sub)
            for n_sub_uuid in n_sub_folders:
                try:
                    item.sub_folders.add(self.fs_uuid_idx[n_sub_uuid])
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
            self.root = item
            break;
        else:
            self.make_root()
        # Traversing root for filename indexing
        def iterate_node_fn(node):
            for item in node.sub_items:
                node.sub_names_idx[item.file_name]
        # All done, finished initialization
        return

    def make_root(self):
        item = fsNode(True, '', 'System', master=self)
        del item.sub_files
        del item.sub_folders
        item.sub_items = set()
        item.parent = None
        # Done generation, inserting.
        self.fs_root = item
        self.fs_uuid_idx[item.uuid] = item
        # FIXME: needs to insert to SQL.
        return

    def locate(self, path):
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
            if i_sub.isdir:
                n_sub_folders.append(i_sub.uuid)
            else:
                s_attr = [
                    str(i_sub.uuid),
                    i_sub.file_name,
                    i_sub.owner,
                    str(i_sub.upload_time),
                    i_sub.f_uuid
                ]
                n_sub_files.append(s_attr)
        n_sub_folders_str = 'ARRAY[' + ', '.join(str(i) for i in n_sub_folders) + ']'
        n_sub_files_str = 'ARRAY[' + ', '.join(('ARRAY[' + ', '.join(str(j) for j in i) + ']') for i in a) + ']'
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
        self.fs_db.execute('UPDATE file_system SET uuid=%d file_name="%s" owner="%s" upload_time=%f sub_folders=%s sub_files=%s;' % (n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str))
        return True

    def _insert_in_db(self, item):
        """Create filesystem record of directory 'item' inside database."""
        if not item.is_dir:
            return False # Must be directory...
        n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str = self._sqlify_fsnode(item)
        # Uploading / committing data
        self.fs_db.execute('INSERT INTO file_system (uuid, file_name, owner, upload_time, sub_folders, sub_files) VALUES (%d, "%s", "%s", %f, %s, %s);' % (n_uuid, n_file_name, n_owner, n_upload_time, n_sub_folders_str, n_sub_files_str))
        return

    def _remove_recursive(self, item):
        """Removes content of a single object and recursively call all its
        children for recursive removal."""
        # We assert item is fsNode().
        # Remove recursively.
        for i_sub in item.sub_items:
            _remove_recursive(i_sub)
        # Delete itself from filesystem.
        del self.fs_uuid_idx[item.uuid]
        # Delete itself from SQL database.
        self.fs_db.execute('DELETE FROM file_system WHERE uuid=%d;' % item.uuid)
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
        self._update_in_db(par)
        return True

    def _copy_recursive(self, item, target_par, new_owner):
        """Copies content of a single object and recursively call all its
        children for recursive copy, targeted as a child under target_par."""
        # We assert item, target_par are all fsNode().
        target_node = target_par.sub_names_idx[item.file_name]
        for i_sub in item.sub_items:
            i_sub.parent = item
            item.sub_names_idx[i_sub.name] = i_sub
            _copy_recursive(i_sub, target_node)
        # Insert into SQL database
        item.uuid = get_new_uuid(None, self.fs_uuid_idx)
        item.upload_time = get_current_time()
        if new_owner:
            item.owner = new_owner # Assignment
        _insert_in_db(item)
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
        target_parent.sub_items.add(target)
        target_parent.sub_names_idx[target.file_name] = target
        # Recursively copy
        _copy_recursive(source, target_parent, new_owner)
        # Update target_parent data and return
        _update_in_db(target_parent)
        return True

    def rename(self, item, file_name):
        """Renames object 'item' into file_name."""
        if type(item) == str:
            item = self.locate(item)
            if not item:
                return False
        item.file_name = file_name
        if item.is_dir:
            _update_in_db(item)
        else:
            _update_in_db(item.parent)
        return True

    def new_file(self, path_parent, file_name, owner, content):
        """Inject object into filesystem, while passing in content. The content
        itself would be indexed in FileStorage."""
        if type(path_parent) == str:
            path_parent = self.locate(path_parent)
            if not path_parent:
                return False
        n_uuid = FileStorage.new_unique_file(content)
        n_fl = fsNode(False, file_name, owner, f_uuid=n_uuid, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_names_idx[file_name] = n_fl
        self._update_in_db(path_parent)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def new_folder(self, path_parent, file_name, owner):
        """Inject folder into filesystem."""
        if type(path_parent) == str:
            path_parent = self.locate(path_parent)
            if not path_parent:
                return False
        n_fl = fsNode(True, file_name, owner, master=self)
        # Updating tree connexions
        n_fl.parent = path_parent
        path_parent.sub_names_idx[file_name] = n_fl
        self._update_in_db(path_parent)
        self._insert_in_db(n_fl)
        # Indexing and return
        self.fs_uuid_idx[n_fl.uuid] = n_fl
        return True

    def listdir(self, path):
        if type(path) == str:
            path = self.locate(path)
            if not path:
                return False
        # List directory, given the list(dict()) result...
        dirs = list()
        for item in path.sub_items:
            attrib = dict()
            try:
                attrib['file-name'] = item.file_name
                attrib['file-size'] = 0 if item.is_dir else FileStorage.st_uuid_idx[item.f_uuid].size
                attrib['owner'] = item.owner
                attrib['date-uploaded'] = item.upload_time
            except:
                continue
            dirs.append(attrib)
        # Give the results to downstream
        return dirs
    pass

Filesystem = FilesystemType()

################################################################################
