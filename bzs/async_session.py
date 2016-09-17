
import threading
import queue

from . import utils

class AsyncSessionType:
    def __init__(self):
        self.session_idx = dict()
        self.running_sessions = 0
        self.max_sessions = 1
        self.pend_session_queue = queue.Queue()
        self.lock = threading.Lock()
        return
    def __session_thread(self, session_id, func, args, kwargs):
        ret_res = func(*args, **kwargs)
        self.session_idx[session_id] = (True, ret_res)
        self.running_sessions -= 1
        # Creating new session in case some are pending
        self.lock.acquire()
        if not self.pend_session_queue.empty():
            self.__spawn_session(self.pend_session_queue.get())
        self.lock.release()
        return
    def __spawn_session(self, tup):
        self.running_sessions += 1
        threading.Thread(target=self.__session_thread, args=tup).start()
        return
    def create_session(self, func, *args, **kwargs):
        self.lock.acquire()
        session_id = utils.get_new_uuid(None, self.session_idx)
        self.session_idx[session_id] = (False, None)
        if self.running_sessions < self.max_sessions:
            self.__spawn_session((session_id, func, args, kwargs))
        else:
            self.pend_session_queue.put((session_id, func, args, kwargs))
        self.lock.release()
        return session_id
    def query_state(self, session_id):
        if session_id not in self.session_idx:
            raise KeyError('Session ID does not exist')
        self.lock.acquire()
        ret_val = self.session_idx[session_id][0]
        self.lock.release()
        return ret_val
    def query_result(self, session_id):
        if not self.query_state(session_id):
            raise KeyError('Session not yet completed')
        self.lock.acquire()
        ret_val = self.session_idx[session_id][1]
        del self.session_idx[session_id]
        self.lock.release()
        return ret_val
    pass

AsyncSession = AsyncSessionType()

def create_session(function, *args, **kwargs):
    """ Creates a multithreaded session and returns the session ID. """
    return AsyncSession.create_session(function, *args, **kwargs)

def completed(session_id):
    """ Queries asynchronously the state of the session, returns boolean. """
    return AsyncSession.query_state(session_id)

def get_result(session_id):
    """ Queries asynchronously the result of the session. """
    return AsyncSession.query_result(session_id)
