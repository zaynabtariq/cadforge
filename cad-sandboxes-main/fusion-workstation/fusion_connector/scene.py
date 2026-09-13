import base64
import collections
import copy
import gzip
import hashlib
import io
import json
import struct
import threading
import time
import uuid

from .bridge import BridgeError


class SceneStore:
    """Bounded in-memory immutable snapshots; one export serves every viewer.

    Explicit captures happen after committed modeling steps. Readers never
    trigger Fusion work. Version numbers are scoped to this connector epoch.
    """
    def __init__(self, bridge, capacity=16, byte_limit=64*1024*1024):
        self.bridge = bridge
        self.capacity, self.byte_limit = capacity, byte_limit
        self.epoch = uuid.uuid4().hex
        self.lock, self.capture_lock = threading.RLock(), threading.Lock()
        self.frames = collections.deque(maxlen=capacity)
        self.assets, self.keys = {}, collections.OrderedDict()
        self.version = 0

    def capture(self, *, quality='medium', step_id=None, key=None):
        if quality not in ('low', 'medium', 'high'):
            raise BridgeError('invalid_quality', 'Unsupported quality', 400)
        if step_id is not None and (not isinstance(step_id, str) or len(step_id)>128):
            raise BridgeError('invalid_step', 'step_id must be at most 128 characters', 400)
        if key is not None and (not isinstance(key, str) or not 1<=len(key)<=128):
            raise BridgeError('invalid_key', 'Idempotency key must be 1–128 characters', 400)
        fingerprint = (quality, step_id)
        def replay():
            if key and key in self.keys:
                saved, frame = self.keys[key]
                if saved != fingerprint: raise BridgeError('key_conflict', 'Key already used for a different capture', 409)
                return copy.deepcopy(frame)
        with self.lock:
            old = replay()
            if old: return old
        if not self.capture_lock.acquire(blocking=False):
            raise BridgeError('busy', 'A capture is already running; coalesce updates', 409)
        try:
            with self.lock:
                old = replay()
                if old: return old
            captured = self.bridge.call('/v1/viewer/capture', {'quality':quality,'encoding':'gzip'})
            mesh = captured['geometry']
            compressed = base64.b64decode(mesh['data_base64'], validate=True)
            if len(compressed)>4*1024*1024: raise BridgeError('payload_limit', 'Compressed mesh exceeds limit')
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw = stream.read(32*1024*1024+1)
            if len(raw)>32*1024*1024 or len(raw)<84 or len(raw)!=84+50*struct.unpack_from('<I',raw,80)[0]:
                raise BridgeError('invalid_mesh', 'Invalid binary STL')
            digest = hashlib.sha256(raw).hexdigest()
            if digest != mesh['sha256'] or len(raw) != mesh['raw_bytes']:
                raise BridgeError('checksum', 'Mesh integrity verification failed')
            with self.lock:
                self.version += 1
                frame = {'api_version':'1.0','connector_epoch':self.epoch,'version':self.version,
                    'fusion_epoch':captured['epoch'],'document_key':captured['document_key'],
                    'step_id':step_id,'created_at':time.time(),'state':captured['state'],
                    'geometry':{k:v for k,v in mesh.items() if k!='data_base64'}}
                self.frames.append(frame); self.assets[digest]=compressed
                if key: self.keys[key]=(fingerprint,frame)
                while len(self.keys)>self.capacity: self.keys.popitem(last=False)
                def prune():
                    referenced={x['geometry']['sha256'] for x in self.frames}
                    self.assets={k:v for k,v in self.assets.items() if k in referenced}
                    self.keys=collections.OrderedDict((k,v) for k,v in self.keys.items()
                        if any(f['version']==v[1]['version'] for f in self.frames))
                prune()
                while len(self.frames)>1 and sum(map(len,self.assets.values()))>self.byte_limit:
                    self.frames.popleft();prune()
                return copy.deepcopy(frame)
        finally:
            self.capture_lock.release()

    def latest(self):
        with self.lock: return copy.deepcopy(self.frames[-1]) if self.frames else None

    def events(self, after=0, epoch=None):
        if not isinstance(after,int) or after<0:raise BridgeError('invalid_cursor','after must be a nonnegative integer',400)
        with self.lock:
            resync = epoch != self.epoch or (self.frames and after < self.frames[0]['version']-1) or after>self.version
            return {'connector_epoch':self.epoch,'latest_version':self.version,'resync_required':bool(resync),
                    'events':[{'version':f['version'],'step_id':f['step_id']} for f in self.frames if f['version']>after]}

    def asset(self, digest):
        with self.lock:
            if digest not in self.assets: raise BridgeError('asset_expired','Fetch the latest scene',410)
            return self.assets[digest]
