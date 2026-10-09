# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
CI-mode helpers shared by `lbuild` and `ltest`.

Standard library only, and nothing here imports colcon, so the pieces can be
unit tested without a ROS workspace.

- `is_ci_mode` decides whether to print the stable, non-interactive log (no
  cursor movement) instead of the live board. It is driven only by ``--ci``
  and the ``CI``/``GITHUB_ACTIONS`` variables, never by a non-TTY stdout, so
  a piped ``colcon lb`` keeps the output of the earlier releases.
- `workflow_command` / `annotation` / `group` build GitHub Actions workflow
  commands with the escaping the runner expects.
- `append_step_summary` / `md_table` write Markdown to `$GITHUB_STEP_SUMMARY`.
- `pick_free_domain_id` / `isolated_test_env` choose an unused ROS_DOMAIN_ID
  for `ltest --isolated-domain`.
- `apply_output_mode` swaps the live board for the CI log in the verb's args.
"""

import contextlib
import os
import random
import socket

_FALSY = ('', '0', 'false', 'no', 'off')

#: DDS (RTPS) port formula: PB + DG * domainId + offset, with PB=7400, DG=250
DDS_PORT_BASE = 7400
DDS_DOMAIN_GAIN = 250
#: offsets d0..d3 of participant 0: discovery multicast/unicast, user
#: multicast/unicast. Probing these tells whether a domain is in use here.
DDS_PORT_OFFSETS = (0, 1, 10, 11)
#: ROS 2 accepts ROS_DOMAIN_ID values 0..232
ROS_DOMAIN_ID_MAX = 232
#: candidates for --isolated-domain. Domain 0 is the default domain (what the
#: isolation is meant to avoid), and above 101 the DDS ports reach the Linux
#: ephemeral port range (32768-60999), where a clash would fail at random.
ISOLATED_DOMAIN_IDS = tuple(range(1, 102))


def _flag_set(value):
    return (value or '').strip().lower() not in _FALSY


def is_github_actions(environ=None):
    """True when running under GitHub Actions (``GITHUB_ACTIONS`` is set)."""
    env = os.environ if environ is None else environ
    return _flag_set(env.get('GITHUB_ACTIONS'))


def is_ci_mode(*, forced=False, environ=None):
    """
    Decide whether to use the CI log instead of the live terminal board.

    CI mode is on when `forced` (``--ci``) is set, or when the ``CI`` or
    ``GITHUB_ACTIONS`` environment variable is set to something other than
    0/false/no/off. A non-TTY stdout alone does not turn it on.
    """
    if forced:
        return True
    env = os.environ if environ is None else environ
    return any(_flag_set(env.get(name)) for name in ('CI', 'GITHUB_ACTIONS'))


def registered_handler_names():
    """
    Names of the event handlers colcon can actually load, or None if unknown.

    colcon raises a bare KeyError when `--event-handlers` names a handler that
    is not registered, so the verbs must never enable one that is missing
    (for example when another installation shadows this package's entry
    points).
    """
    try:
        from colcon_core.event_handler import get_event_handler_extensions
        return set(get_event_handler_extensions(context=None))
    except Exception:  # noqa: BLE001 -- discovery problems must not break the verb
        return None


def apply_output_mode(args, *, live, ci_handler, environ=None, registered=None):
    """
    Choose the live board or the CI log for this run.

    Rewrites ``args.event_handlers`` in place: in CI mode the `live` handler
    is removed and `ci_handler` is enabled. Explicit ``-``/``+`` tokens for
    other handlers are kept. Returns True when CI mode is in effect.

    If `ci_handler` is not registered, the live board is kept instead, so
    the run never fails on an unknown handler name.
    `environ` defaults to the process environment; `registered` defaults to
    `registered_handler_names()`.
    """
    ci_on = is_ci_mode(
        forced=bool(getattr(args, 'ci', False)), environ=environ)
    if not ci_on:
        return False
    if registered is None:
        registered = registered_handler_names()
    if registered is not None and ci_handler not in registered:
        return False
    handlers = [
        token for token in (args.event_handlers or [])
        if token[:-1] != live]
    handlers.append(ci_handler + '+')
    args.event_handlers = handlers
    return True


# ----------------------------------------------------------------------
# GitHub Actions workflow commands
# ----------------------------------------------------------------------

def _escape_data(text):
    return text.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def _escape_property(text):
    return _escape_data(text).replace(':', '%3A').replace(',', '%2C')


def workflow_command(command, message='', **properties):
    """Build ``::command key=value,...::message`` with runner escaping."""
    params = [
        '{0}={1}'.format(key, _escape_property(str(value)))
        for key, value in properties.items() if value not in (None, '')]
    head = '::' + command
    if params:
        head += ' ' + ','.join(params)
    return head + '::' + _escape_data(str(message))


def annotation(level, message, *, file=None, line=None, title=None):
    """An ``::error``/``::warning`` annotation, optionally tied to a file/line."""
    return workflow_command(
        level, message, file=file,
        line=None if line in (None, '') else str(line), title=title)


def group(title):
    """Open a collapsible log group (``::group::``)."""
    return workflow_command('group', title)


def endgroup():
    """Close the innermost log group (``::endgroup::``)."""
    return '::endgroup::'


def annotation_path(path, environ=None):
    """
    Make an absolute path relative to ``$GITHUB_WORKSPACE`` if possible.

    Annotations are matched to files in the checkout by repository-relative
    path, so a workspace-absolute path would not link to the file.
    """
    env = os.environ if environ is None else environ
    workspace = (env.get('GITHUB_WORKSPACE') or '').rstrip(os.sep)
    if workspace and path and path.startswith(workspace + os.sep):
        return path[len(workspace) + 1:]
    return path


# ----------------------------------------------------------------------
# Step summary
# ----------------------------------------------------------------------

def append_step_summary(markdown, environ=None):
    """Append Markdown to ``$GITHUB_STEP_SUMMARY``. False if it is not set."""
    env = os.environ if environ is None else environ
    path = (env.get('GITHUB_STEP_SUMMARY') or '').strip()
    if not path:
        return False
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(markdown.rstrip('\n') + '\n\n')
    return True


def md_table(headers, rows):
    """A GitHub-flavoured Markdown table; pipes and newlines are escaped."""
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')

    lines = [
        '| ' + ' | '.join(cell(h) for h in headers) + ' |',
        '|' + '|'.join('---' for _ in headers) + '|',
    ]
    for row in rows:
        lines.append('| ' + ' | '.join(cell(c) for c in row) + ' |')
    return '\n'.join(lines)


# ----------------------------------------------------------------------
# Isolated ROS_DOMAIN_ID
# ----------------------------------------------------------------------

def domain_ports(domain_id):
    """The four UDP ports DDS uses for `domain_id` (participant 0)."""
    base = DDS_PORT_BASE + DDS_DOMAIN_GAIN * domain_id
    return [base + offset for offset in DDS_PORT_OFFSETS]


def _udp_port_free(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('', port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def domain_is_free(domain_id, *, port_free=_udp_port_free):
    """True when none of the domain's DDS ports is already bound here."""
    return all(port_free(port) for port in domain_ports(domain_id))


def pick_free_domain_id(*, rng=None, is_free=None, exclude=()):
    """
    Return a random ROS_DOMAIN_ID from `ISOLATED_DOMAIN_IDS` whose DDS ports
    are unbound, skipping any in `exclude`.

    This is a heuristic: it sees other DDS participants on this host (and
    anything else holding those UDP ports), not ones on other machines.
    Raises RuntimeError when no candidate is free.
    """
    rng = rng or random.Random()
    if is_free is None:
        def is_free(domain_id):
            return domain_is_free(domain_id)
    order = [d for d in ISOLATED_DOMAIN_IDS if d not in set(exclude)]
    rng.shuffle(order)
    for domain_id in order:
        if is_free(domain_id):
            return domain_id
    raise RuntimeError('no free ROS_DOMAIN_ID in {0}..{1} found'.format(
        ISOLATED_DOMAIN_IDS[0], ISOLATED_DOMAIN_IDS[-1]))


def isolated_test_env(domain_id):
    """Environment that keeps a test run's DDS traffic on loopback."""
    return {
        'ROS_DOMAIN_ID': str(domain_id),
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST',
    }


@contextlib.contextmanager
def scoped_environ(updates):
    """Set environment variables for the duration of a block, then restore."""
    saved = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
