
import random
import requests
import threading
import time

def test_request_delay(path):
    """ Returns the average delay of requests. """
    tmal = list()
    for i in range(0, 10):
        tm = time.time()
        req = requests.get(path)
        tmal.append(time.time() - tm)
    return sum(tmal) / len(tmal)

def get(path):
    """ Get content of data from 'path', returning also the request time. """
    tm = time.time()
    req = requests.get(path)
    tm = time.time() - tm
    dat = '\n'.join(i.decode('utf-8', 'ignore') for i in req.iter_lines())
    return (tm, dat)

def force_thread(thr_num, path):
    print('Thread #%d HAD STARTED' % thr_num)
    while True:
        # Create randomization
        time.sleep(random.random() * 0.618)
        print('Thread #%d:   %s ms' % (thr_num, get(path)[0] * 1000))
    return

def create_thread(threads=1, path='http://localhost'):
    print('Creating stress tester with %d thread\n%s\n' % (threads, '#' * 70))
    for i in range(0, threads):
        time.sleep(0.3)
        threading.Thread(target=force_thread, args=[i, path]).start()
    return

create_thread(20, 'http://localhost/files')
