"""Electrical loads engine: power flow, time-domain loads, and validation."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np


def example_project():
    return {
        'name': '28 V Avionics Power Budget', 'duration_s': 60.0, 'dt_s': 0.1, 'mission_enabled': False, 'mission_phases': [],
        'buses': [
            {'id': 'BUS28', 'name': 'Primary 28 V', 'voltage_v': 28.0, 'source_limit_a': 12.0},
            {'id': 'BUS12', 'name': '12 V Regulated', 'voltage_v': 12.0, 'source_limit_a': 0},
            {'id': 'BUS5', 'name': '5 V Regulated', 'voltage_v': 5.0, 'source_limit_a': 0},
            {'id': 'BUS3V3', 'name': '3.3 V Digital', 'voltage_v': 3.3, 'source_limit_a': 0},
        ],
        'converters': [
            {'id': 'DCDC1', 'name': '28-to-12', 'input_bus': 'BUS28', 'output_bus': 'BUS12', 'efficiency': 0.91, 'max_output_a': 8.0, 'quiescent_input_a': 0.018},
            {'id': 'DCDC2', 'name': '12-to-5', 'input_bus': 'BUS12', 'output_bus': 'BUS5', 'efficiency': 0.90, 'max_output_a': 6.0, 'quiescent_input_a': 0.010},
            {'id': 'DCDC3', 'name': '5-to-3.3', 'input_bus': 'BUS5', 'output_bus': 'BUS3V3', 'efficiency': 0.88, 'max_output_a': 3.0, 'quiescent_input_a': 0.006},
        ],
        'loads': [
            {'id': 'L1', 'name': 'Radio', 'bus': 'BUS28', 'min_a': 0.20, 'nom_a': 0.55, 'max_a': 1.80, 'profile': [{'time_s': 0, 'current_a': 0.3}, {'time_s': 10, 'current_a': 1.7}, {'time_s': 13, 'current_a': 0.3}, {'time_s': 35, 'current_a': 1.7}, {'time_s': 39, 'current_a': 0.3}]},
            {'id': 'L2', 'name': 'Actuator', 'bus': 'BUS12', 'min_a': 0.0, 'nom_a': 0.75, 'max_a': 3.0, 'profile': [{'time_s': 0, 'current_a': 0}, {'time_s': 18, 'current_a': 2.8}, {'time_s': 23, 'current_a': 0.2}, {'time_s': 45, 'current_a': 2.8}, {'time_s': 50, 'current_a': 0.2}]},
            {'id': 'L3', 'name': 'SBC', 'bus': 'BUS5', 'min_a': 0.6, 'nom_a': 1.3, 'max_a': 2.0, 'profile': []},
            {'id': 'L4', 'name': 'MCU and Sensors', 'bus': 'BUS3V3', 'min_a': 0.12, 'nom_a': 0.26, 'max_a': 0.48, 'profile': []},
        ],
    }


def validate(project):
    buses = project['buses']; converters = project['converters']; loads = project['loads']
    if float(project['dt_s']) <= 0 or float(project['duration_s']) <= 0:
        raise ValueError('Duration and timestep must both be positive.')
    if float(project['duration_s']) / float(project['dt_s']) > 250_000:
        raise ValueError('Too many samples (limit 250,000). Increase the timestep.')
    ids = [b['id'] for b in buses]
    if len(ids) != len(set(ids)) or not ids: raise ValueError('Bus IDs must be unique, with at least one bus.')
    all_object_ids=[o['id'] for k in ('buses','converters','loads') for o in project[k]]
    if len(all_object_ids)!=len(set(all_object_ids)) or any(not x for x in all_object_ids):
        raise ValueError('All bus, converter and equipment IDs must be unique and non-empty.')
    for b in buses:
        if float(b['voltage_v']) <= 0: raise ValueError(f"Bus {b['id']} voltage must be positive.")
        if float(b.get('source_limit_a', 0)) < 0: raise ValueError('Source limits cannot be negative.')
    seen_outputs = set(); incoming = {}
    for c in converters:
        a, b = c['input_bus'], c['output_bus']
        if a not in ids or b not in ids or a == b: raise ValueError(f"Converter {c['id']} has invalid bus connections.")
        if b in seen_outputs: raise ValueError(f'Bus {b} has multiple upstream converters (unsupported).')
        seen_outputs.add(b); incoming[b] = a
        if not (0 < float(c['efficiency']) <= 1): raise ValueError(f"Converter {c['id']} efficiency must be within (0, 1].")
        if float(c['max_output_a']) <= 0 or float(c.get('quiescent_input_a', 0)) < 0: raise ValueError('Invalid converter rating or quiescent current.')
    for bus in ids:
        trail=set(); current=bus
        while current in incoming:
            if current in trail: raise ValueError('Converter graph contains a cycle.')
            trail.add(current); current=incoming[current]
    phases=project.get('mission_phases', [])
    if project.get('mission_enabled',False) and not phases:
        raise ValueError('Mission is enabled but no phases are defined.')
    for phase in phases:
        if not str(phase.get('name','')).strip() or float(phase.get('duration_s',0)) <= 0:
            raise ValueError('Mission phase needs a name and positive duration.')
        if not isinstance(phase.get('states',{}),dict):raise ValueError('Phase states must be a mapping.')
        for load_id, state in phase.get('states',{}).items():
            if load_id not in [l['id'] for l in loads]:raise ValueError(f'Unknown equipment {load_id} in mission.')
            if state not in ('default','off','min','nom','max','duty','profile'):
                raise ValueError(f'Unknown mission state {state}.')
    for l in loads:
        if l['bus'] not in ids: raise ValueError(f"Load {l['id']} has an unknown bus.")
        mn, nom, mx = (float(l[k]) for k in ('min_a', 'nom_a', 'max_a'))
        if not 0 <= mn <= nom <= mx: raise ValueError(f"Load {l['id']} must have 0 <= min <= nominal <= max.")
        method=l.get('load_mode','profile')
        if method not in ('profile','nominal','duty'): raise ValueError(f"Load {l['id']}: invalid load mode {method}")
        if method=='duty':
            duty=float(l.get('duty_pct',50)); period=float(l.get('period_s',10)); phase=float(l.get('phase_s',0))
            on=float(l.get('on_a',l['max_a'])); off=float(l.get('off_a',l['min_a']))
            if not 0 <= duty <= 100 or period <= 0 or phase < 0 or not (0 <= off <= float(l['max_a']) and 0 <= on <= float(l['max_a'])):
                raise ValueError(f"Load {l['id']}: duty must be 0..100%, period positive, phase nonnegative and currents within 0..max A.")
        times = [float(p['time_s']) for p in l.get('profile', [])]
        currents = [float(p['current_a']) for p in l.get('profile', [])]
        if len(set(times)) != len(times) or any(t < 0 for t in times) or any(i < 0 for i in currents):
            raise ValueError(f"Load {l['id']} profile has duplicate/negative times or negative current.")
    return True


def simulate(project, mode='profile'):
    """Profiles are zero-order held (piecewise constant); fallback is nominal current.

    Each output bus has exactly one upstream converter; bus voltage is assumed
    constant and conversion is a constant-efficiency power balance.
    """
    validate(project)
    dt=float(project['dt_s']); duration=float(project['duration_s'])
    t = np.arange(int(np.floor(duration/dt + 1e-9)) + 1, dtype=float)*dt
    if t[-1] < duration - 1e-9: t=np.append(t, duration)
    buses={b['id']:b for b in project['buses']}; converters=project['converters']
    load_i={}; direct={key:np.zeros(t.size) for key in buses}
    for l in project['loads']:
        if mode in ('min', 'nom', 'max'):
            x=np.full(t.size, float(l[{'min':'min_a','nom':'nom_a','max':'max_a'}[mode]]))
        elif l.get('load_mode','profile')=='duty':
            period=float(l.get('period_s',10)); duty=float(l.get('duty_pct',50))/100
            phase=float(l.get('phase_s',0)); on=float(l.get('on_a',l['max_a'])); off=float(l.get('off_a',l['min_a']))
            # A periodic rectangular load, on from start of period for duty*period.
            fraction=np.mod(t+phase,period)/period
            x=np.where(fraction < duty,on,off)
        elif l.get('load_mode','profile')=='nominal':
            x=np.full(t.size,float(l['nom_a']))
        else:
            pts=sorted(l.get('profile', []), key=lambda p:float(p['time_s']))
            x=np.full(t.size, float(l['nom_a']))
            if pts:
                xp=np.array([float(p['time_s']) for p in pts]); fp=np.array([float(p['current_a']) for p in pts])
                indices=np.searchsorted(xp,t,side='right')-1
                mask=indices>=0
                x[mask]=fp[indices[mask]]
        if mode=='profile' and project.get('mission_enabled',False):
            # Phase durations define sequential intervals. When they end, loads return
            # to their configured default schedules for the remainder of simulation.
            start=0.0
            for phase in project.get('mission_phases',[]):
                stop=start+float(phase['duration_s'])
                mask=(t>=start-1e-10)&(t<stop-1e-10)
                state=phase.get('states',{}).get(l['id'],'default')
                if np.any(mask) and state!='default':
                    if state=='off':x[mask]=0.0
                    elif state in ('min','nom','max'):
                        x[mask]=float(l[{'min':'min_a','nom':'nom_a','max':'max_a'}[state]])
                    elif state=='duty':
                        period=float(l.get('period_s',10));duty=float(l.get('duty_pct',50))/100
                        phase_offset=float(l.get('phase_s',0))
                        frac=np.mod((t[mask]-start)+phase_offset,period)/period
                        x[mask]=np.where(frac<duty,float(l.get('on_a',l['max_a'])),float(l.get('off_a',l['min_a'])))
                    elif state=='profile':
                        pts=sorted(l.get('profile',[]),key=lambda q:float(q['time_s']))
                        local=t[mask]-start
                        x[mask]=float(l['nom_a'])
                        if pts:
                            xp=np.array([float(q['time_s']) for q in pts]);fp=np.array([float(q['current_a']) for q in pts])
                            ind=np.searchsorted(xp,local,side='right')-1; valid=ind>=0
                            chunk=x[mask];chunk[valid]=fp[ind[valid]];x[mask]=chunk
                start=stop
        load_i[l['id']]=x; direct[l['bus']] += x
    conv_by_output={c['output_bus']:c for c in converters}
    order=[]; visited=set()
    def walk(bus):
        if bus in visited:return
        visited.add(bus)
        for c in converters:
            if c['input_bus']==bus:walk(c['output_bus'])
        order.append(bus)
    for bid in buses:walk(bid)
    bus_i={k:v.copy() for k,v in direct.items()}; conv_in={}; conv_out={}
    for bid in order:
        c=conv_by_output.get(bid)
        if c:
            conv_out[c['id']]=bus_i[bid].copy()
            # downstream demand is fed by converter. All currents drawn at nominal bus voltages.
            pin=bus_i[bid]*float(buses[bid]['voltage_v'])/float(c['efficiency'])
            ii=pin/float(buses[c['input_bus']]['voltage_v']) + float(c.get('quiescent_input_a',0))
            conv_in[c['id']]=ii
            bus_i[c['input_bus']] += ii
    roots=[bid for bid in buses if bid not in conv_by_output]
    source_p=sum((bus_i[r]*float(buses[r]['voltage_v']) for r in roots),np.zeros_like(t))
    source_i={rid:bus_i[rid] for rid in roots}
    total_source_i=source_i[roots[0]].copy() if len(roots)==1 else None
    bus_p={bid:bus_i[bid]*float(buses[bid]['voltage_v']) for bid in buses}
    loss_p={c['id']: conv_in[c['id']]*float(buses[c['input_bus']]['voltage_v']) - conv_out[c['id']]*float(buses[c['output_bus']]['voltage_v']) for c in converters}
    issues=[]
    for c in converters:
        peak=float(conv_out[c['id']].max()); rated=float(c['max_output_a'])
        if peak>rated+1e-9:issues.append(f"Converter {c['id']}: peak {peak:.3f} A exceeds {rated:.3f} A output rating")
    for bid,b in buses.items():
        rated=float(b.get('source_limit_a',0))
        if bid in roots and rated>0 and bus_i[bid].max()>rated+1e-9:
            issues.append(f"Source {bid}: peak {bus_i[bid].max():.3f} A exceeds {rated:.3f} A limit")
    for l in project['loads']:
        peak=float(load_i[l['id']].max()); bound=float(l['max_a'])
        if peak>bound+1e-9:issues.append(f"Load {l['id']}: profile peak {peak:.3f} A exceeds specified max {bound:.3f} A")
    return dict(t=t,bus_i=bus_i,load_i=load_i,conv_in=conv_in,conv_out=conv_out,
                source_p=source_p,source_i=source_i,total_source_i=total_source_i,bus_p=bus_p,loss_p=loss_p,issues=issues,roots=roots,buses=buses)


def save_project(project,path):
    validate(project)
    Path(path).write_text(json.dumps(project,indent=2),encoding='utf-8')


def load_project(path):
    project=json.loads(Path(path).read_text(encoding='utf-8'));validate(project);return project
