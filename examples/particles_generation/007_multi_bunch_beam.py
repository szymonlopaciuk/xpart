import xpart as xp
import numpy as np
import xtrack as xt
import json


class DummyCommunicator:
    def __init__(self, n_procs):
        self.n_procs = n_procs

    def Get_size(self):
        return self.n_procs

filename = xt._pkg_root.joinpath('/home/giacomel/xsuite/xtrack/test_data/lhc_no_bb/line_and_particle.json')
with open(filename, 'r') as fid:
    input_data = json.load(fid)

line = xt.Line.from_dict(input_data['line'])
particle_ref = xp.Particles.from_dict(input_data['particle'])

line.build_tracker()
#line_dict = xp._characterize_line(line, particle_ref)

circumference = line.get_length()
h_list = [35640]

bunch_spacing_in_buckets = 10
filling_scheme_array = np.zeros(3564)
filling_scheme_array[0:100] = 1
n_bunches = 100
filled_slots = np.linspace(0, n_bunches, n_bunches)
n_procs = 3
communicator = DummyCommunicator(n_procs)
filling_scheme = xp.FillingScheme(bunch_spacing_in_buckets=bunch_spacing_in_buckets,
                                  filling_scheme_array=filling_scheme_array, communicator=communicator,
                                  circumference=circumference, harmonic_list=h_list)

assert (filling_scheme.bunches_per_rank[0] == np.linspace(0, 33, 34)).all()
assert (filling_scheme.bunches_per_rank[1] == np.linspace(34, 66, 33)).all()
assert (filling_scheme.bunches_per_rank[2] == np.linspace(67, 99, 33)).all()