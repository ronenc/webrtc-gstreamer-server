import asyncio
import json
import logging
import platform
import queue
import types
import socketio

#from events import Events # Note you must pip install events

logger = logging.getLogger(__name__)
BYE = object()
msg_queue = queue.Queue()

class SocketIOSignaler():
    def __init__(self, host, port):
        self.onPreOffer = asyncio.Event()
        self.onOffer = asyncio.Event()
        self.onAnswer = asyncio.Event()
        self.onIceCandidate = asyncio.Event()
        self._host = host
        self._port = port
        self.mySocketId = None
        self.sio = socketio.Client()
        self.connectedUserSocketId = None

        #self.onPreOffer = self.__events.on_pre_offer
        #self.onAnswer = self.__events.on_answer
        #self.onIceCandidate = self.__events.on_ice_candidate
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        @self.sio.event
        def message(data):
            print('I received a message!')

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
                        break
                '''    
                count = 0
                for user in activeUsers:
                    count+=1

                if count > 1:
                    self.sendPreOffer(activeUsers)
                '''    
            print('I received a broadcast message!')

        @self.sio.on('webRTC-candidate')
        def on_ice_candidate( data ):
            candidate = candidate_from_string(data)
            #asyncio.run(self.onIceCandidate(candidate))
            #loop = asyncio.new_event_loop()
            #asyncio.set_event_loop(loop)
            #self.loop.run_until_complete(self.onIceCandidate(candidate))
            #print('webRTC-candidate', data)
            msg_queue.put(candidate)


        @self.sio.on('pre-offer')
        def on_pre_offer( data ):
            self.connectedUserSocketId = data['callerSocketId']
            #asyncio.run(self.onPreOffer(data))
            #loop = asyncio.new_event_loop()
            #asyncio.set_event_loop(loop)
            #asyncio.run(self.onPreOffer(data))
            #print('pre-offer Completed!')
            print('pre-offer', data)
            asyncio.run(self.sendWebRtcPreOfferAnswer())

        @self.sio.on('webRTC-offer')
        def on_offer( data ):
            print('webRTC-offer Completed!')
            #print(data)
            #self.onOffer(data['offer'], 'offer')
            offer =  offer_from_string(data)
            #asyncio.run(self.onOffer(offer))
            #loop = asyncio.new_event_loop()
            #asyncio.set_event_loop(loop)
            #loop.run_until_complete(self.onOffer(data))
            msg_queue.put(offer)

        @self.sio.on('webRTC-answer')
        def on_answer( data ):
            #print('webRTC-answer Completed!')
            answer =  answer_from_string(data)
            #asyncio.run(self.onAnswer(answ1))
            #loop = asyncio.new_event_loop()
            #asyncio.set_event_loop(loop)
            #self.loop.run_until_complete(self.onAnswer(answ1))
            #asyncio.run(self.onAnswer(answer))
            msg_queue.put(answer)

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

        self.sio.connect('http://10.0.0.151:5000')

    def ConnectToServer():
        url = "http://10.0.0.160:5000"

    async def ConnectToServer(self):
        url = "http://{}:{}".format(self._host, self._port)
        await self.sio.connect(url)

    async def close(self):
        self.sio.disconnect()
#            await self.send(BYE)

    async def sendWebRtcOffer(self, descr):
        #str = object_to_string(descr) + "\n"
        #self.sio.emit("webRTC-offer", {'calleeSocketId':self.connectedUserSocketId, 'offer':str})
        self.sio.emit("webRTC-offer", {'calleeSocketId':self.connectedUserSocketId, 'offer':descr.sdp})

    async def sendWebRtcAnswer(self, descr):
        self.sio.emit("webRTC-answer", {'callerSocketId':self.connectedUserSocketId, 'answer':descr.sdp})
        print("sendWebRtcAnswer", self.connectedUserSocketId)

    async def sendWebRtcCandidate(self, descr):
        print("sendWebRtcCandidate", self.connectedUserSocketId)
        self.sio.emit("webRTC-candidate", {'candidate':descr, 'connectedUserSocketId':self.connectedUserSocketId})

    async def sendWebRtcPreOfferAnswer(self):
        self.sio.emit("pre-offer-answer", {'callerSocketId':self.connectedUserSocketId, 'answer':'CALL_ACCEPTED'})
        print("sendWebRtcPreOfferAnswer", self.connectedUserSocketId)

    def get_queue_item(self):
        return msg_queue.get()
    

    def sendPreOffer(self, activeUsers):
         for peerUser in activeUsers:
            if peerUser['socketId'] != self.mySocketId:
                self.connectedUserSocketId = peerUser['socketId']
                #self.sio.emit("pre-offer", {'callee':peerUser, 'caller':{'username': 'remotepeer'}})
                print("sendPreOffer to", self.connectedUserSocketId)

    def message(data):
        print('I received a message!')

    def on_message(data):
        print('I received a message!')

    def connect():
        print("I'm connected!")

    def connect_error(data):
        print("The connection failed!")

    def disconnect():
        print("I'm disconnected!")

    def on_broadcast(data):
        print('I received a broadcast onevent!')

    def broadcast(data):
        print('I received a broadcast event!')


def add_signaling_arguments(parser):
    """
    Add signaling method arguments to an argparse.ArgumentParser.
    """
    parser.add_argument(
        "--signaling",
        "-s",
        choices=["copy-and-paste", "tcp-socket", "unix-socket"],
    )
    parser.add_argument(
        "--signaling-host", default="10.0.0.160", help="Signaling host (tcp-socket only)"
    )
    parser.add_argument(
        "--signaling-port", default=1234, help="Signaling port (tcp-socket only)"
    )
    parser.add_argument(
        "--signaling-path",
        default="aiortc.socket",
        help="Signaling socket path (unix-socket only)",
    )

def create_signaler(args):
    """
    Create a signaling method based on command-line arguments.
    """
    #if args.signaling == "tcp-socket":
    #return SocketIOSignaler(args.signaling_host, args.signaling_port)
    signaler = SocketIOSignaler("10.0.0.160", "5000")
    return signaler
