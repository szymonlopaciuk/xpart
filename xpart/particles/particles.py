# copyright ############################### #
# This file is part of the Xpart Package.   #
# Copyright (c) CERN, 2021.                 #
# ######################################### #

import numpy as np
import xobjects as xo

from ..general import _pkg_root
from .particles_base import ParticlesBase, pmass, LAST_INVALID_STATE


def _contains_nan(arr, ctx):
    if isinstance(ctx, xo.ContextPyopencl):
        nparr = ctx.nparray_from_context_array(arr)
        return np.any(np.isnan(nparr))
    else:
        return ctx.nplike_lib.any(ctx.nplike_lib.isnan(arr))


class Particles(ParticlesBase):
    """
        Particle objects have the following fields:

             - s [m]: Reference accumulated path length
             - x [m]: Horizontal position
             - px[1]: Px / (m/m0 * p0c) = beta_x gamma /(beta0 gamma0)
             - y [m]: Vertical position
             - py [1]: Py / (m/m0 * p0c)
             - delta [1]: (Pc m0/m - p0c) /p0c
             - ptau [1]: (Energy m0/m - Energy0) / p0c
             - pzeta [1]: ptau / beta0
             - rvv [1]: beta / beta0
             - rpp [1]: m/m0 P0c / Pc = 1/(1+delta)
             - zeta [m]: (s - beta0 c t )
             - tau [m]: (s / beta0 - ct)
             - mass0 [eV]: Reference rest mass
             - q0 [e]: Reference charge
             - p0c [eV]: Reference momentum
             - energy0 [eV]: Reference energy
             - gamma0 [1]: Reference relativistic gamma
             - beta0 [1]: Reference relativistic beta
             - mass_ratio [1]: mass/mass0 (this is used to track particles of
                               different species. Note that mass is the rest mass
                               of the considered particle species and not the
                               relativistic mass)
             - chi [1]: q / q0 * m0 / m = qratio / mratio
             - charge_ratio [1]: q / q0
             - particle_id [int]: Identifier of the particle
             - at_turn [int]: Number of tracked turns
             - state [int]: It is <= 0 if the particle is lost, > 0 otherwise
                            (different values are used to record information
                            on how the particle is lost or generated).
             - weight [int]: Particle weight in number of particles
                              (for collective sims.)
             - at_element [int]: Identifier of the last element through which
                                 the particle has been
             - parent_particle_id [int]: Identifier of the parent particle
                                         (secondary production processes)
    """
    _cname = 'ParticlesData'

    size_vars = ParticlesBase.size_vars
    scalar_vars = ParticlesBase.scalar_vars
    per_particle_vars = ParticlesBase.per_particle_vars + \
                        ((xo.Float64, 'x'),
                         (xo.Float64, 'y'),
                         (xo.Float64, 'px'),
                         (xo.Float64, 'py'))

    _xofields = {
        **{nn: tt for tt, nn in size_vars + scalar_vars},
        **{nn: tt[:] for tt, nn in per_particle_vars},
    }

    _rename = ParticlesBase._rename

    _extra_c_sources = [
        _pkg_root.joinpath('rng_src', 'base_rng.h'),
        _pkg_root.joinpath('rng_src', 'particles_rng.h'),
        '\n /*placeholder_for_local_particle_src*/ \n'
    ]

    _kernels = {
        'Particles_initialize_rand_gen': xo.Kernel(
            args=[
                xo.Arg(xo.ThisClass, name='particles'),
                xo.Arg(xo.UInt32, pointer=True, name='seeds'),
                xo.Arg(xo.Int32, name='n_init')],
            n_threads='n_init')
    }

    def init_independent_per_part_vars(self, kwargs):
        super(Particles, self).init_independent_per_part_vars(kwargs)
        self.x = kwargs.get('x', 0)
        self.y = kwargs.get('y', 0)
        self.px = kwargs.get('px', 0)
        self.py = kwargs.get('py', 0)

    @classmethod
    def gen_local_particle_api(cls, mode='no_local_copy'):
        source = super(Particles, cls).gen_local_particle_api(mode)
        source += """
            #ifdef XTRACK_GLOBAL_POSLIMIT
        
            /*gpufun*/
            void global_aperture_check(LocalParticle* part0) {
                //start_per_particle_block (part0->part)
                    double const x = LocalParticle_get_x(part);
                    double const y = LocalParticle_get_y(part);
        
                int64_t const is_alive = (int64_t)(
                                  (x >= -XTRACK_GLOBAL_POSLIMIT) &&
                          (x <=  XTRACK_GLOBAL_POSLIMIT) &&
                          (y >= -XTRACK_GLOBAL_POSLIMIT) &&
                          (y <=  XTRACK_GLOBAL_POSLIMIT) );
        
                // I assume that if I am in the function is because
                    if (!is_alive){
                       LocalParticle_set_state(part, -1);
                }
                //end_per_particle_block
            }

            #endif
            
            /*gpufun*/
            void LocalParticle_add_to_energy(LocalParticle* part, double delta_energy, int pz_only ){
                double ptau = LocalParticle_get_ptau(part);
                double const p0c = LocalParticle_get_p0c(part);
        
                ptau += delta_energy/p0c;
                double const old_rpp = LocalParticle_get_rpp(part);
        
                LocalParticle_update_ptau(part, ptau);
        
                if (!pz_only) {
                    double const new_rpp = LocalParticle_get_rpp(part);
                    double const f = old_rpp / new_rpp;
                    LocalParticle_scale_px(part, f);
                    LocalParticle_scale_py(part, f);
                }
            }
            
            
            /*gpufun*/
            void LocalParticle_update_p0c(LocalParticle* part, double new_p0c_value){
        
                double const mass0 = LocalParticle_get_mass0(part);
                double const old_p0c = LocalParticle_get_p0c(part);
                double const old_delta = LocalParticle_get_delta(part);
                double const old_beta0 = LocalParticle_get_beta0(part);
        
                double const ppc = old_p0c * old_delta + old_p0c;
                double const new_delta = (ppc - new_p0c_value)/new_p0c_value;
        
                double const new_energy0 = sqrt(new_p0c_value*new_p0c_value + mass0 * mass0);
                double const new_beta0 = new_p0c_value / new_energy0;
                double const new_gamma0 = new_energy0 / mass0;
        
                LocalParticle_set_p0c(part, new_p0c_value);
                LocalParticle_set_gamma0(part, new_gamma0);
                LocalParticle_set_beta0(part, new_beta0);
        
                LocalParticle_update_delta(part, new_delta);
        
                LocalParticle_scale_px(part, old_p0c/new_p0c_value);
                LocalParticle_scale_py(part, old_p0c/new_p0c_value);
        
                LocalParticle_scale_zeta(part, new_beta0/old_beta0);
        
            }
    
            /*gpufun*/
            void LocalParticle_kill_particle(LocalParticle* part, int64_t kill_state) {
                LocalParticle_set_x(part, 1e30);
                LocalParticle_set_px(part, 1e30);
                LocalParticle_set_y(part, 1e30);
                LocalParticle_set_py(part, 1e30);
                LocalParticle_set_zeta(part, 1e30);
                LocalParticle_update_delta(part, -1);  // zero energy
                LocalParticle_set_state(part, kill_state);
            }
        """
        return source
