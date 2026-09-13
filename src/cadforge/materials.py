"""Source-versioned nominal screening data, never certified design allowables."""
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class MaterialProfile:
    name: str
    process: str
    density_g_cm3: float
    tensile_modulus_xy_mpa: float
    tensile_modulus_z_mpa: float
    source_url: str
    document_id: str
    document_date: str
    applicability: str
    official_current_datasheet_url: str
    current_datasheet_verified: bool = False
    qualified_for_production: bool = False
    allowable_stress_mpa: float | None = None

    @property
    def screening_modulus_mpa(self):
        """Lower listed directional nominal value, not a statistical lower bound."""
        return min(self.tensile_modulus_xy_mpa,self.tensile_modulus_z_mpa)

    def model_dump(self):
        return {**asdict(self),'screening_modulus_mpa':self.screening_modulus_mpa}

HP_MJF_PA12_LEGACY = MaterialProfile(
    name='HP 3D High Reusability PA 12 — legacy nominal screening profile',
    process='HP Multi Jet Fusion; balanced print mode, FW BD5',
    density_g_cm3=1.01,
    tensile_modulus_xy_mpa=1700.0,
    tensile_modulus_z_mpa=1800.0,
    source_url='https://www.3dmeclab.com/download/MJF/MJF-PA12.pdf',
    document_id='4AA6-4895ENE',
    document_date='2017-11',
    applicability='HP-authored datasheet retrieved from a distributor mirror. Typical values for legacy 4210/4200/3200 generation; not current-machine qualification or specification limits.',
    official_current_datasheet_url='https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-5028ENW',
)

@dataclass(frozen=True)
class ComponentMass:
    component: str
    nominal_mass_g: float | None
    source_url: str | None
    scope: str
    measured_actual: bool = False

HARDWARE_MASSES = (
    ComponentMass('Raspberry Pi Zero 2 W',12.0,
        'https://www.raspberrypi.com/news/what-can-you-build-with-raspberry-pi-zero/',
        'Official 2025-11-17 article nominal board value; actual revision/headers/microSD must be weighed.'),
    ComponentMass('Raspberry Pi Camera Module 3 Standard',4.0,
        'https://www.raspberrypi.com/documentation/accessories/camera.html',
        'Official camera comparison nominal module value; separate installed cable/fasteners not inventoried.'),
    ComponentMass('Camera ribbon cable',None,None,'Selected cable part number, length and actual mass required.'),
    ComponentMass('USB power cable carried by frame',None,None,'External power selected; cable load and strain relief still affect worn assembly.'),
    ComponentMass('Mounting screws, nuts and washers',None,None,'Final fastener sizes/counts and measured mass required.'),
    ComponentMass('microSD card',None,None,'Selected installed card mass required.'),
    ComponentMass('Optical/demo lenses',None,None,'Actual lens specification and mass absent.'),
)

EYEWEAR_REFERENCE = {
    'model':'Ray-Ban RX7074 / RB7074, marketed size 52-18-145',
    'lens_width_mm':52.0,
    'bridge_mm':18.0,
    'temple_length_mm':145.0,
    'lens_height_mm':42.4,
    'source_url':'https://india.ray-ban.com/eyeglasses/male/rx7074.html',
    'scope':'Representative commercially sold sizing, not a population standard or wearer fit measurement. Detailed product lens width is 52.1 mm; design uses marketed nominal 52 mm.',
    'wearer_fit_verified':False,
}


def nominal_screening_inputs():
    """Serializable assumptions to include beside, never conceal behind, estimates."""
    return {'material':HP_MJF_PA12_LEGACY.model_dump(),
            'hardware_masses':[asdict(c) for c in HARDWARE_MASSES],
            'eyewear_reference':dict(EYEWEAR_REFERENCE),
            'known_component_mass_g':sum(c.nominal_mass_g or 0 for c in HARDWARE_MASSES),
            'bom_complete':False,'engineering_ready':False}
