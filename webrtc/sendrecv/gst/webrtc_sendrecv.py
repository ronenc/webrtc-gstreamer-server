import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import socketio
import queue

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

PIPELINE_DESC1 = '''
webrtcbin name=sendrecv bundle-policy=max-bundle stun-server=stun://stun.l.google.com:19302
 videotestsrc is-live=true pattern=ball ! videoconvert ! queue ! vp8enc deadline=1 ! rtpvp8pay !
 queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! sendrecv.
 audiotestsrc is-live=true wave=red-noise ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay !
 queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv.
'''

PIPELINE_DESC = '''
webrtcbin name=sendrecv stun-server=stun://stun.l.google.com:19302
 rtspsrc location=rtsp://127.0.0.1:6554/stream1 name=demuxer
 demuxer. ! rtpjitterbuffer mode=0 ! queue ! parsebin ! rtph264pay config-interval=-1 timestamp-offset=0 !
  queue ! application/x-rtp,media=video,encoding-name=H264,payload=98 ! queue ! sendrecv.
 demuxer. ! rtpjitterbuffer mode=0 ! queue ! decodebin ! audioconvert ! audioresample ! opusenc ! rtpopuspay timestamp-offset=0 !
  queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! queue ! sendrecv.
'''
#from websockets.version import version as wsv
msg_queue = queue.Queue()

class WebRTCClient:
    def __init__(self, id_, peer_id, server):
        self.id_ = id_
        self.conn = None
        self.pipe = None
        self.webrtc = None
        self.peer_id = peer_id
        self.server = server or 'wss://webrtc.nirbheek.in:8443'
        self.sio = socketio.Client()
        self.connectedUserSocketId = None

        @self.sio.event
        def message(data):
            print(data)

        @self.sio.on('connection')
        def on_connection(data):
            self.mySocketId = data
            self.sio.emit("register-new-user", {'username':'python-test-offer', 'socketId':data})
            print('I received a connection!', data)

        @self.sio.event
        def connect():
            print("I'm connected!")

        @self.sio.event
        def connect_error(data):
            print("The connection failed!")

        @self.sio.event
        def disconnect():
            print("I'm disconnected!")

        @self.sio.on('broadcast')
        def on_broadcast( data ):
            if data['eventname'] == 'ACTIVE_USERS':
                activeUsers = data['activeUsers']
                print (activeUsers)
                for peerUser in activeUsers:
                    print(peerUser['username'])
                    print(peerUser['socketId'])
                    if peerUser['socketId'] != self.mySocketId:
                        self.connectedUserSocketId = peerUser['socketId']
                        peer = peerUser
                        thisDict = {
                            "type": "message",
                            "value": "SESSION_OK"
                        }
                        msg_queue.put(thisDict)
                        #self.start_pipeline()
                        break
            print('I received a broadcast message!')

        @self.sio.on('pre-offer')
        def on_pre_offer( data ):
            print('webRTC-offer Completed!')
            thisDict = {
                "type": "pre-offer",
                "value": "PRE_OFFER"
            }
            msg_queue.put(thisDict)

        @self.sio.on('webRTC-candidate')
        def on_ice_candidate( data ):
            thisDict = {
                "type": "candidate",
                "value": data
            }
            msg_queue.put(thisDict)

        @self.sio.on('webRTC-offer')
        def on_offer( data ):
            print('webRTC-offer Completed!')
            thisDict = {
                "type": "offer",
                "value": data
            }
            msg_queue.put(thisDict)

        @self.sio.on('webRTC-answer')
        def on_answer( data ):
            thisDict = {
                "type": "answer",
                "value": data
            }
            msg_queue.put(thisDict)

        #self.sio.connect(server)
        #self.sio.connect("https://8264-70-71-185-138.ngrok.io/webrtcPeer", {'path':'io/webrtc', 'query': ''})
