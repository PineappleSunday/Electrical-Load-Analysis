"""Structured PDF summary and graphs for the electrical loads workbench."""
from io import BytesIO
import numpy as np
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch
from matplotlib.figure import Figure
from engine import simulate
from phase_overlay import add_phase_overlay, add_mission_timeline


def create_pdf(project,r,path):
    styles=getSampleStyleSheet();doc=SimpleDocTemplate(str(path),pagesize=(612,792),leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=40)
    story=[Paragraph('Electrical Loads Analysis',styles['Title']),Paragraph(project['name'],styles['Heading2']),
           Paragraph(f"Duration: {project['duration_s']} s | Timestep: {project['dt_s']} s | Profile: zero-order hold",styles['Normal']),Spacer(1,14)]
    cases={m:simulate(project,m) for m in ('min','nom','max')}
    story.append(Paragraph('Voltage Bus Power Budget',styles['Heading2']))
    rows=[['Bus / Voltage','Min A','Nom A','Max A','Profile peak A','Profile avg A']]
    for b in project['buses']:
        k=b['id'];x=r['bus_i'][k]
        rows.append([f"{k} / {b['voltage_v']:g} V",*(f"{cases[m]['bus_i'][k][0]:.3f}" for m in ('min','nom','max')),f'{x.max():.3f}',f'{x.mean():.3f}'])
    story.append(_table(rows,[125,70,70,70,95,95]))
    source_energy=np.trapezoid(r['source_p'],r['t'])/3600
    story.extend([Spacer(1,9),Paragraph(f"<b>Total source power:</b> average {r['source_p'].mean():.2f} W; peak {r['source_p'].max():.2f} W; modeled energy {source_energy:.4f} Wh",styles['Normal']),Spacer(1,15)])
    if r['total_source_i'] is not None:
        ii=r['total_source_i'];story.append(Paragraph(f'<b>Total source current:</b> average {ii.mean():.3f} A; peak {ii.max():.3f} A',styles['Normal']))
    else:story.append(Paragraph('Multiple independent sources: current is reported per source, not summed across unequal bus voltages.',styles['Normal']))
    if project.get('mission_enabled',False):
        story.append(Spacer(1,12));story.append(Paragraph('Mission Profile',styles['Heading2']))
        phase_rows=[['Phase','Start s','End s','Equipment overrides']];start=0.0
        for ph in project.get('mission_phases',[]):
            end=start+float(ph['duration_s']);states=', '.join(f'{k}: {v}' for k,v in ph.get('states',{}).items()) or 'Default schedules'
            phase_rows.append([ph['name'][:24],f'{start:g}',f'{end:g}',states[:85]])
            start=end
        story.append(_table(phase_rows,[110,65,65,275]));story.append(Spacer(1,10))
    story.append(Paragraph('Converter Assessment',styles['Heading2']))
    rows=[['Converter','In → Out','Efficiency','Rating A','Peak out A','Peak loss W']]
    for c in project['converters']:
        k=c['id'];rows.append([k,f"{c['input_bus']} → {c['output_bus']}",f"{100*c['efficiency']:.1f}%",f"{c['max_output_a']:.2f}",f"{r['conv_out'][k].max():.3f}",f"{r['loss_p'][k].max():.2f}"])
    if len(rows)>1:story.append(_table(rows,[76,119,75,65,88,82]))
    else:story.append(Paragraph('No converters.',styles['Normal']))
    story.extend([Spacer(1,15),Paragraph('Equipment Loads',styles['Heading2'])])
    rows=[['ID / Name','Bus','Mode','Nom A','Max A','Peak A']]
    for l in project['loads']:
        rows.append([f"{l['id']} {l['name'][:17]}",l['bus'],f"{l.get('load_mode','profile')}" + (f" {l.get('duty_pct',50):g}%" if l.get('load_mode')=='duty' else ''),f"{l['nom_a']:.3f}",f"{l['max_a']:.3f}",f"{r['load_i'][l['id']].max():.3f}"])
    if len(rows)>1:story.append(_table(rows,[155,76,66,66,66,76]))
    else:story.append(Paragraph('No loads.',styles['Normal']))
    story.extend([Spacer(1,15),Paragraph('Limit Checks',styles['Heading2'])])
    for issue in (r['issues'] or ['PASS: No configured ratings exceeded.']):story.append(Paragraph(issue.replace('&','&amp;').replace('<','&lt;'),styles['Normal']))
    plots=[('Total Source Power',{'Total':r['source_p']},'Power (W)'),('Source Currents',r['source_i'],'Current (A)'),('Bus Currents',r['bus_i'],'Current (A)'),('Bus Powers',r['bus_p'],'Power (W)'),('Equipment Currents',r['load_i'],'Current (A)')]
    if r['loss_p']:plots.append(('Converter Dissipation',r['loss_p'],'Power (W)'))
    if project.get('mission_enabled') and project.get('mission_phases'):
        fig=Figure(figsize=(7.4,2.0),dpi=125);ax=fig.add_subplot(111)
        add_mission_timeline(ax,project,float(r['t'][-1]));fig.tight_layout()
        buf=BytesIO();fig.savefig(buf,format='png');buf.seek(0)
        story.extend([Spacer(1,14),Image(buf,width=7.1*inch,height=1.92*inch)])
    for title,series,ylabel in plots:
        fig=Figure(figsize=(7.4,3.0),dpi=125);ax=fig.add_subplot(111)
        for k,y in series.items():ax.step(r['t'],y,where='post',label=k,linewidth=1.4)
        ax.set(xlabel='Time (s)',ylabel=ylabel,title=title);ax.grid(alpha=.25)
        add_phase_overlay(ax,project,float(r['t'][-1]))
        if series:ax.legend(fontsize=8,ncol=2)
        fig.tight_layout();buf=BytesIO();fig.savefig(buf,format='png');buf.seek(0)
        story.extend([Spacer(1,16),Image(buf,width=7.1*inch,height=2.88*inch)])
    story.extend([Spacer(1,12),Paragraph('Model Assumptions and Limitations',styles['Heading2']),
                  Paragraph('Each regulated bus has one upstream converter. Voltages are fixed at their declared values. Converter efficiency is constant and quiescent current is charged to its input bus. Duty-cycle modes use rectangular ON/OFF waveforms with period and phase offset. Duty cycles are sampled at the simulation timestep (short pulses may be missed without a sufficiently small timestep). Dynamic profile entries are piecewise constant and held until the next time entry; before the first entry the nominal load is applied. Min/nom/max static scenarios are evaluated independently from dynamic profiles. No supply voltage droop, converter transient response, inrush, thermal behavior, battery discharge curve, or wiring resistance is modeled. Energy is integrated across the modeled interval. Source limits and converter output current ratings are checked against peak modeled values.',styles['BodyText'])])
    doc.build(story)

def _table(rows,widths):
    t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17324c')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#edf3f7')]),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    return t
