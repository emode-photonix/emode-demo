"""Tests of the notebook's setup cell, against mocks (no network, no EMode).

The cell's source is read from EMode_demo.ipynb, so these test what a visitor
runs. Its definitions run in a fresh namespace per test, and the part that
calls them (from `if platform.system()` on) runs with them swapped for fakes.
"""

from __future__ import annotations

import email.message
import hashlib
import io
import json
import types
import urllib.error
import zipfile
from pathlib import Path

import pytest
from emodeconnection import installer
from emodeconnection.types import EModeError, LicenseError

NOTEBOOK = Path(__file__).parent.parent / 'EMode_demo.ipynb'
MAIN = "if platform.system() != 'Linux':"
PASSWORD = 'not-a-real-password-1234'
DEMO = {
    'enabled': True,
    'message': '',
    'email': 'demo@example.com',
    'password': PASSWORD,
    'version': '9.9.9',
    'variant': 'rslab',
    'sha256': '',
    'license_url': 'https://lm.example.com/demo/',
}


def setup_source() -> str:
    cells = json.loads(NOTEBOOK.read_text())['cells']
    return next(''.join(c['source']) for c in cells if 'Set up EMode' in ''.join(c['source']))


@pytest.fixture
def cell(tmp_path, monkeypatch):
    """The setup cell's definitions, with its install marker in tmp_path."""
    definitions, _ = setup_source().split(MAIN)
    namespace: dict = {'__name__': 'setup_cell'}
    exec(definitions, namespace)
    namespace['MARKER'] = tmp_path / 'marker.json'
    return namespace


def run_main(namespace: dict, system: str = 'Linux') -> None:
    _, main = setup_source().split(MAIN)
    namespace['platform'] = types.SimpleNamespace(system=lambda: system)
    exec(MAIN + main, namespace)


def reply(payload: dict):
    """A stand-in for urlopen that answers `payload` as JSON."""

    def urlopen(request, timeout):
        return io.BytesIO(json.dumps(payload).encode())

    return urlopen


def http_error(code: int):
    def urlopen(request, timeout):
        headers = email.message.Message()
        headers['Retry-After'] = '3600'
        raise urllib.error.HTTPError(request.full_url, code, 'error', headers, None)

    return urlopen


