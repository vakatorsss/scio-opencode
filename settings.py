"""User-visible SCIO CODE settings; unsupported provider knobs are not invented."""
import scio_console as scio

DEFAULTS = {'auto_allow': False, 'thinking': 'default', 'max_steps': 20,
            'max_agents': 8, 'max_depth': 3, 'max_children': 32}


def load():
    saved = scio.read_json(scio.DATA_DIR / 'settings.json', {})
    return {**DEFAULTS, **{k: validate(k, v) for k, v in saved.items() if k in DEFAULTS}}


def validate(name, value):
    if name == 'thinking':
        if value not in ('default', 'low', 'high'):
            raise ValueError('thinking: default, low, high')
        return value
    if name == 'auto_allow':
        if isinstance(value, bool): return value
        if value not in ('on', 'off'): raise ValueError('auto_allow: on or off')
        return value == 'on'
    ranges = {'max_steps': (1, 100), 'max_agents': (1, 32), 'max_depth': (0, 8), 'max_children': (0, 128)}
    if name not in ranges: raise ValueError('Unsupported setting: ' + name)
    number = int(value)
    low, high = ranges[name]
    if not low <= number <= high: raise ValueError(f'{name}: {low}..{high}')
    return number


def save(values):
    scio.save_json(scio.DATA_DIR / 'settings.json', {k: validate(k, v) for k, v in values.items()})


def describe(values):
    return {'settings': values, 'models': scio.MODELS,
            'thinking_scope': 'Scio built-in set_thinking_level: low/high, for each turn; default leaves it to Scio.',
            'speed': 'No verified speed parameter. Select google-weak for the frontend-designated fast model.',
            'not_exposed_in_chat_transport': ['temperature', 'top_p', 'max_output_tokens', 'reasoning_budget', 'service_tier'],
            'limits': 'max_steps and agent limits are local harness limits, not model inference settings.'}
