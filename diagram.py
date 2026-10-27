"""Interactive architecture canvas for Electrical Loads Workbench.

Drag blocks to position them; double-click to edit properties. Connections are
inferred from bus assignments and converter input/output assignments.
"""
import tkinter as tk
from tkinter import ttk

COLORS = {'buses': ('#d9eaff', '#1e5792'), 'converters': ('#fff0ca', '#92660d'), 'loads': ('#ddf5e3', '#226c43')}
WIDTH, HEIGHT = 170, 78

class Architecture(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.selected = None
        self.drag_start = None
        header=ttk.Frame(self, padding=7); header.pack(fill='x')
        for label, kind in [('+ Voltage Bus','buses'), ('+ Converter','converters'), ('+ Equipment','loads')]:
            ttk.Button(header,text=label,command=lambda k=kind:self.add(k)).pack(side='left',padx=4)
        ttk.Button(header,text='Edit Selected',command=self.edit_selected).pack(side='left',padx=4)
        ttk.Button(header,text='Delete Selected',command=self.delete_selected).pack(side='left',padx=4)
        ttk.Button(header,text='Auto Layout',command=self.auto_layout).pack(side='left',padx=4)
        ttk.Label(header,text='Drag to move · Double-click to edit · Right-click for actions').pack(side='right')
        outer=ttk.Frame(self);outer.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(outer,background='#f6f8fb',highlightthickness=0,scrollregion=(0,0,1800,1200))
        h=ttk.Scrollbar(outer,orient='horizontal',command=self.canvas.xview)
        v=ttk.Scrollbar(outer,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=h.set,yscrollcommand=v.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');v.grid(row=0,column=1,sticky='ns');h.grid(row=1,column=0,sticky='ew')
        outer.columnconfigure(0,weight=1);outer.rowconfigure(0,weight=1)
        self.canvas.bind('<Button-1>',self.on_press)
        self.canvas.bind('<B1-Motion>',self.on_drag)
        self.canvas.bind('<Double-Button-1>',self.on_double)
        self.canvas.bind('<Button-3>',self.on_context)
        self.canvas.bind('<Delete>',lambda e:self.delete_selected())
        self.canvas.bind('<Configure>',lambda e:self.redraw())

    def objects(self):
        for kind in ('buses','converters','loads'):
            for obj in self.app.project[kind]: yield kind,obj

    def find(self, key):
        return next(((k,o) for k,o in self.objects() if o['id']==key),None)

    def positions(self):
        return self.app.project.setdefault('layout',{})

    def auto_layout(self):
        buses=self.app.project['buses']; convs=self.app.project['converters'];loads=self.app.project['loads']
        parents={c['output_bus']:c['input_bus'] for c in convs}
        depths={}
        def depth(bus):
            if bus in depths:return depths[bus]
            depths[bus]=0 if bus not in parents else depth(parents[bus])+1
            return depths[bus]
        for b in buses:depth(b['id'])
        levels={}
        for b in buses:levels.setdefault(depth(b['id']),[]).append(b)
        pos={}
        for level,bs in levels.items():
            for j,b in enumerate(bs):pos[b['id']]=[65+level*310,80+j*280]
        for c in convs:
            p=pos.get(c['output_bus'],[370,150]);pos[c['id']]=[p[0]-210,p[1]+90]
        offsets={}
        for l in loads:
            bid=l['bus'];idx=offsets.get(bid,0);offsets[bid]=idx+1
            anchor=pos.get(bid,[75,75]);pos[l['id']]=[anchor[0]+20+idx*195,anchor[1]+165]
        self.app.project['layout']=pos
        self.redraw()

    def ensure_positions(self):
        pos=self.positions()
        all_ids={o['id'] for _,o in self.objects()}
        if not pos or not all_ids.issubset(pos):
            old=dict(pos); self.auto_layout()
            self.positions().update({k:v for k,v in old.items() if k in all_ids})

    def redraw(self):
        self.canvas.delete('all')
        pos=self.positions()
        if not pos:self.ensure_positions();return
        c=self.canvas
        for x in range(0,2000,30):c.create_line(x,0,x,1500,fill='#e8edf3')
        for y in range(0,1500,30):c.create_line(0,y,2000,y,fill='#e8edf3')
        for converter in self.app.project['converters']:
            self.line(converter['input_bus'],converter['id'], '#8b98aa')
            self.line(converter['id'],converter['output_bus'], '#8b98aa')
        for load in self.app.project['loads']:self.line(load['bus'],load['id'],'#80a28b')
        for kind,o in self.objects():
            key=o['id'];x,y=pos.get(key,(65,65))
            fill,edge=COLORS[kind]
            if self.selected==key:edge='#d56025'
            tag=f'node:{key}'
            c.create_rectangle(x+3,y+4,x+WIDTH+3,y+HEIGHT+4,fill='#dce2eb',outline='',tags=(tag,))
            c.create_rectangle(x,y,x+WIDTH,y+HEIGHT,fill=fill,outline=edge,width=3 if self.selected==key else 2,tags=(tag,))
            if kind=='buses':
                title=f"{o['voltage_v']:g} V BUS";subtitle=o['name'];detail=key
            elif kind=='converters':
                iv=next((b['voltage_v'] for b in self.app.project['buses'] if b['id']==o['input_bus']), '?')
                ov=next((b['voltage_v'] for b in self.app.project['buses'] if b['id']==o['output_bus']), '?')
                title=f'{iv} → {ov} V';subtitle=o['name'];detail=f"η {100*o['efficiency']:g}%  ·  {o['max_output_a']:g} A max"
            else:
                title=o['name'];subtitle=f"{o['nom_a']:g} A nominal";detail=f"{o['min_a']:g} / {o['nom_a']:g} / {o['max_a']:g} A"
            for yy,txt,sz,bold in [(y+20,title,12,True),(y+42,subtitle,10,False),(y+62,detail,9,False)]:
                c.create_text(x+WIDTH/2,yy,text=txt,font=('Segoe UI',sz,'bold' if bold else 'normal'),fill='#24364a',width=WIDTH-10,tags=(tag,))
        if pos:
            c.configure(scrollregion=(0,0,max(1300,max(p[0] for p in pos.values())+270),max(850,max(p[1] for p in pos.values())+230)))

    def line(self, from_id,to_id,color):
        pos=self.positions()
        if from_id not in pos or to_id not in pos:return
        a,b=pos[from_id],pos[to_id]
        x1,y1=a[0]+WIDTH/2,a[1]+HEIGHT/2
        x2,y2=b[0]+WIDTH/2,b[1]+HEIGHT/2
        self.canvas.create_line(x1,y1,x2,y2,fill=color,width=2.5,arrow=tk.LAST,arrowshape=(9,11,4))

    def hit(self,event):
        x=self.canvas.canvasx(event.x);y=self.canvas.canvasy(event.y)
        items=self.canvas.find_overlapping(x,y,x,y)
        for item in reversed(items):
            for tag in self.canvas.gettags(item):
                if tag.startswith('node:'):return tag[5:]
        return None

    def on_press(self,event):
        self.canvas.focus_set();self.selected=self.hit(event)
        self.drag_start=(self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)) if self.selected else None
        self.redraw()

    def on_drag(self,event):
        if not self.selected or not self.drag_start:return
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        dx,dy=x-self.drag_start[0],y-self.drag_start[1]
        p=self.positions().get(self.selected)
        if p:p[0]=max(0,p[0]+dx);p[1]=max(0,p[1]+dy)
        self.drag_start=(x,y);self.redraw()

    def on_double(self,event):
        key=self.hit(event)
        if key:self.selected=key;self.edit_selected()

    def on_context(self,event):
        self.selected=self.hit(event);self.redraw()
        m=tk.Menu(self,tearoff=0)
        if self.selected:
            m.add_command(label='Edit properties / load profile',command=self.edit_selected)
            m.add_command(label='Delete',command=self.delete_selected)
            m.add_separator()
        for label,kind in [('+ Add voltage bus','buses'),('+ Add converter','converters'),('+ Add equipment','loads')]:
            m.add_command(label=label,command=lambda k=kind:self.add(k))
        m.tk_popup(event.x_root,event.y_root)

    def add(self,kind):
        self.app.add(kind)
        self.ensure_positions();self.redraw()

    def edit_selected(self):
        found=self.find(self.selected)
        if found:
            kind,obj=found
            idx=self.app.project[kind].index(obj)
            self.app.edit_index(kind,idx)

    def delete_selected(self):
        found=self.find(self.selected)
        if found:
            kind,obj=found
            idx=self.app.project[kind].index(obj)
            self.app.delete_index(kind,idx)
            self.selected=None
