"""Bounded, read-only viewer snapshot prototype. Run on Fusion's main thread.

Body-ordered binary STL in millimeters, gzip/base64 over existing SSH HTTP
transport. Triangle ranges identify individual body instances for highlighting.
if_none_match saves transfer, but still exports to detect geometry changes.
"""
import base64
import gzip
import hashlib
import os
import re
import struct
import tempfile
import time
import uuid

import adsk.fusion
import bridge_helpers as bh

MAX_RAW = 32 * 1024 * 1024
MAX_PAYLOAD = 4 * 1024 * 1024  # below transport's 8 MiB JSON result cap
VIEWER_EPOCH = uuid.uuid4().hex


def capabilities(body):
    return {'api_version': '1.0', 'epoch': VIEWER_EPOCH,
            'features': ['assembly_state', 'atomic_capture', 'stl_gzip', 'content_hash', 'part_ranges'],
            'formats': ['stl'], 'qualities': ['low', 'medium', 'high'],
            'limits': {'raw_bytes': MAX_RAW, 'payload_bytes': MAX_PAYLOAD},
            'units': 'mm', 'up_axis': 'z'}


def body_instances(root):
    for native in root.bRepBodies:
        yield native, None
    for occurrence in root.allOccurrences:
        for native in occurrence.component.bRepBodies:
            yield native, occurrence


def transform_facets(facets, matrix):
    """Transform STL mm vertices and direction normals with Fusion's cm matrix."""
    result = bytearray(len(facets))
    for offset in range(0, len(facets), 50):
        values = struct.unpack_from('<12fH', facets, offset)
        transformed = []
        for index in range(0, 12, 3):
            x, y, z = values[index:index + 3]
            for row in range(3):
                at = row * 4
                transformed.append(matrix[at] * x + matrix[at + 1] * y + matrix[at + 2] * z
                                   + (matrix[at + 3] * 10 if index else 0))
        struct.pack_into('<12fH', result, offset, *transformed, values[12])
    return result


