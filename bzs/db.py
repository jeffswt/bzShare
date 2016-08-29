
import psycopg2
import time
import uuid

from bzs import const

"""
-- PostgreSQL DDL
CREATE TABLE storage (
   filename     text          NOT NULL,
   id           uuid          NOT NULL,
   upload_time  timestamptz   NOT NULL,
   content      bytea         NOT NULL
);
ALTER TABLE public.storage ADD CONSTRAINT storage_pkey PRIMARY KEY (id);
CREATE UNIQUE INDEX storage_id_uindex ON storage USING btree (id);
"""

################################################################################

class UniqueFile:
    uuid_list = set()
    hash_list = set()
    # Hashing algorithm, could be md5, sha1, sha224, sha256, sha384, sha512
    # sha384 and sha512 are not recommended due to slow speeds on 32-bit computers
    hash_algo = hashlib.sha256

    @classmethod
    def insert_uuid(self, _uuid):
        self.uuid_list.add(_uuid)
        return

    @classmethod
    def insert_hash(self, _hash):
        self.hash_list.add(_hash)
        return

    def __init__(self, content, uuid_=None, hash_=None, upload_time=None):
        # Assign content
        self.content = content
        # Takes in UUID or generates a new one, randomly
        if not uuid_:
            uuid_ = uuid.uuid4().hex
            while uuid_ in uuid_list: # Must make sure this is uniquely unique
                uuid_ = uuid.uuid4().hex
        self.uuid = uuid_
        self.insert_uuid(self.uuid)
        # Generates the content hash or takes in **without** verifing
        # Uses SHA256 algorithm for lower incident possibilities
        self.hash = hash_ or self.hash_algo().hexlify()
        self.insert_hash(self.hash)
        # Generates upload time or takes in
        self.upload_time = _upload_time or datetime.datetime.now(tz=
            const.get_const('time-zone')
        return
    pass

################################################################################

class Filesystem:
    class fsNode:
        uuid_list = set()

        @classmethod
        def insert_uuid(self, _uuid):
            self.uuid_list.add(_uuid)
            return

        def __init__(self, is_dir, filename, uuid_=None, child_list=set() ):
            self.is_dir = is_dir
            # It depends...
            if self.is_dir:
                # Assign file name
                self.filename = filename
                # The file system uuid is assigned
                if not uuid_:
                    uuid_ = uuid.uuid4().hex
                    while uuid_ in uuid_list:
                        uuid_ = uuid.uuid4().hex
                self.uuid = uuid_
                self.insert_uuid(self.uuid)
                # The list of its children, literally, set
                self.child_list = set()
                for item in child_list:
                    self.child_list.add(i)
            else:
                # Assign file name
                self.filename = filename
                # The file system uuid is assigned
                if not uuid_:
                    raise ValueError('Must have a UUID pointing to actual file storage')
                self.uuid = uuid_
                # There will be no insertions because it does not belong here
                # The list of its children must be null
                self.child_list = set()
            return
        pass
    # TODO
    pass

################################################################################

class Database:













################################################################################
