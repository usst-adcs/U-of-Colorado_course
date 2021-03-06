import numpy as np
from adcsim import disturbance_torques as dt, integrators as it, transformations as tr, util as ut, \
    state_propagations as st, integral_considerations as ic
from adcsim.CubeSat_model import CubeSat
from tqdm import tqdm
import xarray as xr
from adcsim.dcm_convert.dcm_to_stk import dcm_to_stk_simple
from adcsim.containers import AttitudeData, OrbitData
import os
from datetime import datetime, timedelta
from skyfield.api import utc


def sim_attitude(sim_params, cubesat_params, file_name, save=True, ret=False):
    if isinstance(sim_params, str):
        sim_params = eval(sim_params)

    save_every = sim_params['save_every']  # only save the data every number of iterations

    # declare time step for integration
    time_step = sim_params['time_step']
    end_time = sim_params['duration']
    time = np.arange(0, end_time, time_step)
    le = (len(time) - 1) // save_every + 1     # Number of time steps where data points are saved

    num_simulation_data_points = int(sim_params['duration'] // sim_params['time_step']) + 1
    start_time = datetime.strptime(sim_params['start_time'], "%Y/%m/%d %H:%M:%S")
    start_time = start_time.replace(tzinfo=utc)
    final_time = start_time + timedelta(seconds=sim_params['time_step']*num_simulation_data_points)

    # create the CubeSat model
    cubesat = CubeSat.fromdict(cubesat_params)

    states = np.zeros((le, 2, 3))
    dcm_bn = np.zeros((le, 3, 3))
    dcm_on = np.zeros((le, 3, 3))
    dcm_bo = np.zeros((le, 3, 3))
    controls = np.zeros((le, 3))
    nadir = np.zeros((le, 3))
    sun_vec = np.zeros((le, 3))
    sun_vec_body = np.zeros((le, 3))
    lons = np.zeros(le)
    lats = np.zeros(le)
    alts = np.zeros(le)
    positions = np.zeros((le, 3))
    velocities = np.zeros((le, 3))
    aerod = np.zeros((le, 3))
    gravityd = np.zeros((le, 3))
    solard = np.zeros((le, 3))
    magneticd = np.zeros((le, 3))
    density = np.zeros(le)
    mag_field = np.zeros((le, 3))
    mag_field_body = np.zeros((le, 3))
    solar_power = np.zeros(le)
    is_eclipse = np.zeros(le)
    hyst_rod = np.zeros((le, len(cubesat.hyst_rods), 3))
    h_rods = np.zeros((le, len(cubesat.hyst_rods)))
    b_rods = np.zeros((le, len(cubesat.hyst_rods)))

    # load saved orbit and environment data
    with xr.open_dataset(os.path.join(os.path.dirname(__file__), '../../orbit_pre_process.nc')) as saved_data:
        orbit = OrbitData(sim_params, saved_data)

    # allocate space for attitude data
    attitude = AttitudeData(cubesat)

    # initialize attitude so that z direction of body frame is aligned with nadir
    # sun_vec[0], mag_field[0], density[0], lons[0], lats[0], alts[0], positions[0], velocities[0] = interp_info(0)
    attitude.interp_orbit_data(orbit, 0.0)
    sun_vec[0], mag_field[0], density[0], lons[0], lats[0], alts[0], positions[0], velocities[0] = attitude.temp.sun_vec, attitude.temp.mag_field, attitude.temp.density, attitude.temp.lons, attitude.temp.lats, attitude.temp.alts, attitude.temp.positions, attitude.temp.velocities
    sigma0 = np.array(sim_params['sigma0'])
    omega0_body = np.array(sim_params['omega0_body'])
    states[0] = state = [sigma0, omega0_body]
    dcm_bn[0] = tr.mrp_to_dcm(states[0][0])
    dcm_on[0] = ut.inertial_to_orbit_frame(positions[0], velocities[0])
    dcm_bo[0] = dcm_bn[0] @ dcm_on[0].T

    # Put hysteresis rods in an initial state that is reasonable. (Otherwise you can get large magnetization from the rods)
    mag_field_body[0] = (dcm_bn[0] @ mag_field[0]) * 10 ** -9  # in the body frame in units of T
    for rod in cubesat.hyst_rods:
        rod.define_integration_size(le)
        axes = np.argwhere(rod.axes_alignment == 1)[0][0]
        rod.h[0] = rod.h_current = mag_field_body[0][axes]/cubesat.hyst_rods[0].u0
        rod.b[0] = rod.b_current = rod.b_field_bottom(rod.h_current)

    # initialize the disturbance torque object
    disturbance_torques = dt.DisturbanceTorques(*([True for _ in range(len(sim_params['disturbance_torques']))] + [sim_params['calculate_power']]))
    if 'aerodynamic' in sim_params['disturbance_torques']:
        cubesat.create_aerodynamic_table(disturbance_torques.aerodynamic_torque, 101, 101)
    if 'solar' in sim_params['disturbance_torques']:
        cubesat.create_solar_table(disturbance_torques.solar_pressure, 101, 101)
    if sim_params['calculate_power']:
        cubesat.create_power_table(disturbance_torques.solar_panel_power, 101, 101)
    disturbance_torques.save_hysteresis = True

    # the integration
    k = 0
    for i in tqdm(range(len(time) - 1)):
        # propagate attitude state
        disturbance_torques.propagate_hysteresis = True  # should propagate the hysteresis history, bringing it up to the current position
        disturbance_torques.save_torques = True
        state = it.rk4(st.state_dot_mrp, time[i], state, time_step, attitude, orbit, cubesat, disturbance_torques)
        # controls[k] = ...

        # do 'tidy' up things at the end of integration (needed for many types of attitude coordinates)
        state = ic.mrp_switching(state)
        if not (i + 1) % save_every:
            k += 1
            states[k] = state
            dcm_bn[k] = attitude.save.dcm_bn
            dcm_on[k] = attitude.save.dcm_on
            dcm_bo[k] = attitude.save.dcm_bo
            controls[k] = attitude.save.controls
            nadir[k] = attitude.save.nadir
            sun_vec[k] = attitude.save.sun_vec
            sun_vec_body[k] = attitude.save.sun_vec_body
            lons[k] = attitude.save.lons
            lats[k] = attitude.save.lats
            alts[k] = attitude.save.alts
            positions[k] = attitude.save.positions
            velocities[k] = attitude.save.velocities
            aerod[k] = attitude.save.aerod
            gravityd[k] = attitude.save.gravityd
            solard[k] = attitude.save.solard
            magneticd[k] = attitude.save.magneticd
            density[k] = attitude.save.density
            mag_field[k] = attitude.save.mag_field
            mag_field_body[k] = attitude.save.mag_field_body
            if not attitude.save.is_eclipse:
                solar_power[k] = disturbance_torques.solar_panel_power(attitude.save.sun_vec_body,
                                                                       attitude.save.sun_vec,
                                                                       attitude.save.positions, cubesat)
            is_eclipse[k] = attitude.save.is_eclipse
            hyst_rod[k] = attitude.save.hyst_rod
            disturbance_torques.save_hysteresis = True
            if k >= le - 1:
                break

    for i, rod in enumerate(cubesat.hyst_rods):
        b_rods[:, i] = rod.b
        h_rods[:, i] = rod.h

    omegas = states[:, 1]
    sigmas = states[:, 0]

    # save the data
    sim_params_dict = {'time_step': time_step, 'save_every': save_every, 'duration': end_time,
                       'start_time': start_time.strftime('%Y/%m/%d %H:%M:%S'),
                       'final_time': final_time.strftime('%Y/%m/%d %H:%M:%S'), 'omega0_body': omega0_body.tolist(),
                       'sigma0': sigma0.tolist()}
    a = xr.Dataset({'sun': (['time', 'cord'], sun_vec),
                    'mag': (['time', 'cord'], mag_field),
                    'atmos': ('time', density),
                    'lons': ('time', lons),
                    'lats': ('time', lats),
                    'alts': ('time', alts),
                    'positions': (['time', 'cord'], positions),
                    'velocities': (['time', 'cord'], velocities),
                    'dcm_bn': (['time', 'dcm_mat_dim1', 'dcm_mat_dim2'], dcm_bn),
                    'dcm_bo': (['time', 'dcm_mat_dim1', 'dcm_mat_dim2'], dcm_bo),
                    'angular_vel': (['time', 'cord'], omegas),
                    'controls': (['time', 'cord'], controls),
                    'gg_torque': (['time', 'cord'], gravityd),
                    'aero_torque': (['time', 'cord'], aerod),
                    'solar_torque': (['time', 'cord'], solard),
                    'magnetic_torque': (['time', 'cord'], magneticd),
                    'hyst_rod_torque': (['time', 'hyst_rod', 'cord'], hyst_rod),
                    'hyst_rod_magnetization': (['time', 'hyst_rod'], b_rods),
                    'hyst_rod_external_field': (['time', 'hyst_rod'], h_rods),
                    'nadir': (['time', 'cord'], nadir),
                    'solar_power': ('time', solar_power),
                    'is_eclipse': ('time', is_eclipse)},
                   coords={'time': np.arange(0, le, 1), 'cord': ['x', 'y', 'z'], 'hyst_rod': [f'rod{i}' for i in range(len(cubesat.hyst_rods))]},
                   attrs={'simulation_parameters': str(sim_params_dict), 'cubesat_parameters': str(cubesat.asdict()),
                          'description': 'University of kentucky attitude propagator software '
                                         '(they call it SNAP) recreation'})
    # Note: the simulation and cubesat parameter dictionaries are saved as strings for the nc file. If you wish
    # you could just eval(a.cubesat_parameters) to get the dictionary back.
    if save:
        a.to_netcdf(os.path.join(os.path.dirname(__file__), f'../../{file_name}.nc'))
        dcm_to_stk_simple(time[::save_every], dcm_bn, os.path.join(os.path.dirname(__file__), f'../../{file_name}.a'))
    if ret:
        return a


# function to continue a simulation from the simulation data time for a given number of additional iterations
def continue_sim(sim_dataset, num_iter, file_name):
    import copy
    original_params = eval(sim_dataset.simulation_parameters)
    sim_params = copy.deepcopy(original_params)
    sim_params['duration'] = num_iter
    sim_params['start_time'] = sim_params['final_time']
    last_data = sim_dataset.isel(time=-1)
    sim_params['omega0_body'] = last_data.dcm_bn.values @ last_data.angular_vel.values
    sim_params['sigma0'] = tr.dcm_to_mrp(last_data.dcm_bn.values)
    cubesat_params = eval(sim_dataset.cubesat_parameters)
    new_data = sim_attitude(sim_params, cubesat_params, 'easter_egg', save=False, ret=True)
    new_data['time'] = np.arange(len(sim_dataset.time), len(sim_dataset.time) + sim_params['duration']*sim_params['save_every'], 1)
    a = xr.concat([sim_dataset, new_data], dim='time')
    true_sim_params = eval(a.simulation_parameters)
    true_sim_params['duration'] = original_params['duration'] + num_iter
    true_sim_params['final_time'] = eval(new_data.simulation_parameters)['final_time']
    a.attrs['simulation_parameters'] = str(true_sim_params)
    a.to_netcdf(os.path.join(os.path.dirname(__file__), f'../../{file_name}.nc'))


if __name__ == "__main__":
    # run a short simulation
    from adcsim.hysteresis_rod import HysteresisRod
    from adcsim.CubeSat_model_examples import CubeSatModel
    sim_params = {
        'time_step': 0.2,
        'save_every': 1,
        'duration': 3000,
        'start_time': '2019/03/24 18:35:01',
        'omega0_body': (np.pi / 180) * np.array([-2, 3, 3.5]),
        'sigma0': [0.6440095705520482, 0.39840861883760637, 0.18585931442943798],
        'disturbance_torques': ['gravity', 'magnetic', 'hysteresis', 'aerodynamic', 'solar'],
        'calculate_power': True
    }

    # create inital cubesat parameters dict (the raw data is way to large to do manually like above)
    rod1 = HysteresisRod(br=0.35, bs=0.73, hc=1.59, volume=0.075 / (100 ** 3), axes_alignment=np.array([1.0, 0, 0]))
    rod2 = HysteresisRod(br=0.35, bs=0.73, hc=1.59, volume=0.075 / (100 ** 3), axes_alignment=np.array([0, 1.0, 0]))
    cubesat = CubeSatModel(inertia=np.diag([8 * (10 ** -3), 8 * (10 ** -3), 2 * (10 ** -3)]),
                           magnetic_moment=np.array([0, 0, 1.5]),
                           hyst_rods=[rod1, rod2])
    cubesat_params = cubesat.asdict()

    # Run simulation
    data = sim_attitude(sim_params, cubesat_params, 'sim1', save=True, ret=True)

    # run the simulation longer
    # continue_sim(data, 30, 'test1')