"""Electrical Loads Workbench - standard Tkinter desktop user interface."""
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from engine import example_project, simulate, save_project, load_project
from diagram import Architecture
from phase_overlay import add_phase_overlay, add_mission_timeline
from id_utils import next_load_id

FIELDS={
'buses': [('id','Bus ID','str'),('name','Name','str'),('voltage_v','Voltage (V)','float'),('source_limit_a','Source current limit (A), 0=none','float')],
'converters': [('id','Converter ID','str'),('name','Name','str'),('input_bus','Input bus ID','str'),('output_bus','Output bus ID','str'),('efficiency','Efficiency (0..1)','float'),('max_output_a','Max output current (A)','float'),('quiescent_input_a','Quiescent input current (A)','float')],
'loads': [('id','Load ID','str'),('name','Name','str'),('bus','Bus ID','str'),('min_a','Minimum current (A)','float'),('nom_a','Nominal current (A)','float'),('max_a','Maximum current (A)','float')]
}

def resultpane_index(notebook, label):
    for i,tab in enumerate(notebook.tabs()):
        if notebook.tab(tab,'text') == label:return i
    return 0

class Editor(tk.Toplevel):
    def __init__(self,parent,kind,existing=None):
        super().__init__(parent); self.title(('Edit ' if existing else 'Add ')+kind[:-1]);self.resizable(False,False)
        self.result=None;self.kind=kind;self.original=existing or {};self.vars={}
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        self.proposed_id = next_load_id(parent.project) if kind == 'loads' and existing is None else None
        for n,(key,label,typ) in enumerate(FIELDS[kind]):
            ttk.Label(body,text=label).grid(row=n,column=0,sticky='w',padx=(0,12),pady=4)
            val=self.original.get(key, self.proposed_id if key == 'id' and self.proposed_id else '')
            if key in ('input_bus','output_bus','bus'):
                opts=[b['id'] for b in parent.project['buses']]
                v=tk.StringVar(value=str(val or (opts[0] if opts else '')))
                ctl=ttk.Combobox(body,textvariable=v,values=opts,state='readonly',width=29)
            else:
                v=tk.StringVar(value=str(val));ctl=ttk.Entry(body,textvariable=v,width=32)
            ctl.grid(row=n,column=1,sticky='ew',pady=4);self.vars[key]=v
            if key == 'id' and self.proposed_id:
                ttk.Label(body,text='Auto-generated; edit to use your own ID.',foreground='#64748b').grid(row=n,column=2,sticky='w',padx=8)
        if kind=='loads':
            rr=len(FIELDS[kind]);self.load_mode=tk.StringVar(value=self.original.get('load_mode','profile'))
            ttk.Label(body,text='Load schedule').grid(row=rr,column=0,sticky='w',pady=4)
            ttk.Combobox(body,textvariable=self.load_mode,values=['nominal','profile','duty'],state='readonly',width=29).grid(row=rr,column=1,sticky='ew')
            self.duty_vars={}
            specs=[('duty_pct','Duty cycle (%)',50),('period_s','Cycle period (s)',10),('phase_s','Cycle phase offset (s)',0),('on_a','ON current (A)',self.original.get('max_a',0)),('off_a','OFF current (A)',self.original.get('min_a',0))]
            for ii,(key,label,default) in enumerate(specs,rr+1):
                ttk.Label(body,text=label).grid(row=ii,column=0,sticky='w',pady=2)
                v=tk.StringVar(value=str(self.original.get(key,default)));self.duty_vars[key]=v
                ttk.Entry(body,textvariable=v,width=32).grid(row=ii,column=1,sticky='ew',pady=2)
        if kind=='loads':
            r=len(FIELDS[kind])+6;ttk.Label(body,text='Dynamic profile: time_s, current_A per line\nStep-held; empty = nominal current.',justify='left').grid(row=r,column=0,columnspan=2,sticky='w',pady=(12,4))
            self.profile=tk.Text(body,width=42,height=9,undo=True)
            self.profile.grid(row=r+1,column=0,columnspan=2)
            for p in self.original.get('profile',[]):self.profile.insert('end',f"{p['time_s']}, {p['current_a']}\n")
        buttons=ttk.Frame(body);buttons.grid(row=99,column=0,columnspan=2,sticky='e',pady=(16,0))
        ttk.Button(buttons,text='Cancel',command=self.destroy).pack(side='right',padx=4)
        ttk.Button(buttons,text='Save',command=self.commit).pack(side='right')
        # Place edit popup centered over the main application (not wherever the
        # window manager last put a popup). Clamp to the usable screen bounds.
        self.update_idletasks()
        parent.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(px + (pw-w)//2, screen_w-w))
        y = max(0, min(py + (ph-h)//2, screen_h-h))
        self.geometry(f'+{x}+{y}')
        self.transient(parent);self.grab_set();self.lift()
        self.bind('<Escape>',lambda e:self.destroy());self.wait_window()

    def commit(self):
        try:
            d={key:(float(self.vars[key].get()) if typ=='float' else self.vars[key].get().strip()) for key,_,typ in FIELDS[self.kind]}
            if not all(d[k] for k in ('id','name')):raise ValueError('ID and name are required.')
            if self.kind=='loads':
                d['load_mode']=self.load_mode.get()
                for key,var in self.duty_vars.items(): d[key]=float(var.get())
                d['profile']=[]
                for n,line in enumerate(self.profile.get('1.0','end').splitlines(),1):
                    if not line.strip():continue
                    vals=[s.strip() for s in line.replace('\t',',').split(',')]
                    if len(vals)!=2:raise ValueError(f'Profile line {n}: expected time, current')
                    d['profile'].append({'time_s':float(vals[0]),'current_a':float(vals[1])})
            self.result=d;self.destroy()
        except ValueError as e:messagebox.showerror('Invalid entry',str(e),parent=self)

class BulkEdit(tk.Toplevel):
    """Apply only checked fields to the selected rows."""
    FIELDS=[('bus','Bus assignment'),('min_a','Minimum current (A)'),('nom_a','Nominal current (A)'),('max_a','Maximum current (A)'),('load_mode','Load schedule'),('duty_pct','Duty %'),('period_s','Duty period (s)'),('on_a','ON current (A)'),('off_a','OFF current (A)')]
    def __init__(self,app,indices):
        super().__init__(app);self.title(f'Bulk edit {len(indices)} equipment loads');self.result=None
        self.resizable(False,False)
        outer=ttk.Frame(self,padding=15);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text=f'Apply checked fields to {len(indices)} selected equipment rows. Unchecked fields stay unchanged.').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,10))
        self.fields={}
        for i,(key,title) in enumerate(self.FIELDS,1):
            selected=tk.BooleanVar(value=False);val=tk.StringVar()
            ttk.Checkbutton(outer,variable=selected).grid(row=i,column=0,sticky='w')
            ttk.Label(outer,text=title).grid(row=i,column=1,sticky='w',padx=10,pady=3)
            if key=='bus': w=ttk.Combobox(outer,textvariable=val,values=[b['id'] for b in app.project['buses']],state='readonly',width=20)
            elif key=='load_mode':w=ttk.Combobox(outer,textvariable=val,values=['nominal','profile','duty'],state='readonly',width=20)
            else:w=ttk.Entry(outer,textvariable=val,width=23)
            w.grid(row=i,column=2,sticky='ew');self.fields[key]=(selected,val)
        foot=ttk.Frame(outer);foot.grid(row=20,column=0,columnspan=3,sticky='e',pady=(14,0))
        ttk.Button(foot,text='Cancel',command=self.destroy).pack(side='right',padx=4)
        ttk.Button(foot,text='Apply',command=self.commit).pack(side='right')
        self.transient(app);self.grab_set();self.wait_window()
    def commit(self):
        try:
            d={}
            for key,(checked,val) in self.fields.items():
                if checked.get():
                    v=val.get().strip()
                    if not v:raise ValueError(f'{key} needs a value.')
                    d[key]=v if key in ('bus','load_mode') else float(v)
            if not d:raise ValueError('Select at least one field to change.')
            self.result=d;self.destroy()
        except ValueError as exc:messagebox.showerror('Bulk edit',str(exc),parent=self)

