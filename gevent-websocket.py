#!/usr/bin/python

from videoconference.wsgi import application
import simplejson as json

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from websockets.websockethandler import Handler
from websockets.sockets import WebSockets
from scheduler.models import MCU, Reservation


from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth.models import User
from importlib import import_module
from django.http import parse_cookie
from django.contrib.sessions.models import Session
from django.utils import timezone
from copy import copy



global_sockets = WebSockets()

def websocket_app(environ, start_response):
    if not 'wsgi.websocket' in environ:
        print "Not a websocket"
        return
    ws = environ["wsgi.websocket"]

    # Important to call, otherwise we may get stale user sessions
    SessionStore.clear_expired() 

    # Get the session object and implicitly check if the session is valid
    cookie = parse_cookie(environ['HTTP_COOKIE'])
    if not 'sessionid' in cookie:
        print "No session cookie"
        return

    s = SessionStore(session_key=cookie['sessionid'])
    if not '_auth_user_id' in s:
        print "Invalid session"
        return

    user = User.objects.get(pk=s['_auth_user_id'])
    if not user:
        print "Invalid user"
        return

    path = environ['PATH_INFO'].split('/')
    if len(path) < 3 or path[1] != 'conference' or not path[2].isdigit():
        print "Invalid path"
        return

    conference_id = int(path[2])

    conference = Reservation.objects.get(pk=conference_id)
    if conference.user != user:
        print "User not owner of this conference"
        return

    #if conference.end_time < timezone.now() or conference.begin_time > timezone.now():
    #    print "Conference not currently in progress"
    #    return

    # FIXME Hardcoded
    backend_info = {
        'mcu': '127.0.0.1',
        'room': 'room101',
    }

    socket_info = copy(global_sockets)
    socket_info.subscribe(ws, conference)

    interface = Handler(backend_info=backend_info, conference=conference, sockets=socket_info)

    while True:
        data = ws.receive()
        if data is None:
            socket_info.close(socket_info.local)
            return

        try:
            message = json.loads(data)
        except Exception as e:
            print repr(e), data
            return


        handlers = {
                'LIST_MOSAIC':           'list_mosaic',
                'LIST_PARTICIPANTS':     'list_participants',
                'MOVE_PARTICIPANT':      'move_participant',
                'REMOVE_PARTICIPANT':    'remove_participant',
                'JOIN_CONFERENCE':       'join_conference',
        }

        if not 'message_type' in message:
            print "Message has no message type"
            return
        if not message['message_type'] in handlers:
            print "No handler for message type", message['message_type']
            return

        print message['message_type'], "received"

        # Find and call the method in the MCUInterface class instance
        func = getattr(interface, handlers[message['message_type']])
        func(message['data'])


server = pywsgi.WSGIServer(("", 8000), websocket_app,
    handler_class=WebSocketHandler)
server.serve_forever()