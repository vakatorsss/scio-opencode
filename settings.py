"""User-visible SCIO CODE settings; unsupported provider knobs are not invented."""
import scio_console as scio

DEFAULTS = {'auto_allow': False, 'thinking': 'default', 'max_steps': 20,
            'max_agents': 8, 'max_depth': 3, 'max_children': 32,
            'locale': 'en', 'instructions': '', 'web_search': 'off',
            'tone': 'balanced', 'conciseness': 'balanced'}

PERSONA_SETTINGS = ('thinking', 'locale', 'instructions', 'web_search', 'tone', 'conciseness')
CHOICES = {'thinking': ('default', 'low', 'high'), 'locale': ('en', 'cs'),
           'web_search': ('off', 'auto', 'on'), 'tone': ('balanced', 'direct'),
           'conciseness': ('balanced', 'short', 'detailed')}


def persona_options(values):
    return {k: validate(k, values.get(k, DEFAULTS[k])) for k in PERSONA_SETTINGS}


def add_arguments(parser):
    for name in PERSONA_SETTINGS:
        if name == 'thinking': continue  # Existing launchers already expose it.
        parser.add_argument('--' + name.replace('_', '-'), choices=CHOICES.get(name), default=None,
                            help='Private-agent preference; style fields are experimental' if name in ('tone', 'conciseness') else None)
    parser.add_argument('--instructions-file', help='Load UTF-8 private-agent instructions from a file')


def arguments_options(args):
    values = load()
    for name in DEFAULTS:
        value = getattr(args, name, None)
        if value is not None: values[name] = validate(name, value)
    if getattr(args, 'instructions_file', None):
        from pathlib import Path
        values['instructions'] = validate('instructions', Path(args.instructions_file).read_text(encoding='utf-8-sig'))
    return values


def load():
    saved = scio.read_json(scio.DATA_DIR / 'settings.json', {})
    return {**DEFAULTS, **{k: validate(k, v) for k, v in saved.items() if k in DEFAULTS}}


def validate(name, value):
    if name in CHOICES:
        if value not in CHOICES[name]: raise ValueError(name + ': ' + ', '.join(CHOICES[name]))
        return value
    if name == 'instructions':
        if not isinstance(value, str) or len(value) > 20000:
            raise ValueError('instructions: text up to 20000 characters')
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
            'locale': 'en/cs sent when opening chats and on subsequent messages.',
            'instructions': 'Appended to the private persona system prompt. Model-followed, not a hard constraint.',
            'web_search': 'off disables the web-search skill; auto makes it available; on keeps it always on. Server-side search does not use local executor approvals. Skill configuration is not a security boundary.',
            'experimental_style': 'tone and conciseness are validated saved preferences; behavioral effect is unconfirmed.',
            'limits': 'max_steps and agent limits are local harness limits, not model inference settings.'}
