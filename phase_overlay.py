"""Shared, non-intrusive mission phase shading for GUI and PDF time-series plots."""
from matplotlib.transforms import blended_transform_factory


def add_phase_overlay(ax, project, duration_s, compact=False):
    """Shade mission intervals and label phases along the top edge of the axis.

    Intervals are clipped to the visible analysis duration. The last phase may
    end before the simulation does; unassigned time stays unshaded.
    """
    if not project.get('mission_enabled', False):
        return
    phases = project.get('mission_phases', [])
    if not phases:
        return
    start = 0.0
    colors = ('#a8c5e6', '#b6dfca', '#f0d9a3', '#d8c6e9')
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    for index, phase in enumerate(phases):
        stop = start + float(phase['duration_s'])
        left, right = max(0., start), min(float(duration_s), stop)
        if right > left:
            ax.axvspan(left, right, color=colors[index % len(colors)], alpha=0.19, zorder=0)
            ax.axvline(left, color='#64748b', alpha=0.45, linewidth=0.65, zorder=1)
            # Avoid unreadable labels in narrow phases. Full names appear in
            # the dedicated mission timeline, independent of plot zoom.
            width = right - left
            if width >= float(duration_s) * (0.055 if compact else 0.035):
                name = str(phase['name'])
                max_chars = max(3, int(width / max(float(duration_s), 1e-6) * (55 if compact else 85)))
                if len(name) > max_chars:
                    name = name[:max_chars - 1] + '…'
                ax.text((left + right)/2, 0.985, name, transform=trans,
                        ha='center', va='top', fontsize=6 if compact else 7,
                        color='#334155', clip_on=True, zorder=4,
                        bbox={'facecolor':'white', 'edgecolor':'none', 'alpha':0.65, 'pad':0.7})
        start = stop
        if start >= duration_s:
            break
    if 0 < start <= duration_s:
        ax.axvline(start, color='#64748b', alpha=0.45, linewidth=0.65, zorder=1)


def add_mission_timeline(ax, project, duration_s):
    """Dedicated phase timeline, suitable for a standalone plot or PDF page."""
    from matplotlib.patches import Rectangle
    ax.set_xlim(0, duration_s)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel('Time (s)')
    ax.set_title('Flight phase timeline')
    colors = ('#a8c5e6', '#b6dfca', '#f0d9a3', '#d8c6e9')
    start = 0.
    for i, phase in enumerate(project.get('mission_phases', []) if project.get('mission_enabled') else []):
        stop = start + float(phase['duration_s'])
        right = min(stop, duration_s)
        if right > start:
            ax.add_patch(Rectangle((start, .15), right-start, .7,
                                   facecolor=colors[i % len(colors)], edgecolor='#7d8793'))
            ax.text((start+right)/2, .5, str(phase['name']),
                    rotation=90 if right-start < duration_s*.07 else 0,
                    ha='center',va='center', fontsize=7, clip_on=True)
        start = stop
        if start >= duration_s: break
    ax.grid(axis='x', alpha=.2)