#        self.sio.connect("https://8264-70-71-185-138.ngrok.io/webrtcPeer", namespaces=['/webrtcPeer', '/webrtc'])
        self.sio.connect('http://10.0.0.17:5000')

    async def sendWebRtcOffer(self, descr):
        print("sendWebRtcOffer", self.connectedUserSocketId)
        self.sio.emit("webRTC-offer", {'calleeSocketId':self.connectedUserSocketId, 'offer':descr})

    async def sendWebRtcAnswer(self, descr):
        print("sendWebRtcAnswer", self.connectedUserSocketId)
        self.sio.emit("webRTC-answer", {'callerSocketId':self.connectedUserSocketId, 'answer':descr})

    async def sendWebRtcCandidate(self, candidate, sdpMLineIndex):
        print("sendWebRtcCandidate", candidate)
        self.sio.emit("webRTC-candidate", {'candidate': {'candidate': candidate, 'sdpMid': int(sdpMLineIndex), 'sdpMlineIndex': sdpMLineIndex}, 
            'connectedUserSocketId':self.connectedUserSocketId})

    async def connect(self):
        #sslctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        ##self.conn = await websockets.connect(self.server, ssl=sslctx)
        #await self.conn.send('HELLO %d' % self.id_)
        await self.sio.connect('http://10.0.0.151:5000')

    async def setup_call(self):
        await self.conn.send('SESSION {}'.format(self.peer_id))

    def send_sdp_offer(self, offer):
        text = offer.sdp.as_text()
        print ('Sending offer:\n%s' % text)
        msg = json.dumps({'sdp': {'type': 'offer', 'sdp': text}})
        asyncio.run(self.sendWebRtcOffer(text))

    def on_offer_created(self, promise, _, __):
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        self.send_sdp_offer(offer)

    def on_negotiation_needed(self, element):
        print('on_negotiation_needed', element)
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        print ('Send ice candidate :%s' % candidate)
        asyncio.run(self.sendWebRtcCandidate(candidate, mlineindex))

    def on_incoming_decodebin_stream(self, _, pad):
        print('on_incoming_decodebin_stream', pad)
        if not pad.has_current_caps():
            print (pad, 'has no caps, ignoring')
            return

        caps = pad.get_current_caps()
        name = caps.to_string()
        if name.startswith('video'):
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('videoconvert')
            sink = Gst.ElementFactory.make('autovideosink')
            #self.pipe.add(q, conv, sink)
            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(sink)
            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))
            q.link(conv)
            conv.link(sink)
        elif name.startswith('audio'):
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('audioconvert')
            resample = Gst.ElementFactory.make('audioresample')
            sink = Gst.ElementFactory.make('autoaudiosink')
            self.pipe.add(q, conv, resample, sink)
            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))
            q.link(conv)
            conv.link(resample)
            resample.link(sink)

    def on_incoming_stream(self, _, pad):
        print('on_incoming_stream', pad)
        if pad.direction != Gst.PadDirection.SRC:
            return
        decodebin = Gst.ElementFactory.make('decodebin')
        decodebin.connect('pad-added', self.on_incoming_decodebin_stream)
        self.pipe.add(decodebin)
        decodebin.sync_state_with_parent()
        self.webrtc.link(decodebin)

    def on_incoming_streamFake(self, _, pad):
        if pad.direction != Gst.PadDirection.SRC:
            return
        fakesink = Gst.ElementFactory.make('fakesink')
        self.pipe.add(fakesink)
        fakesink.sync_state_with_parent()
        self.webrtc.link(fakesink)

    def start_pipeline(self):
        print('start_pipeline')
        self.pipe = Gst.parse_launch(PIPELINE_DESC)
        self.webrtc = self.pipe.get_by_name('sendrecv')
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.send_ice_candidate_message)
        self.webrtc.connect('pad-added', self.on_incoming_streamFake)
        self.pipe.set_state(Gst.State.PLAYING)

    def handle_candidate(self, message):
        assert (self.webrtc)
        ice = message['candidate']
        candidate = ice['candidate']
        sdpmlineindex = ice['sdpMLineIndex']
        sdpMid = ice['sdpMid']
        print ('Received candidate:%s' % message)
        self.webrtc.emit('add-ice-candidate', sdpmlineindex, candidate)

    def handle_sdp(self, message):
        assert (self.webrtc)
        sdp = message['answer']
        print ('Received answer:\n%s' % sdp)
        res, sdpmsg = GstSdp.SDPMessage.new_from_text(sdp)
        answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
        promise = Gst.Promise.new()
        self.webrtc.emit('set-remote-description', answer, promise)
        promise.interrupt()

        print ('Setanswer:\n%s' % sdpmsg)

    def close_pipeline(self):
        self.pipe.set_state(Gst.State.NULL)
        self.pipe = None
        self.webrtc = None

    async def loop(self):
        while True:
            message = msg_queue.get()
            #assert self.conn
            if message["value"] == 'SESSION_OK':
                print (message["value"])
            elif message["value"] == 'PRE_OFFER':
                print (message["value"])
                self.start_pipeline()
            elif message["value"] =='ERROR':
                print (message)
                self.close_pipeline()
                return 1
            elif message["type"] == 'candidate':
                self.handle_candidate(message["value"])
            elif message["type"] == 'answer':
                self.handle_sdp(message["value"])
            else: 
                self.close_pipeline()
                return 0

    async def stop(self):
        if self.conn:
            await self.conn.close()
        self.conn = None


def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True


if __name__=='__main__':
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)
    #parser = argparse.ArgumentParser()
    #parser.add_argument('peerid', help='String ID of the peer to connect to')
    #parser.add_argument('--server', help='Signalling server to connect to, eg "wss://127.0.0.1:8443"')
    #args = parser.parse_args()
    server = 'https://350a-70-71-185-138.ngrok.io/webrtcPeer'
    peerid = '11223344'

    our_id = random.randrange(10, 10000)
#    c = WebRTCClient(our_id, args.peerid, args.server)
    c = WebRTCClient(our_id, peerid, server)
    loop = asyncio.get_event_loop()
    #loop.run_until_complete(c.connect())
    res = loop.run_until_complete(c.loop())
    sys.exit(res)