class MissionPhaseEditor(tk.Toplevel):
    def __init__(self,app,phase=None):
        super().__init__(app);self.title('Mission Phase');self.geometry('550x520');self.result=None
        phase=phase or {};body=ttk.Frame(self,padding=12);body.pack(fill='both',expand=True)
        top=ttk.Frame(body);top.pack(fill='x')
        ttk.Label(top,text='Phase name').grid(row=0,column=0,sticky='w',pady=5)
        self.name=tk.StringVar(value=phase.get('name',''));ttk.Entry(top,textvariable=self.name,width=30).grid(row=0,column=1,padx=8)
        ttk.Label(top,text='Duration (s)').grid(row=1,column=0,sticky='w',pady=5)
        self.duration=tk.StringVar(value=str(phase.get('duration_s',10)))
        ttk.Entry(top,textvariable=self.duration,width=15).grid(row=1,column=1,sticky='w',padx=8)
        ttk.Label(body,text='Select a load and assign its operating state. Default uses the load’s own schedule.',wraplength=520).pack(anchor='w',pady=(12,7))
        options=['default','off','min','nom','max','duty','profile']
        self.states={};frame=ttk.Frame(body);frame.pack(fill='both',expand=True)
        canv=tk.Canvas(frame,highlightthickness=0);scroll=ttk.Scrollbar(frame,orient='vertical',command=canv.yview)
        inner=ttk.Frame(canv);inner.bind('<Configure>',lambda ev:canv.configure(scrollregion=canv.bbox('all')))
        canv.create_window((0,0),window=inner,anchor='nw');canv.configure(yscrollcommand=scroll.set)
        canv.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        for i,l in enumerate(app.project['loads']):
            ttk.Label(inner,text=f"{l['name']} ({l['id']})",width=34).grid(row=i,column=0,sticky='w',pady=3)
            v=tk.StringVar(value=phase.get('states',{}).get(l['id'],'default'));self.states[l['id']]=v
            ttk.Combobox(inner,values=options,textvariable=v,state='readonly',width=15).grid(row=i,column=1,pady=3)
        bottom=ttk.Frame(body);bottom.pack(fill='x',pady=8)
        ttk.Button(bottom,text='Cancel',command=self.destroy).pack(side='right',padx=5)
        ttk.Button(bottom,text='Save phase',command=self.commit).pack(side='right')
        self.transient(app);self.grab_set();self.wait_window()
    def commit(self):
        try:
            duration=float(self.duration.get())
            if duration<=0 or not self.name.get().strip():raise ValueError('Enter a name and positive duration.')
            self.result={'name':self.name.get().strip(),'duration_s':duration,'states':{k:v.get() for k,v in self.states.items() if v.get()!='default'}}
            self.destroy()
        except ValueError as exc:messagebox.showerror('Mission phase',str(exc),parent=self)

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('Electrical Loads Workbench');self.geometry('1270x850');self.minsize(970,620)
        self.project=example_project();self.path=None;self.results=None
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('Treeview',rowheight=25)
        menu=tk.Menu(self);filemenu=tk.Menu(menu,tearoff=0)
        for title,cmd in [('New',self.new),('Open JSON...',self.open),('Save',self.save),('Save As...',self.save_as),('Export Excel Project...',self.export_excel),('Import Excel Project...',self.import_excel),('Export PDF Report...',self.report),('Export Time Series CSV...',self.export_csv)]:filemenu.add_command(label=title,command=cmd)
        menu.add_cascade(label='File',menu=filemenu);self.config(menu=menu)
        top=ttk.Frame(self,padding=10);top.pack(fill='x')
        ttk.Label(top,text='Project').pack(side='left');self.name=tk.StringVar();ttk.Entry(top,textvariable=self.name,width=33).pack(side='left',padx=7)
        ttk.Label(top,text='Duration (s)').pack(side='left',padx=(12,3));self.duration=tk.StringVar();ttk.Entry(top,textvariable=self.duration,width=9).pack(side='left')
        ttk.Label(top,text='Step (s)').pack(side='left',padx=(12,3));self.dt=tk.StringVar();ttk.Entry(top,textvariable=self.dt,width=9).pack(side='left')
        ttk.Button(top,text='Run Analysis',command=self.run).pack(side='left',padx=12)
        ttk.Button(top,text='PDF Report',command=self.report).pack(side='left')
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=10,pady=(0,8))
        self.trees={}
        self.diagram=Architecture(self.tabs,self);self.tabs.add(self.diagram,text='Architecture')
        for kind in FIELDS:
            pane=ttk.Frame(self.tabs,padding=8);self.tabs.add(pane,text={'buses':'Voltage Buses','converters':'Converters','loads':'Equipment Loads'}[kind])
            bar=ttk.Frame(pane);bar.pack(fill='x',pady=(0,6))
            ttk.Button(bar,text='+ Add',command=lambda k=kind:self.add(k)).pack(side='left',padx=(0,6))
            ttk.Button(bar,text='Edit Selected',command=lambda k=kind:self.edit(k)).pack(side='left',padx=6)
            ttk.Button(bar,text='Delete Selected',command=lambda k=kind:self.delete(k)).pack(side='left',padx=6)
            cols=[x[0] for x in FIELDS[kind]]
            if kind=='loads':
                cols.extend(['load_mode','duty_pct','period_s','profile'])
                ttk.Button(bar,text='Bulk Edit Selected...',command=self.bulk_edit).pack(side='left',padx=6)
                ttk.Button(bar,text='Select All',command=lambda:self.trees['loads'].selection_set(self.trees['loads'].get_children())).pack(side='left',padx=6)
            tree=ttk.Treeview(pane,columns=cols,show='headings',selectmode='extended' if kind=='loads' else 'browse')
            for col in cols:
                label=next((x[1] for x in FIELDS[kind] if x[0]==col),'Profile points')
                tree.heading(col,text=label);tree.column(col,width=130 if col!='name' else 190,stretch=True)
            tree.pack(fill='both',expand=True);tree.bind('<Double-1>',lambda ev,k=kind:self.edit(k));self.trees[kind]=tree
        missionpane=ttk.Frame(self.tabs,padding=10);self.tabs.add(missionpane,text='Mission Profile')
        missionbar=ttk.Frame(missionpane);missionbar.pack(fill='x',pady=5)
        self.mission_enabled=tk.BooleanVar(value=False)
        ttk.Checkbutton(missionbar,text='Enable mission phase simulation',variable=self.mission_enabled,command=self.mission_toggle).pack(side='left',padx=(0,14))
        for label,cmd in [('+ Phase',self.add_phase),('Edit Phase',self.edit_phase),('Delete Phase',self.delete_phase),('Move Up',lambda:self.move_phase(-1)),('Move Down',lambda:self.move_phase(1))]:
            ttk.Button(missionbar,text=label,command=cmd).pack(side='left',padx=3)
        self.phase_tree=ttk.Treeview(missionpane,columns=['name','duration','start','end','overrides'],show='headings',selectmode='browse')
        for k,label in [('name','Phase'),('duration','Duration (s)'),('start','Start (s)'),('end','End (s)'),('overrides','Equipment overrides')]:
            self.phase_tree.heading(k,text=label);self.phase_tree.column(k,width=170)
        self.phase_tree.pack(fill='both',expand=True,pady=8)
        self.phase_tree.bind('<Double-1>',lambda event:self.edit_phase())
        ttk.Label(missionpane,text='Mission phases run in listed order, from t=0. A phase state overrides the equipment default. Duty and profile states use that equipment’s configured waveform, restarted at the phase boundary. Unspecified equipment uses its default schedule. After the mission ends, equipment returns to its default schedule.',wraplength=1060).pack(anchor='w',pady=8)
        resultpane=ttk.Frame(self.tabs,padding=8);self.tabs.add(resultpane,text='Analysis')
        self.summary=tk.Text(resultpane,height=10,wrap='none',font=('Consolas',10));self.summary.pack(fill='x')
        self.figure=Figure(figsize=(9,5),dpi=100);self.ax=self.figure.add_subplot(111)
        self.canvas=FigureCanvasTkAgg(self.figure,master=resultpane);self.canvas.get_tk_widget().pack(fill='both',expand=True)
        bottom=ttk.Frame(resultpane);bottom.pack(fill='x',pady=6)
        ttk.Label(bottom,text='Plot').pack(side='left');self.plotmode=tk.StringVar(value='Dashboard')
        combo=ttk.Combobox(bottom,textvariable=self.plotmode,values=['Dashboard','Total Power','Total Source Current','Bus Current','Bus Power','Source Power','Converter Dissipation','Equipment Current','Flight Phase Timeline'],state='readonly',width=25)
        combo.pack(side='left',padx=6);combo.bind('<<ComboboxSelected>>',lambda e:self.plot())
        ttk.Label(resultpane,text='Assumptions: constant bus voltage; ideal source; constant converter efficiency; no startup/inrush unless profiled; profiles are step-held.').pack(anchor='w')
        warningpane=ttk.Frame(self.tabs,padding=8)
        self.tabs.add(warningpane,text='Warnings & Errors')
        tools=ttk.Frame(warningpane);tools.pack(fill='x',pady=(0,8))
        ttk.Label(tools,text='Analysis diagnostics (run analysis to refresh)').pack(side='left')
        ttk.Button(tools,text='Go to Selected Component',command=self.goto_issue).pack(side='right')
        cols=('severity','component','time','duration','measured','limit','detail')
        self.issue_tree=ttk.Treeview(warningpane,columns=cols,show='headings',selectmode='browse')
        for col,heading,width in [('severity','Severity',85),('component','Component',130),('time','First time (s)',115),('duration','Duration (s)',110),('measured','Peak (A)',100),('limit','Limit (A)',100),('detail','Description',400)]:
            self.issue_tree.heading(col,text=heading);self.issue_tree.column(col,width=width,stretch=(col=='detail'))
        self.issue_tree.tag_configure('Error',foreground='#b91c1c')
        self.issue_tree.tag_configure('Warning',foreground='#a16207')
        self.issue_tree.pack(fill='both',expand=True)
        self.issue_tree.bind('<Double-1>',lambda event:self.goto_issue())
        self.issue_count=tk.StringVar(value='No diagnostics yet')
        ttk.Label(warningpane,textvariable=self.issue_count).pack(anchor='w',pady=(8,0))
        self.status=tk.StringVar(value='Ready');ttk.Label(self,textvariable=self.status,anchor='w',padding=7).pack(fill='x')
        self.sync_from_project();self.run()

    def sync_from_project(self):
        self.name.set(self.project['name']);self.duration.set(str(self.project['duration_s']));self.dt.set(str(self.project['dt_s']));self.mission_enabled.set(bool(self.project.get('mission_enabled',False)));self.refresh_phases()
        self.refresh()
        self.diagram.ensure_positions();self.diagram.redraw()
    def capture(self):
        self.project['name']=self.name.get().strip() or 'Untitled';self.project['duration_s']=float(self.duration.get());self.project['dt_s']=float(self.dt.get());self.project['mission_enabled']=self.mission_enabled.get()
    def refresh(self):
        for kind,tree in self.trees.items():
            tree.delete(*tree.get_children())
            for i,obj in enumerate(self.project[kind]):
                values=[obj.get(x[0],'') for x in FIELDS[kind]]
                if kind=='loads':values.extend([obj.get('load_mode','profile'),obj.get('duty_pct',''),obj.get('period_s',''),len(obj.get('profile',[]))])
                tree.insert('', 'end',iid=str(i),values=values)
        self.diagram.ensure_positions();self.diagram.redraw()
    def selection(self,kind):
        sel=self.trees[kind].selection();return int(sel[0]) if sel else None
    def add(self,kind):
        ed=Editor(self,kind)
        if ed.result:
            if any(obj['id'] == ed.result['id'] for group in FIELDS for obj in self.project[group]):
                messagebox.showerror('Duplicate ID',f"ID {ed.result['id']} already exists.");return
            self.project[kind].append(ed.result);self.refresh();self.status.set('Edited; run analysis to update results.')
    def edit(self,kind):
        i=self.selection(kind)
        if i is None:return
        self.edit_index(kind,i)
    def edit_index(self,kind,i):
        old=self.project[kind][i];oldid=old['id']
        ed=Editor(self,kind,old)
        if ed.result:
            new=ed.result;newid=new['id']
            if newid!=oldid:
                if any(obj['id']==newid for group in FIELDS for obj in self.project[group]):
                    messagebox.showerror('Duplicate ID',f'ID {newid} already exists.');return
                for c in self.project['converters']:
                    for field in ('input_bus','output_bus'):
                        if c[field]==oldid:c[field]=newid
                for l in self.project['loads']:
                    if l['bus']==oldid:l['bus']=newid
                if kind=='loads':
                    for phase in self.project.get('mission_phases',[]):
                        if oldid in phase.get('states',{}):phase['states'][newid]=phase['states'].pop(oldid)
                layout=self.project.setdefault('layout',{})
                if oldid in layout:layout[newid]=layout.pop(oldid)
                if self.diagram.selected==oldid:self.diagram.selected=newid
            self.project[kind][i]=new;self.refresh();self.status.set('Edited; run analysis to update results.')
    def delete(self,kind):
        i=self.selection(kind)
        if i is None:return
        if kind=='loads' and len(self.trees['loads'].selection())>1:
            if messagebox.askyesno('Delete loads',f'Delete {len(self.trees["loads"].selection())} selected loads?'):
                for index in sorted([int(v) for v in self.trees['loads'].selection()],reverse=True):
                    obj=self.project['loads'].pop(index);self.project.setdefault('layout',{}).pop(obj['id'],None)
                    for phase in self.project.get('mission_phases',[]):phase.get('states',{}).pop(obj['id'],None)
                self.refresh();self.refresh_phases()
            return
        self.delete_index(kind,i)
    def delete_index(self,kind,i):
        obj=self.project[kind][i]
        if kind=='buses':
            bid=obj['id']
            if any(c['input_bus']==bid or c['output_bus']==bid for c in self.project['converters']) or any(l['bus']==bid for l in self.project['loads']):
                messagebox.showerror('Bus in use','Remove connected converters and loads first.');return
        if messagebox.askyesno('Confirm deletion',f"Delete {obj['name']}?"):
            self.project[kind].pop(i);self.project.setdefault('layout',{}).pop(obj['id'],None);
        if kind=='loads':
            for phase in self.project.get('mission_phases',[]):phase.get('states',{}).pop(obj['id'],None)
        self.refresh();self.refresh_phases()
    def bulk_edit(self):
        indices=[int(x) for x in self.trees['loads'].selection()]
        if not indices:messagebox.showinfo('Bulk edit','Select equipment rows first (Ctrl/Shift-click or Select All).');return
        dialog=BulkEdit(self,indices)
        if dialog.result is None:return
        from engine import validate
        import copy
        trial=copy.deepcopy(self.project)
        for i in indices:trial['loads'][i].update(dialog.result)
        try:validate(trial)
        except Exception as exc:messagebox.showerror('Bulk edit rejected',f'No changes applied.\n{exc}');return
        self.project=trial;self.refresh();self.status.set(f'Bulk updated {len(indices)} loads; rerun the analysis.')
    def mission_toggle(self):
        self.project['mission_enabled']=self.mission_enabled.get();self.status.set('Mission setting changed; run analysis to update.')
    def refresh_phases(self):
        if not hasattr(self,'phase_tree'):return
        self.phase_tree.delete(*self.phase_tree.get_children());start=0.0
        for i,ph in enumerate(self.project.get('mission_phases',[])):
            d=float(ph['duration_s']);self.phase_tree.insert('','end',iid=str(i),values=(ph['name'],f'{d:g}',f'{start:g}',f'{start+d:g}',len(ph.get('states',{}))));start+=d
    def phase_index(self):
        sel=self.phase_tree.selection();return int(sel[0]) if sel else None
    def add_phase(self):
        dialog=MissionPhaseEditor(self)
        if dialog.result:
            self.project.setdefault('mission_phases',[]).append(dialog.result);self.refresh_phases()
    def edit_phase(self):
        i=self.phase_index()
        if i is None:return
        dialog=MissionPhaseEditor(self,self.project['mission_phases'][i])
        if dialog.result:self.project['mission_phases'][i]=dialog.result;self.refresh_phases()
    def delete_phase(self):
        i=self.phase_index()
        if i is not None and messagebox.askyesno('Delete phase','Delete selected mission phase?'):
            self.project['mission_phases'].pop(i);self.refresh_phases()
    def move_phase(self,delta):
        i=self.phase_index();phases=self.project.setdefault('mission_phases',[])
        if i is None or not 0<=i+delta<len(phases):return
        phases[i],phases[i+delta]=phases[i+delta],phases[i]
        self.refresh_phases();self.phase_tree.selection_set(str(i+delta))
    def run(self):
        try:
            self.capture();self.results=simulate(self.project)
            result=self.results;lines=[f"PROJECT: {self.project['name']}  |  {self.project['duration_s']} s  |  dt={self.project['dt_s']} s",'']
            lines+=['Bus                     Voltage    Profile mean A     Peak A     Min/Nom/Max A']
            cases={m:simulate(self.project,m) for m in ('min','nom','max')}
            for bid,b in result['buses'].items():
                x=result['bus_i'][bid]
                lines.append(f"{bid:<22} {b['voltage_v']:>6.2f} V     {x.mean():>9.3f}      {x.max():>7.3f}     "+' / '.join(f"{cases[m]['bus_i'][bid][0]:.3f}" for m in ('min','nom','max')))
            lines+=['',f"Source power: mean {result['source_p'].mean():.2f} W | peak {result['source_p'].max():.2f} W | energy {np.trapezoid(result['source_p'],result['t'])/3600:.4f} Wh",'']
            if result['total_source_i'] is not None:
                ii=result['total_source_i'];lines.append(f"Total source current: mean {ii.mean():.3f} A | peak {ii.max():.3f} A")
            else:lines.append('Multiple independent sources: currents reported individually (not summed across voltages).')
            lines+=['WARNINGS:']+(result['issues'] or ['None'])
            self.summary.config(state='normal');self.summary.delete('1.0','end');self.summary.insert('end','\n'.join(lines));self.summary.config(state='disabled')
            self.update_issues(result)
            self.plot();self.status.set('Analysis complete' + (f" - {len(result['issues'])} warning(s)" if result['issues'] else ' - no limits exceeded'))
            self.tabs.select(resultpane_index(self.tabs, 'Analysis'))
            return result
        except Exception as e:
            self.show_analysis_error(e)
            messagebox.showerror('Analysis error',str(e))
            self.status.set(f'Error: {e}')
            return None
    def update_issues(self, result):
        """Convert solver warnings into actionable, time-localized diagnostics."""
        self.issue_tree.delete(*self.issue_tree.get_children())
        t=result['t']; dt=float(self.project['dt_s']); count=0
        sources=set(result['roots'])
        checks=[]
        for conv in self.project['converters']:
            checks.append(('Converter',conv['id'],result['conv_out'][conv['id']],float(conv['max_output_a'])))
        for bus in self.project['buses']:
            if bus['id'] in sources and float(bus.get('source_limit_a',0))>0:
                checks.append(('Source',bus['id'],result['bus_i'][bus['id']],float(bus['source_limit_a'])))
        for load in self.project['loads']:
            checks.append(('Equipment',load['id'],result['load_i'][load['id']],float(load['max_a'])))
        for category,component,trace,limit in checks:
            over=trace>limit+1e-9
            if not np.any(over):continue
            first=int(np.flatnonzero(over)[0]); peak=float(np.max(trace)); elapsed=float(np.sum(over[:-1]))*dt
            detail=f'{category} {component} exceeds its current limit'
            vals=('Warning',component,f'{t[first]:.3f}',f'{elapsed:.3f}',f'{peak:.3f}',f'{limit:.3f}',detail)
            self.issue_tree.insert('','end',values=vals,tags=('Warning',))
            count+=1
        self.issue_count.set(f'{count} warning(s), 0 error(s)' if count else 'No warnings or errors detected at the sampled times.')
        self.tabs.tab(self.issue_tree.master,text=f'Warnings & Errors ({count})' if count else 'Warnings & Errors')

    def show_analysis_error(self,exc):
        self.issue_tree.delete(*self.issue_tree.get_children())
        self.issue_tree.insert('','end',values=('Error','Project','—','—','—','—',str(exc)),tags=('Error',))
        self.issue_count.set('1 error; analysis did not complete.')
        self.tabs.tab(self.issue_tree.master,text='Warnings & Errors (1)')

    def goto_issue(self):
        selected=self.issue_tree.selection()
        if not selected:return
        row=self.issue_tree.item(selected[0],'values')
        component=row[1]
        if component in ('Project',''):return
        self.tabs.select(self.diagram)
        self.diagram.selected=component
        self.diagram.redraw()

    def plot(self):
        if self.results is None:return
        r=self.results;self.figure.clear();mode=self.plotmode.get()
        def draw(ax,title,series,unit):
            for label,y in series.items(): ax.step(r['t'],y,label=label,where='post',linewidth=1.35)
            ax.set(xlabel='Time (s)',ylabel=unit,title=title)
            ax.grid(True,alpha=.3)
            add_phase_overlay(ax, self.project, float(r['t'][-1]), compact=(mode=='Dashboard'))
            if series:ax.legend(loc='best',fontsize=7,ncol=2)
        sources=r['source_i']
        current=({'Total source current':r['total_source_i']} if r['total_source_i'] is not None else sources)
        datasets={
            'Total Power':('Total source power',{'Total power':r['source_p']},'Power (W)'),
            'Total Source Current':('Source current' if len(sources)>1 else 'Total source current',current,'Current (A)'),
            'Bus Current':('Bus current',r['bus_i'],'Current (A)'),
            'Bus Power':('Bus power (includes converter loads)',r['bus_p'],'Power (W)'),
            'Source Power':('Source power',{'Total source power':r['source_p']},'Power (W)'),
            'Converter Dissipation':('Converter dissipation',r['loss_p'],'Power (W)'),
            'Equipment Current':('Equipment current',r['load_i'],'Current (A)')}
        if mode=='Flight Phase Timeline':
            ax=self.figure.add_subplot(111);add_mission_timeline(ax,self.project,float(r['t'][-1]))
        elif mode=='Dashboard':
            charts=[datasets['Total Power'],datasets['Total Source Current'],datasets['Bus Current'],datasets['Equipment Current']]
            for ax,data in zip(self.figure.subplots(2,2).flat,charts):draw(ax,*data)
        else:
            ax=self.figure.add_subplot(111);draw(ax,*datasets.get(mode,datasets['Total Power']))
        self.figure.tight_layout();self.canvas.draw_idle()
    def new(self):
        self.project={'name':'New Electrical Loads Analysis','duration_s':60,'dt_s':0.1,'buses':[{'id':'BUS28','name':'Primary 28 V','voltage_v':28,'source_limit_a':0}],'converters':[],'loads':[],'mission_phases':[],'mission_enabled':False}
        self.path=None;self.results=None;self.sync_from_project()
    def open(self):
        path=filedialog.askopenfilename(filetypes=[('Project JSON','*.json')])
        if path:
            try:self.project=load_project(path);self.path=path;self.sync_from_project();self.run()
            except Exception as e:messagebox.showerror('Open error',str(e))
    def save(self):
        if not self.path:return self.save_as()
        try:self.capture();save_project(self.project,self.path);self.status.set(f'Saved {self.path}')
        except Exception as e:messagebox.showerror('Save error',str(e))
    def save_as(self):
        path=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('Project JSON','*.json')])
        if path:self.path=path;self.save()
    def export_excel(self):
        try:
            from excel_io import export_excel
            self.capture()
            path=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel Workbook','*.xlsx')])
            if not path:return
            export_excel(self.project,path)
            self.status.set(f'Exported editable Excel project: {path}')
        except Exception as exc:messagebox.showerror('Excel export error',str(exc),parent=self)
    def import_excel(self):
        from excel_io import import_excel
        path=filedialog.askopenfilename(filetypes=[('Excel Workbook','*.xlsx')])
        if not path:return
        try:
            incoming=import_excel(path)  # Validation before touching the open project
        except Exception as exc:
            messagebox.showerror('Excel import rejected',f'Your existing project was not changed.\n\n{exc}',parent=self)
            return
        if not messagebox.askyesno('Import Excel Project',
            f"Replace the current project with '{incoming['name']}' from this workbook?\n\n"
            'This does not overwrite the saved JSON file until you choose Save.',parent=self):return
        self.project=incoming;self.path=None;self.results=None
        self.sync_from_project();self.run()
        self.status.set('Excel project imported. Save As JSON to store the updated project.')
    def export_csv(self):
        r=self.run()
        if r is None:return
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        cols={'time_s':r['t'],'total_source_power_W':r['source_p']}
        if r['total_source_i'] is not None:cols['total_source_current_A']=r['total_source_i']
        cols.update({f'source_{k}_current_A':v for k,v in r['source_i'].items()});cols.update({f'bus_{k}_power_W':v for k,v in r['bus_p'].items()})
        cols.update({f'bus_{k}_A':v for k,v in r['bus_i'].items()});cols.update({f'load_{k}_A':v for k,v in r['load_i'].items()})
        cols.update({f'converter_{k}_input_A':v for k,v in r['conv_in'].items()});cols.update({f'converter_{k}_loss_W':v for k,v in r['loss_p'].items()})
        with open(path,'w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(cols.keys());w.writerows(zip(*cols.values()))
        self.status.set(f'CSV exported to {path}')
    def report(self):
        r=self.run()
        if r is None:return
        path=filedialog.asksaveasfilename(defaultextension='.pdf',filetypes=[('PDF','*.pdf')])
        if not path:return
        try:
            from reporting import create_pdf
            create_pdf(self.project,r,path);self.status.set(f'Report exported to {path}')
            messagebox.showinfo('Report created',str(Path(path).resolve()))
        except Exception as e:messagebox.showerror('Report error',str(e))

if __name__=='__main__':App().mainloop()