def make_zip(path: Path) -> str:
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('emode', b'#!/bin/sh\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_installer(tmp_path, monkeypatch):
    """emodeconnection.installer with the network and the install faked. Returns the call log."""
    calls: list[str] = []
    zip_source = tmp_path / 'source.zip'
    sha256 = make_zip(zip_source)

    def login(email, password):
        calls.append('login')
        return 'token'

    def download_release(token, platform_key, version, filename, dest_dir):
        calls.append(f'download {platform_key} {version} {filename}')
        target = dest_dir / filename
        target.write_bytes(zip_source.read_bytes())
        return target

    def install_linux(zip_path, install_dir, explicit_dir):
        calls.append('install')
        exe = tmp_path / 'bin' / 'emode'
        exe.parent.mkdir(exist_ok=True)
        exe.write_text('fake')
        return exe

    monkeypatch.setattr(installer, 'login', login)
    monkeypatch.setattr(installer, 'download_release', download_release)
    monkeypatch.setattr(installer, 'install_linux', install_linux)
    return types.SimpleNamespace(calls=calls, sha256=sha256)


# --- the credential reply ----------------------------------------------------


def test_paused_stops_with_the_message_and_no_traceback(cell, monkeypatch):
    monkeypatch.setattr(
        cell['urllib'].request,
        'urlopen',
        reply({'enabled': False, 'message': 'The EMode demo opens soon.'}),
    )
    with pytest.raises(cell['DemoPaused']) as stop:
        cell['fetch_credentials']()
    assert str(stop.value) == 'The EMode demo opens soon.'
    # IPython shows _render_traceback_ in place of the traceback.
    assert stop.value._render_traceback_() == ['\033[1mThe EMode demo opens soon.\033[0m']


def test_paused_without_a_message_still_says_why(cell, monkeypatch):
    monkeypatch.setattr(cell['urllib'].request, 'urlopen', reply({'enabled': False}))
    with pytest.raises(cell['DemoPaused'], match='paused'):
        cell['fetch_credentials']()


def test_rate_limited(cell, monkeypatch):
    monkeypatch.setattr(cell['urllib'].request, 'urlopen', http_error(429))
    with pytest.raises(cell['DemoStop'], match='too often') as stop:
        cell['fetch_credentials']()
    assert not isinstance(stop.value, cell['DemoPaused'])


def test_server_error(cell, monkeypatch):
    monkeypatch.setattr(cell['urllib'].request, 'urlopen', http_error(503))
    with pytest.raises(cell['DemoStop'], match='HTTP 503'):
        cell['fetch_credentials']()


def test_unreachable(cell, monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError('Name or service not known')

    monkeypatch.setattr(cell['urllib'].request, 'urlopen', urlopen)
    with pytest.raises(cell['DemoStop'], match='Could not reach'):
        cell['fetch_credentials']()


def test_enabled_reply_is_returned(cell, monkeypatch):
    monkeypatch.setattr(cell['urllib'].request, 'urlopen', reply(DEMO))
    assert cell['fetch_credentials']() == DEMO


# --- installing EMode ----------------------------------------------------------


def test_installs_the_rslab_build_at_the_replys_version(cell, fake_installer):
    demo = {**DEMO, 'sha256': fake_installer.sha256}
    exe = cell['install_emode'](demo)
    assert exe.name == 'emode'
    assert fake_installer.calls == [
        'login',
        'download linux-rslab 9.9.9 EMode-9.9.9-Linux-rslab.zip',
        'install',
    ]


def test_a_wrong_sha256_stops_before_installing(cell, fake_installer):
    demo = {**DEMO, 'sha256': '0' * 64}
    with pytest.raises(cell['DemoStop'], match='SHA-256'):
        cell['install_emode'](demo)
    assert 'install' not in fake_installer.calls
    assert not cell['MARKER'].exists()


def test_a_second_run_skips_the_download(cell, fake_installer):
    demo = {**DEMO, 'sha256': fake_installer.sha256}
    first = cell['install_emode'](demo)
    fake_installer.calls.clear()
    assert cell['install_emode'](demo) == first
    assert fake_installer.calls == []


def test_a_new_version_installs_again(cell, fake_installer):
    cell['install_emode']({**DEMO, 'sha256': fake_installer.sha256})
    fake_installer.calls.clear()
    cell['install_emode']({**DEMO, 'version': '9.9.10', 'sha256': fake_installer.sha256})
    assert 'install' in fake_installer.calls


def test_a_refused_download_login_is_a_credential_error(cell, fake_installer, monkeypatch):
    def login(email, password):
        raise SystemExit(1)  # what installer.login does on a wrong password

    monkeypatch.setattr(installer, 'login', login)
    with pytest.raises(cell['CredentialsRejected']):
        cell['install_emode']({**DEMO, 'sha256': fake_installer.sha256})


def test_a_failed_download_stops(cell, fake_installer, monkeypatch):
    def download_release(*args, **kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(installer, 'download_release', download_release)
    with pytest.raises(cell['DemoStop'], match='download failed'):
        cell['install_emode']({**DEMO, 'sha256': fake_installer.sha256})


# --- logging in ------------------------------------------------------------------


def test_login_passes_the_password_in_the_environment_only(cell, monkeypatch, tmp_path):
    seen = {}

    def run(args, env, **kwargs):
        seen['args'], seen['env'] = args, env
        return types.SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(cell['subprocess'], 'run', run)
    monkeypatch.delenv('EMODE_LICENSE_URL', raising=False)
    cell['log_in'](tmp_path / 'emode', DEMO)
    assert seen['args'][1:] == ['login', '--write']
    assert PASSWORD not in ' '.join(seen['args'])
    assert seen['env']['EMODE_PASSWORD'] == PASSWORD
    assert seen['env']['EMODE_EMAIL'] == DEMO['email']
    import os

    assert os.environ['EMODE_LICENSE_URL'] == DEMO['license_url']
    assert 'EMODE_PASSWORD' not in os.environ


def test_a_failed_login_write_stops(cell, monkeypatch, tmp_path):
    def run(args, env, **kwargs):
        return types.SimpleNamespace(returncode=1, stdout='bad\n', stderr='')

    monkeypatch.setattr(cell['subprocess'], 'run', run)
    with pytest.raises(cell['DemoStop'], match='could not store'):
        cell['log_in'](tmp_path / 'emode', DEMO)


# --- opening the session ---------------------------------------------------------


@pytest.fixture
def started(cell, monkeypatch, tmp_path):
    """`start` with installing and logging in faked. Set `.error` to make EMode() raise it."""
    state = types.SimpleNamespace(error=None)

    class FakeEMode:
        running = True

        def __init__(self):
            if state.error is not None:
                raise state.error

    import emodeconnection

    monkeypatch.setattr(emodeconnection, 'EMode', FakeEMode)
    monkeypatch.setitem(cell, 'install_emode', lambda demo: tmp_path / 'bin' / 'emode')
    monkeypatch.setitem(cell, 'log_in', lambda exe, demo: None)
    monkeypatch.setenv('PATH', '/usr/bin')
    state.FakeEMode = FakeEMode
    return state


def test_start_opens_a_session_with_emode_on_path(cell, started, tmp_path):
    import os

    assert isinstance(cell['start'](DEMO), started.FakeEMode)
    assert os.environ['PATH'].startswith(str(tmp_path / 'bin'))


def test_a_rejected_checkout_is_a_credential_error(cell, started):
    started.error = LicenseError(
        'EMode could not verify the stored user profile. Log in again with `emode login`.', None
    )
    with pytest.raises(cell['CredentialsRejected']):
        cell['start'](DEMO)


def test_a_busy_demo_stops_with_its_message(cell, started):
    started.error = LicenseError('The EMode demo is busy, please try again in a few minutes', None)
    with pytest.raises(cell['DemoStop'], match='busy') as stop:
        cell['start'](DEMO)
    assert not isinstance(stop.value, cell['CredentialsRejected'])


def test_a_failed_launch_stops(cell, started):
    started.error = EModeError('EMode failed to launch.')
    with pytest.raises(cell['DemoStop'], match='failed to launch'):
        cell['start'](DEMO)


# --- the whole cell ----------------------------------------------------------------


@pytest.fixture
def flow(cell, monkeypatch):
    """The cell's top level with fetch, client install and start faked. Returns the call log."""
    log = types.SimpleNamespace(fetches=0, starts=0, failures=[])

    def fetch_credentials():
        log.fetches += 1
        return dict(DEMO)

    def start(demo):
        log.starts += 1
        if log.failures:
            raise log.failures.pop(0)
        return types.SimpleNamespace(running=True, close=lambda: log.__setattr__('closed', True))

    monkeypatch.setitem(cell, 'fetch_credentials', fetch_credentials)
    monkeypatch.setitem(cell, 'install_client', lambda: None)
    monkeypatch.setitem(cell, 'start', start)
    return log


def test_the_cell_opens_a_session(cell, flow, capsys):
    run_main(cell)
    assert cell['em'].running
    assert (flow.fetches, flow.starts) == (1, 1)
    assert 'demo' not in cell  # the reply, with the password, is not left behind
    out = capsys.readouterr().out
    assert 'EMode is ready.' in out
    assert PASSWORD not in out


def test_a_password_change_mid_setup_retries_once_with_fresh_credentials(cell, flow, capsys):
    flow.failures = [cell['CredentialsRejected']('changed')]
    run_main(cell)
    assert (flow.fetches, flow.starts) == (2, 2)
    assert cell['em'].running
    assert PASSWORD not in capsys.readouterr().out


def test_a_second_rejection_stops(cell, flow):
    flow.failures = [cell['CredentialsRejected']('changed'), cell['CredentialsRejected']('again')]
    with pytest.raises(cell['CredentialsRejected'], match='again'):
        run_main(cell)
    assert flow.fetches == 2


def test_other_errors_are_not_retried(cell, flow):
    flow.failures = [cell['DemoStop']('busy')]
    with pytest.raises(cell['DemoStop'], match='busy'):
        run_main(cell)
    assert flow.fetches == 1


def test_running_the_cell_again_closes_the_earlier_session(cell, flow):
    run_main(cell)
    first = cell['em']
    run_main(cell)
    assert getattr(flow, 'closed', False)
    assert cell['em'] is not first


def test_not_on_linux(cell, flow):
    with pytest.raises(cell['DemoStop'], match='runs on Linux'):
        run_main(cell, system='Darwin')
    assert flow.fetches == 0