def snapshot(body):
    start = time.perf_counter()
    quality = body.get('quality', 'medium')
    encoding = body.get('encoding', 'gzip')
    known = body.get('if_none_match')
    if quality not in ('low', 'medium', 'high'):
        raise ValueError('quality must be low, medium, or high')
    if encoding not in ('gzip', 'identity'):
        raise ValueError('encoding must be gzip or identity')
    if known is not None and (not isinstance(known, str) or not re.fullmatch('[a-f0-9]{64}', known)):
        raise ValueError('if_none_match must be a SHA-256 digest')
    design = bh.get_design()
    parts = []
    facets = bytearray()
    export_start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='fusion-viewer-') as folder:
        path = os.path.join(folder, 'snapshot.stl')
        for native, occurrence in body_instances(design.rootComponent):
            occurrence_path = occurrence.fullPathName if occurrence else ''
            visible = native.isVisible and (occurrence.isVisible if occurrence else True)
            identity = occurrence_path + '\0' + native.entityToken
            part = {'id': hashlib.sha256(identity.encode()).hexdigest(),
                    'name': native.name, 'path': occurrence_path, 'visible': bool(visible),
                    'triangle_start': len(facets) // 50, 'triangle_count': 0}
            parts.append(part)
            if not visible:
                continue
            # Export the native body in component coordinates, then explicitly
            # place every instance in the root assembly (including nested ones).
            opts = design.exportManager.createSTLExportOptions(native, path)
            opts.unitType = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
            opts.isBinaryFormat = True
            opts.isOneFilePerBody = False
            opts.sendToPrintUtility = False
            opts.meshRefinement = {
                'low': adsk.fusion.MeshRefinementSettings.MeshRefinementLow,
                'medium': adsk.fusion.MeshRefinementSettings.MeshRefinementMedium,
                'high': adsk.fusion.MeshRefinementSettings.MeshRefinementHigh,
            }[quality]
            if not design.exportManager.execute(opts):
                raise RuntimeError('Fusion STL export failed')
            if os.path.getsize(path) + len(facets) > MAX_RAW:
                raise ValueError('Snapshot exceeds 32 MiB raw limit; use a lower quality')
            with open(path, 'rb') as stream:
                raw_body = stream.read(MAX_RAW + 1)
            if len(raw_body) < 84 or len(raw_body) != 84 + 50 * struct.unpack_from('<I', raw_body, 80)[0]:
                raise ValueError('Invalid binary STL length')
            body_facets = raw_body[84:]
            if occurrence:
                body_facets = transform_facets(body_facets, list(occurrence.transform2.asArray()))
            part['triangle_count'] = len(body_facets) // 50
            facets.extend(body_facets)
    export_ms = (time.perf_counter() - export_start) * 1000
    raw = b'Fusion viewer snapshot; units=mm'.ljust(80, b'\0') + struct.pack('<I', len(facets) // 50) + facets
    digest = hashlib.sha256(raw).hexdigest()
    result = {
        'schema': 'fusion-viewer-stl-v1', 'document': bh.app.activeDocument.name,
        'quality': quality, 'format': 'stl', 'units': 'mm', 'up_axis': 'z',
        'sha256': digest, 'changed': digest != known,
        'triangles': (len(raw) - 84) // 50, 'raw_bytes': len(raw),
        'encoding': encoding, 'payload_bytes': 0, 'parts': parts,
        'timing_ms': {'export': round(export_ms, 3)},
    }
    encode_start = time.perf_counter()
    if result['changed']:
        payload = gzip.compress(raw, compresslevel=1, mtime=0) if encoding == 'gzip' else raw
        if len(payload) > MAX_PAYLOAD:
            raise ValueError('Snapshot exceeds 4 MiB payload limit; use gzip/lower quality or split by body')
        result['payload_bytes'] = len(payload)
        result['data_base64'] = base64.b64encode(payload).decode('ascii')
    result['timing_ms']['encode'] = round((time.perf_counter() - encode_start) * 1000, 3)
    result['timing_ms']['handler'] = round((time.perf_counter() - start) * 1000, 3)
    return result


def state(body):
    """Viewer assembly metadata; labels are session-local, not durable entity IDs.

    Matrices are row-major in root assembly context, with translations in mm.
    This is NOT a complete geometry change detector. Emit after committed steps.
    """
    start = time.perf_counter()
    design = bh.get_design()
    root = design.rootComponent
    occurrences = []
    count = root.bRepBodies.count
    for occ in root.allOccurrences:
        matrix = list(occ.transform2.asArray())
        for index in (3, 7, 11):
            matrix[index] *= 10
        bodies = [{'name': b.name, 'visible': b.isVisible} for b in occ.component.bRepBodies]
        count += len(bodies)
        occurrences.append({'path': occ.fullPathName, 'component': occ.component.name,
                            'visible': occ.isVisible, 'matrix_row_major_mm': matrix,
                            'bodies': bodies})
    return {'schema': 'fusion-viewer-state-v1', 'document': bh.app.activeDocument.name,
            'document_key': hashlib.sha256(root.entityToken.encode()).hexdigest(),
            'epoch': VIEWER_EPOCH,
            'units': 'mm', 'up_axis': 'z', 'body_instance_count': count,
            'root_bodies': [{'name': b.name, 'visible': b.isVisible} for b in root.bRepBodies],
            'occurrences': occurrences,
            'handler_ms': round((time.perf_counter() - start) * 1000, 3)}


def capture(body):
    # One dispatcher job holds the CAD command slot for both reads.
    geometry = snapshot(body)
    assembly = state({})
    return {'api_version': '1.0', 'epoch': VIEWER_EPOCH,
            'document_key': assembly['document_key'],
            'state': assembly, 'geometry': geometry}


VIEWER_ROUTES = {'/viewer_snapshot': snapshot, '/viewer_state': state,
                '/v1/viewer/snapshot': snapshot, '/v1/viewer/state': state,
                '/v1/viewer/capture': capture, '/v1/viewer/capabilities': capabilities}
