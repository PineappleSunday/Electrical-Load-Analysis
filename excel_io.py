"""Human-editable, lossless Excel round-trip for ELA project data."""
import copy
import json
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from engine import validate

SHEETS={
    'Buses':['id','name','voltage_v','source_limit_a'],
    'Converters':['id','name','input_bus','output_bus','efficiency','max_output_a','quiescent_input_a'],
    'Equipment':['id','name','bus','min_a','nom_a','max_a','load_mode','duty_pct','period_s','phase_s','on_a','off_a'],
    'Load Profiles':['load_id','time_s','current_a'],
    'Mission Phases':['phase_order','name','duration_s'],
    'Phase States':['phase_order','load_id','state'],
    'Layout':['component_id','x','y'],
}
NUMBER_FIELDS={'voltage_v','source_limit_a','efficiency','max_output_a','quiescent_input_a','min_a','nom_a','max_a','duty_pct','period_s','phase_s','on_a','off_a','time_s','current_a','duration_s','x','y'}
SCHEMA_VERSION=1

def _rows(sheet, columns):
    header=[sheet.cell(1,c).value for c in range(1,len(columns)+1)]
    if header!=columns:raise ValueError(f"Worksheet '{sheet.title}' headers were modified; expected {columns}")
    for row_num,cells in enumerate(sheet.iter_rows(min_row=2,max_col=len(columns),values_only=True),2):
        if all(v is None or v=='' for v in cells):continue
        row=dict(zip(columns,cells))
        for key,value in list(row.items()):
            if key in NUMBER_FIELDS and value not in (None,''):
                try:row[key]=float(value)
                except (ValueError,TypeError):raise ValueError(f"{sheet.title} row {row_num}: '{key}' must be a number")
            elif isinstance(value,str):row[key]=value.strip()
        yield row_num,row

def _put(ws, columns, records):
    ws.append(columns)
    for row in records:
        ws.append([row.get(c) for c in columns])
    ws.freeze_panes='A2';ws.auto_filter.ref=f'A1:{get_column_letter(len(columns))}{max(2,ws.max_row)}'
    for cell in ws[1]:
        cell.fill=PatternFill('solid',fgColor='19324E');cell.font=Font(color='FFFFFF',bold=True)
        cell.alignment=Alignment(vertical='center')
    ws.row_dimensions[1].height=27
    for col_idx,col in enumerate(columns,1):
        ws.column_dimensions[get_column_letter(col_idx)].width=min(38,max(15,len(col)+5))
        if col in NUMBER_FIELDS:
            for cells in ws.iter_cols(min_col=col_idx,max_col=col_idx,min_row=2):
                for cell in cells:cell.number_format='0.0000'
    if ws.title=='Equipment':
        rule=DataValidation(type='list',formula1='"nominal,profile,duty"',allow_blank=True);ws.add_data_validation(rule);rule.add(f'G2:G{max(500,ws.max_row+100)}')
    if ws.title=='Phase States':
        rule=DataValidation(type='list',formula1='"default,off,min,nom,max,duty,profile"',allow_blank=True);ws.add_data_validation(rule);rule.add(f'C2:C{max(1000,ws.max_row+100)}')

def export_excel(project,path):
    validate(project)
    wb=Workbook();intro=wb.active;intro.title='Read Me'
    info=[['ELECTRICAL LOADS WORKBENCH — EDITABLE PROJECT'],['Edit the data worksheets, then use File > Import Excel Project.'],['Do not rename worksheets, column headers, or component IDs without updating their references.'],['Add equipment in Equipment; attach it using the Bus ID.'],['Add step-held load points in Load Profiles with their Equipment ID.'],['Create mission phases in Mission Phases; use phase_order (1, 2, 3...) to control sequence.'],['Use Phase States with phase_order and load_id to override selected equipment in each phase.'],['Unlisted phase states use equipment defaults.'],['Layout coordinates and custom project metadata are retained.'],['Simulation duration and timestep are in Project Settings.']]
    for r in info:intro.append(r)
    intro.column_dimensions['A'].width=110
    intro['A1'].font=Font(bold=True,size=16,color='19324E')
    settings=wb.create_sheet('Project Settings');_put(settings,['setting','value'],[
        {'setting':'name','value':project['name']},{'setting':'duration_s','value':project['duration_s']},
        {'setting':'dt_s','value':project['dt_s']},{'setting':'mission_enabled','value':bool(project.get('mission_enabled',False))},
        {'setting':'schema_version','value':SCHEMA_VERSION}])
    for title,cols in SHEETS.items():
        rows=[]
        if title=='Buses':rows=project['buses']
        elif title=='Converters':rows=project['converters']
        elif title=='Equipment':rows=project['loads']
        elif title=='Load Profiles':rows=[dict(load_id=l['id'],**p) for l in project['loads'] for p in l.get('profile',[])]
        elif title=='Mission Phases':rows=[dict(phase_order=i,name=p['name'],duration_s=p['duration_s']) for i,p in enumerate(project.get('mission_phases',[]),1)]
        elif title=='Phase States':rows=[dict(phase_order=i,load_id=k,state=v) for i,p in enumerate(project.get('mission_phases',[]),1) for k,v in p.get('states',{}).items()]
        elif title=='Layout':
            for k,coords in project.get('layout',{}).items():
                if isinstance(coords,(list,tuple)) and len(coords)>=2:rows.append({'component_id':k,'x':coords[0],'y':coords[1]})
                elif isinstance(coords,dict):rows.append({'component_id':k,'x':coords.get('x',0),'y':coords.get('y',0)})
        _put(wb.create_sheet(title),cols,rows)
    # Keeps unknown future metadata without obscuring human-editable tables.
    extra={k:v for k,v in project.items() if k not in ('name','duration_s','dt_s','mission_enabled','buses','converters','loads','mission_phases','layout')}
    meta=wb.create_sheet('Extra Metadata');_put(meta,['key','json_value'],[{'key':k,'json_value':json.dumps(v)} for k,v in extra.items()]);meta.sheet_state='hidden'
    wb.save(path)

