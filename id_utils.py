"""Stable, collision-free default IDs for newly created equipment."""
import re

def next_load_id(project):
    """Return smallest available L<number> across all component types."""
    used = {str(item['id']) for group in ('buses', 'converters', 'loads')
            for item in project.get(group, [])}
    numbers = [int(m.group(1)) for value in used if (m := re.fullmatch(r'L(\d+)', value))]
    i = max(numbers, default=0) + 1
    while f'L{i}' in used:
        i += 1
    return f'L{i}'
