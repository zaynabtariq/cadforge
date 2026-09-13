"""Source-linked connector selection; not cable routing or qualification."""
from math import isfinite

INSTALL_SOURCE='https://www.raspberrypi.com/documentation/accessories/camera.html'
CABLE_SOURCE='https://www.raspberrypi.com/products/camera-cable/'
CONNECTORS={'standard':15,'mini':22}


def assess_camera_cable(board_connector, camera_connector, cable_ends, *, length_mm=None, required_length_mm=None):
    """Check documented connector families; lengths must be externally specified.

    The endpoint family check does not verify arbitrary third-party pin mapping,
    contact orientation, bend limits, latch clearance or signal integrity.
    """
    if board_connector not in CONNECTORS or camera_connector not in CONNECTORS:
        raise ValueError('Unknown camera connector family')
    if not isinstance(cable_ends,(list,tuple)) or len(cable_ends)!=2 or any(end not in CONNECTORS for end in cable_ends):
        raise ValueError('Two recognized cable endpoint families required')
    for value in (length_mm,required_length_mm):
        if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<=0):
            raise ValueError('Cable and required route lengths must be positive finite millimeters')
    matches=sorted(cable_ends)==sorted((board_connector,camera_connector))
    return {'connector_families':{'status':'pass' if matches else 'fail','required':[board_connector,camera_connector],'supplied':list(cable_ends),'source':INSTALL_SOURCE},
        'length':{'status':'blocked' if length_mm is None or required_length_mm is None else 'pass' if length_mm>=required_length_mm else 'fail','available_mm':length_mm,'required_mm':required_length_mm},
        'physical_qualification':{'status':'blocked','detail':'Exact cable drawing, contact orientation, routing, bend limits, slack and strain relief are unverified.'},
        'production_ready':False}


def reference_interconnect():
    return {'board':'Raspberry Pi Zero 2 W','camera':'Camera Module 3 Standard',
        'board_connector':{'family':'mini','pins':22},'camera_connector':{'family':'standard','pins':15},
        'required_cable_family':'Raspberry Pi Camera Cable Standard-Mini',
        'official_available_lengths_mm':[200,300,500],
        'selected_length_mm':None,'source':INSTALL_SOURCE,'cable_source':CABLE_SOURCE,
        'source_checked':'2026-09-12',
        'assessment':assess_camera_cable('mini','standard',('standard','mini')),
        'supplied_standard_standard_assessment':assess_camera_cable('mini','standard',('standard','standard'))}