def import_excel(path):
    wb=load_workbook(path,data_only=True)
    required=['Project Settings',*SHEETS]
    missing=[s for s in required if s not in wb]
    if missing:raise ValueError('Missing worksheets: '+', '.join(missing))
    settings=dict((str(v[0]).strip(),v[1]) for v in wb['Project Settings'].iter_rows(min_row=2,max_col=2,values_only=True) if v[0] is not None)
    if int(settings.get('schema_version',-1))!=SCHEMA_VERSION:raise ValueError('Unsupported workbook schema version.')
    enabled=settings.get('mission_enabled',False)
    if isinstance(enabled,str):enabled=enabled.strip().lower() in ('true','1','yes')
    project={'name':str(settings['name']),'duration_s':float(settings['duration_s']),'dt_s':float(settings['dt_s']),
             'mission_enabled':bool(enabled)}
    for tab,key in [('Buses','buses'),('Converters','converters'),('Equipment','loads')]:
        project[key]=[]
        for n,row in _rows(wb[tab],SHEETS[tab]):
            if not row.get('id'):raise ValueError(f'{tab} row {n}: ID is required')
            project[key].append({k:v for k,v in row.items() if v not in (None,'')})
    profile_by_load={l['id']:[] for l in project['loads']}
    for n,row in _rows(wb['Load Profiles'],SHEETS['Load Profiles']):
        lid=row.get('load_id')
        if lid not in profile_by_load:raise ValueError(f'Load Profiles row {n}: unknown equipment ID {lid}')
        profile_by_load[lid].append({'time_s':row['time_s'],'current_a':row['current_a']})
    for l in project['loads']:l['profile']=sorted(profile_by_load[l['id']],key=lambda p:p['time_s'])
    phases={}
    for n,row in _rows(wb['Mission Phases'],SHEETS['Mission Phases']):
        try:order=int(row['phase_order'])
        except (ValueError,TypeError,KeyError):raise ValueError(f'Mission Phases row {n}: invalid phase order')
        if order<1 or order in phases:raise ValueError(f'Mission Phases row {n}: duplicate/invalid phase order')
        phases[order]={'name':str(row['name']),'duration_s':row['duration_s'],'states':{}}
    for n,row in _rows(wb['Phase States'],SHEETS['Phase States']):
        order=int(row['phase_order']);lid=row.get('load_id')
        if order not in phases:raise ValueError(f'Phase States row {n}: unknown mission phase {order}')
        if lid not in profile_by_load:raise ValueError(f'Phase States row {n}: unknown equipment ID {lid}')
        if lid in phases[order]['states']:raise ValueError(f'Phase States row {n}: repeated state for {lid}')
        phases[order]['states'][lid]=str(row['state'])
    project['mission_phases']=[phases[i] for i in sorted(phases)]
    layout={}
    for n,row in _rows(wb['Layout'],SHEETS['Layout']):
        if row.get('component_id'):layout[row['component_id']]=[row['x'],row['y']]
    project['layout']=layout
    if 'Extra Metadata' in wb:
        for cells in wb['Extra Metadata'].iter_rows(min_row=2,max_col=2,values_only=True):
            if cells[0] is not None:project[str(cells[0])]=json.loads(cells[1])
    validate(project)
    return project
