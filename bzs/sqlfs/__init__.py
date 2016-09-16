
import re

from . import file_storage
from . import file_system
from . import file_system_permissions

from .. import db
from .. import utils

# Initialize file storage system

FileStorage = file_storage.FileStorage(
    database      = db.Database,
    utils_package = utils)

# Initialize filesystem

Filesystem = file_system.Filesystem(
    database      = db.Database,
    filestorage   = FileStorage,
    utils_package = utils)

# Initialize permission manager

FilesystemPermissions = file_system_permissions.FilesystemPermissions(
    filesystem = Filesystem)

################################################################################
# Exported file-system functions, permission-safe.

def create_file_handle(mode='read', est_length=1024**8, obj_oid=0, obj_data=b''):
    """Returns a new file stream object which does nothing to the filesystem
    unless been invoked to be injected into filesystem."""
    return file_stream.FileStream(
        mode=mode,
        est_length=est_length,
        obj_oid=obj_oid,
        obj_data=obj_data,
        database=db.Database)
    pass

def create_file(path_parent, file_name, content_stream, user=None):
    """Inject object into filesystem, while passing in content. The content
    itself would be indexed in FileStorage. If 'path-parent' is not writable,
    then the creation would be denied."""
    if user and not FilesystemPermissions.writable(path_parent, user):
        return False
    usr_handle = user.handle if user else 'public'
    ret_result = Filesystem.create_file(path_parent, file_name, usr_handle, content_stream)
    return ret_result

def create_directory(path_parent, file_name, user=None):
    """Create directory under path_parent into filesystem. If 'path-parent' is
    not writable, then the creation would be denied."""
    if user and not FilesystemPermissions.writable(path_parent, user):
        return False
    usr_handle = user.handle if user else 'public'
    ret_result = Filesystem.create_directory(path_parent, file_name, usr_handle)
    return ret_result

def copy(source, target_parent, user=None):
    """Copies content of 'source' (recursively) and hang the target object
    that was copied under the node 'target_parent'. Destination can be the
    same as source folder."""
    if user and not FilesystemPermissions.readable(source, user):
        return False
    if user and not FilesystemPermissions.writable(target_parent, user):
        return False
    ret_result = Filesystem.copy_with_handle(source, target_parent, new_owner=None)
    if user:
        FilesystemPermissions.copy_reown(ret_result, user)
    return True if ret_result != None else False

def move(source, target_parent, user=None):
    """Moves content of 'source' (recursively) and hang the target object
    that was moved under the node 'target_parent'. Destination should not
    at all be the same as source folder, otherwise operation would not be
    executed."""
    if user and not FilesystemPermissions.readable(source, user):
        return False
    if user and not FilesystemPermissions.writable_all(source, user):
        return False
    if user and not FilesystemPermissions.writable_self(source, user):
        return False
    if user and not FilesystemPermissions.writable(target_parent, user):
        return False
    ret_result = Filesystem.move(source, target_parent)
    if user:
        FilesystemPermissions.copy_reown(ret_result, user)
    return ret_result

def remove(path, user=None):
    """Removes (recursively) all content of the folder / file itself and
    all its subdirectories. Must have read and write access."""
    if user and not FilesystemPermissions.readable(path, user):
        return False
    if user and not FilesystemPermissions.writable_self(path, user):
        return False
    if user and not FilesystemPermissions.writable_all(path, user):
        return False
    ret_result = Filesystem.remove(path)
    return ret_result

def rename(path, file_name, user=None):
    """Renames object 'path' into file_name. Must have read and write access."""
    if user and not FilesystemPermissions.read_writable(path, user):
        return False
    if user and not FilesystemPermissions.writable_self(path, user):
        return False
    ret_result = Filesystem.rename(path, file_name)
    return ret_result

def change_ownership(path, owner, user=None):
    """Assign owner of 'path' to new owner, recursively. Must have both read
    and write access to itself and all subfiles."""
    if user and not FilesystemPermissions.read_writable_all(path, user):
        return False
    if user and not FilesystemPermissions.writable_self(path, user):
        return False
    ret_result = Filesystem.change_ownership(path, owner)
    return ret_result

def change_permissions(path, permissions, recursive=False, user=None):
    """Assign permissions of 'item' to new permissions. User has the rights
    to determine whether this is done recursively. The available modes and
    representations are:

        perm = '  r    w    x  '
               Read  Write  Effect sub_files
        For each user there is an individual 'perm' string / dict().

    In 'read' mode, sub_files would not be seen if denied access at a parent
        directory.
    In 'write' mode, sub_files would not be writable if and only if it
        itself is not writable or its parent does not allow its writing."""
    if user and not FilesystemPermissions.read_writable_all(path, user):
        return False
    if user and not FilesystemPermissions.writable_self(path, user):
        return False
    ret_result = Filesystem.change_permissions(path, permissions, recursive)
    return ret_result

def expunge_user_ownership(handle):
    """Must only be called from kernel / system, used when removing a usergroup
    or a user. Its ownership is expunged from the system, and replaced by the
    file node's parent."""
    ret_result = Filesystem.expunge_user_ownership(handle)
    return ret_result

def list_directory(path, user=None):
    """Creates a list of files in the directory 'path'. Attributes of the
    returned result contains:

        file-name   - File name
        file-size   - File size
        is-dir      - Whether is directory
        owner       - The handle of the owner
        upload-time - Time uploaded, in float since epoch.
        writable    - Whether the user has write access to this object.

    The result should always be a list, and please index it with your own
    habits or modify the code."""
    fil_ls = Filesystem.list_directory(path)
    ret_result = list()
    for item in fil_ls:
        if user and not FilesystemPermissions.readable(item['file-name'], user, parent=path):
            continue
        if user:
            item['writable'] = FilesystemPermissions.writable_self(item['file-name'], user, parent=path)
        ret_result.append(item)
    return ret_result

def get_content(path, user):
    """Gets binary content of the object (must be file) and returns the
    actual content in bytes."""
    if user and not FilesystemPermissions.readable(path, user):
        return file_stream.EmptyFileStream
    ret_result = Filesystem.get_content(path)
    return ret_result

def get_file_name(path):
    """Returns the filename of 'path', although unknown whether has access
    or even exists."""
    path = path.split('/')
    path.remove('')
    path = [''] + path
    return path[-1:][0]

def readable(path, user):
    """Whether the user has read access to this file."""
    if user and not FilesystemPermissions.readable(path, user):
        return False
    return True

def writable(path, user):
    """Whether the user has write access to this file."""
    if user and not FilesystemPermissions.writable(path, user):
        return False
    return True

def writable_self(path, user):
    """Whether the user has write access to this file from the parent."""
    if user and not FilesystemPermissions.writable_self(path, user):
        return False
    return True
