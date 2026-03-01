"""GTT domain-specific hints for the THAC0 verbosity system.

Hints are contextual tips shown after commands complete. They fire
based on context ('result', 'error', 'verbose') and the THAC0
threshold. Each hint shows at most once per session.

Import this module to register all GTT hints with the global registry.
"""

from ghtraf.lib.log_lib import Hint, register_hints


# Register all GTT hints at import time
register_hints(
    Hint(
        id='setup.dry_run',
        message='  Tip: Use --dry-run to preview all changes before applying.',
        context={'result'},
        min_level=0,
        category='setup',
    ),
    Hint(
        id='setup.configure',
        message='  Tip: Re-run with --configure to update dashboard files.',
        context={'result'},
        min_level=0,
        category='setup',
    ),
    Hint(
        id='api.rate_limit',
        message=('  Note: GitHub API rate limit is 60/hr unauthenticated, '
                 '5,000/hr with token.'),
        context={'verbose'},
        min_level=1,
        category='api',
    ),
    Hint(
        id='config.remember',
        message=('  Tip: ghtraf remembers your settings in .ghtraf.json '
                 '— future commands need zero flags.'),
        context={'result'},
        min_level=0,
        category='config',
    ),
    Hint(
        id='setup.pat',
        message=('  Note: The workflow needs a separate PAT with gist scope '
                 '(different from your gh CLI token).'),
        context={'verbose'},
        min_level=1,
        category='setup',
    ),
)
