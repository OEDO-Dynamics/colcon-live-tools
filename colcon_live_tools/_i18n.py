# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""Tiny, dependency-free UI language detection shared by this package's verbs."""

import os

#: languages this package ships help text in; anything else falls back to
#: English
SUPPORTED_LANGUAGES = ('ja', 'pt', 'en')


def detect_language():
    """
    Guess a UI language ('ja', 'pt' for Brazilian Portuguese, or 'en') from
    the environment.

    Only ever affects the help text *this package's* own verbs add
    themselves (their one-line descriptions and the arguments they add or
    override); `colcon build`'s own argument descriptions are unaffected --
    translating those would mean patching `colcon-core` itself, which is
    out of scope here.
    """
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        value = os.environ.get(var, '')
        if not value:
            continue
        # $LANGUAGE may be a colon-separated preference list, e.g. 'ja:en'
        token = value.split(':')[0]
        lang = token.split('_')[0].split('.')[0].lower()
        if lang in SUPPORTED_LANGUAGES:
            return lang
    return 'en'
