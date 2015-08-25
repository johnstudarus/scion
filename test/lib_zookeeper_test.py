# Copyright 2015 ETH Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
:mod:`lib_zookeeper_test` --- lib.zookeeper unit tests
======================================================
"""
# Stdlib
import logging
from unittest.mock import MagicMock, call, patch

# External packages
import nose
import nose.tools as ntools
from kazoo.client import KazooState
from kazoo.exceptions import (
    ConnectionLoss,
    LockTimeout,
    NoNodeError,
    NodeExistsError,
    SessionExpiredError,
)
from kazoo.handlers.threading import KazooTimeoutError

# SCION
from lib.thread import thread_safety_net
from lib.zookeeper import (
    ZkConnectionLoss,
    ZkNoNodeError,
    ZkParty,
    ZkRetryLimit,
    ZkSharedCache,
    Zookeeper,
)
from test.testcommon import SCIONTestError, create_mock


class BaseZookeeper(object):
    """
    Base class for lib.zookeeper.Zookeeper unit tests
    """
    default_args = [1, 2, "srvtype", "srvid"]
    default_hosts = ["host1:9521", "host2:339"]

    def _init_basic_setup(self, **kwargs):
        all_args = self.default_args + [self.default_hosts]
        return Zookeeper(*all_args, **kwargs)


class TestZookeeperInit(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.__init__
    """
    @patch("lib.zookeeper.Zookeeper._kazoo_start", autospec=True)
    @patch("lib.zookeeper.Zookeeper._setup_state_listener", autospec=True)
    @patch("lib.zookeeper.Zookeeper._kazoo_setup", autospec=True)
    @patch("lib.zookeeper.queue.Queue", autospec=True)
    @patch("lib.zookeeper.threading.Event", autospec=True)
    def test_full(self, event, queue, ksetup, listener, kstart):
        # Setup and call
        event.side_effect = ["event0", "event1"]
        inst = self._init_basic_setup(
            timeout=4.5, on_connect="on_conn", on_disconnect="on_dis")
        # Tests
        ntools.eq_(inst._isd_id, 1)
        ntools.eq_(inst._ad_id, 2)
        ntools.eq_(inst._srv_id, "srvid")
        ntools.eq_(inst._timeout, 4.5)
        ntools.eq_(inst._on_connect, "on_conn")
        ntools.eq_(inst._on_disconnect, "on_dis")
        ntools.eq_(inst.prefix, "/ISD1-AD2/srvtype")
        ntools.eq_(inst._connected, "event0")
        ntools.eq_(inst._lock, "event1")
        queue.assert_called_once_with()
        ntools.eq_(inst._state_events, queue.return_value)
        ntools.eq_(inst.conn_epoch, 0)
        ntools.eq_(inst._parties, {})
        ntools.eq_(inst._zk_lock, None)
        ksetup.assert_called_once_with(inst, self.default_hosts)
        listener.assert_called_once_with(inst)
        kstart.assert_called_once_with(inst)

    @patch("lib.zookeeper.Zookeeper._kazoo_start", autospec=True)
    @patch("lib.zookeeper.Zookeeper._setup_state_listener", autospec=True)
    @patch("lib.zookeeper.Zookeeper._kazoo_setup", autospec=True)
    @patch("lib.zookeeper.threading.Semaphore", autospec=True)
    @patch("lib.zookeeper.threading.Event", autospec=True)
    def test_defaults(self, event, semaphore, ksetup, listener, kstart):
        # Setup and call
        inst = self._init_basic_setup()
        # Tests
        ntools.eq_(inst._timeout, 1.0)
        ntools.eq_(inst._on_connect, None)
        ntools.eq_(inst._on_disconnect, None)


class TestZookeeperKazooSetup(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._kazoo_setup
    """
    @patch("lib.zookeeper.KazooClient", autospec=True)
    @patch("lib.zookeeper.logging.getLogger", autospec=True)
    @patch("lib.zookeeper.KazooRetry", autospec=True)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test(self, init, kretry, getlogger, kclient):
        # Setup
        inst = self._init_basic_setup()
        inst._timeout = 7.9
        logger = create_mock(["setLevel"])
        getlogger.return_value = logger
        # Call
        inst._kazoo_setup(["host0", "host1"])
        # Tests
        kretry.assert_called_once_with(max_tries=-1, max_delay=1)
        getlogger.assert_called_once_with("KazooClient")
        logger.setLevel.assert_called_once_with(logging.ERROR)
        kclient.assert_called_once_with(
            hosts="host0,host1", timeout=7.9,
            connection_retry=kretry.return_value, logger=getlogger.return_value)
        ntools.eq_(inst.kazoo, kclient.return_value)


class TestZookeeperKazooStart(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._kazoo_start
    """
    @patch("lib.zookeeper.logging", autospec=True)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test(self, init, logging_):
        # Setup
        inst = self._init_basic_setup()
        inst.kazoo = create_mock(["start"])
        # Call
        inst._kazoo_start()
        # Tests
        inst.kazoo.start.assert_called_once_with()

    @patch("lib.zookeeper.kill_self", autospec=True)
    @patch("lib.zookeeper.logging", autospec=True)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_timeout(self, init, logging_, kill_self):
        # Setup
        inst = self._init_basic_setup()
        inst.kazoo = create_mock(["start"])
        inst.kazoo.start.side_effect = KazooTimeoutError
        # Call
        inst._kazoo_start()
        # Tests
        kill_self.assert_called_once_with()


class TestZookeeperSetupStateListener(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._setup_state_listener
    """
    @patch("lib.zookeeper.threading.Thread", autospec=True)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test(self, init, thread):
        # Setup
        inst = self._init_basic_setup()
        thread.return_value = create_mock(["start"])
        inst.kazoo = create_mock(["add_listener"])
        # Call
        inst._setup_state_listener()
        # Tests
        thread.assert_called_once_with(target=thread_safety_net,
                                       args=(inst._state_handler,),
                                       name="libZK._state_handler", daemon=True)
        thread.return_value.start.assert_called_once_with()
        inst.kazoo.add_listener(inst._state_listener)


class TestZookeeperStateListener(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._state_listener
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test(self, init):
        # Setup
        inst = self._init_basic_setup()
        inst._state_events = create_mock(["put"])
        inst.conn_epoch = 47
        # Call
        ntools.eq_(inst._state_listener("statist"), False)
        # Tests
        inst._state_events.put.assert_called_once_with("statist")
        ntools.eq_(inst.conn_epoch, 48)


class TestZookeeperStateHandler(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._state_handler
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_flapping(self, init):
        # Setup
        inst = self._init_basic_setup()
        inst._state_events = create_mock(["get", "empty"])
        # Setup inst._state_events.get to allow a single iteration of the loop
        inst._state_events.get.side_effect = [KazooState.CONNECTED]
        inst._state_events.empty.return_value = False
        inst._state_connected = create_mock()
        # Call
        ntools.assert_raises(StopIteration, inst._state_handler)
        # Tests
        inst._state_events.get.assert_has_calls([call()] * 2)
        ntools.assert_false(inst._state_connected.called)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check(self, old_state, new_state, init):
        # Setup
        inst = self._init_basic_setup()
        inst._state_events = create_mock(["get", "empty"])
        # Setup inst._state_events.get to allow a single iteration of the loop
        inst._state_events.get.side_effect = [new_state]
        inst._state_connected = create_mock()
        inst._state_suspended = create_mock()
        inst._state_lost = create_mock()
        # Call
        ntools.assert_raises(StopIteration, inst._state_handler,
                             initial_state=old_state)
        # Tests
        connected = suspended = lost = 0
        if old_state == new_state:
            # In this case none of the state change handlers should be called
            pass
        elif new_state == KazooState.CONNECTED:
            connected = 1
        elif new_state == KazooState.SUSPENDED:
            suspended = 1
        elif new_state == KazooState.LOST:
            lost = 1
        else:
            raise SCIONTestError("Invalid new state")
        ntools.eq_(inst._state_connected.call_count, connected)
        ntools.eq_(inst._state_suspended.call_count, suspended)
        ntools.eq_(inst._state_lost.call_count, lost)

    def test_basic(self):
        test_inputs = (
            ("startup", KazooState.CONNECTED),
            (KazooState.CONNECTED, KazooState.CONNECTED),
            (KazooState.CONNECTED, KazooState.SUSPENDED),
            (KazooState.CONNECTED, KazooState.LOST),
            (KazooState.SUSPENDED, KazooState.CONNECTED),
            (KazooState.SUSPENDED, KazooState.LOST),
            (KazooState.LOST, KazooState.CONNECTED),
        )
        for old_state, new_state, in test_inputs:
            yield self._check, old_state, new_state


class TestZookeeperStateConnected(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._state_connected
    """
    def _setup(self):
        inst = self._init_basic_setup()
        inst.kazoo = MagicMock(spec_set=["client_id"])
        inst.kazoo.client_id = MagicMock(spec_set=["__getitem__"])
        inst.ensure_path = create_mock()
        inst.prefix = "/prefix"
        inst._parties = {
            "/patha": create_mock(["autojoin"]),
            "/pathb": create_mock(["autojoin"]),
        }
        inst._connected = create_mock(["set"])
        inst._on_connect = None
        return inst

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_basic(self, init):
        inst = self._setup()
        # Call
        inst._state_connected()
        # Tests
        inst.ensure_path.assert_called_once_with(inst.prefix, abs=True)
        inst._parties["/patha"].autojoin.assert_called_once_with()
        inst._parties["/pathb"].autojoin.assert_called_once_with()
        inst._connected.set.assert_called_once_with()

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_connloss(self, init):
        inst = self._setup()
        inst.ensure_path.side_effect = ZkConnectionLoss
        # Call
        inst._state_connected()
        # Tests
        ntools.assert_false(inst._connected.called)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_on_connect(self, init):
        inst = self._setup()
        inst._on_connect = create_mock()
        # Call
        inst._state_connected()
        # Tests
        inst._on_connect.assert_called_once_with()


class TestZookeeperStateDisconnected(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper._state_suspended AND
    lib.zookeeper.Zookeeper._state_lost

    _state_suspended and _state_lost currently have almost identical code, so
    test them both in the same way.
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check(self, f_name, init, test_callback=False):
        inst = self._init_basic_setup()
        inst._connected = create_mock(["clear"])
        inst._on_disconnect = None
        if test_callback:
            inst._on_disconnect = create_mock()
        # Call
        getattr(inst, f_name)()
        # Tests
        inst._connected.clear.assert_called_once_with()
        if test_callback:
            inst._on_disconnect.assert_called_once_with()

    def test(self):
        """
        Test with and without a callback function defined
        """
        for f in "_state_suspended", "_state_lost":
            yield self._check, f, True
            yield self._check, f


class TestZookeeperIsConnected(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.is_connected
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check(self, connected, init):
        inst = self._init_basic_setup()
        inst._connected = create_mock(["is_set"])
        inst._connected.is_set.return_value = connected
        # Call
        ntools.eq_(inst.is_connected(), connected)
        # Tests
        inst._connected.is_set.assert_called_once_with()

    def test(self):
        for connected in True, False:
            yield self._check, connected


class TestZookeeperWaitConnected(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.wait_connected
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_connected(self, init):
        inst = self._init_basic_setup()
        inst.is_connected = create_mock()
        # Call
        inst.wait_connected()
        # Tests
        inst.is_connected.assert_called_once_with()

    @patch("lib.zookeeper.SCIONTime.get_time", new_callable=create_mock)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_no_timeout(self, init, get_time):
        inst = self._init_basic_setup()
        inst.is_connected = create_mock()
        inst.is_connected.return_value = False
        get_time.side_effect = [0, 10, 20]
        inst._connected = create_mock(["wait"])
        inst._connected.wait.side_effect = [False, True]
        # Call
        inst.wait_connected(timeout=None)
        # Tests
        inst._connected.wait.assert_has_calls([call(timeout=10.0)] * 2)
        ntools.eq_(inst._connected.wait.call_count, 2)

    @patch("lib.zookeeper.SCIONTime.get_time", new_callable=create_mock)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_timeout_success(self, init, get_time):
        inst = self._init_basic_setup()
        inst.is_connected = create_mock()
        inst.is_connected.return_value = False
        get_time.side_effect = [0, 10, 20]
        inst._connected = create_mock(["wait"])
        inst._connected.wait.side_effect = [False, True]
        # Call
        inst.wait_connected(timeout=15)
        # Tests
        inst._connected.wait.assert_has_calls([call(timeout=10.0),
                                               call(timeout=5.0)])
        ntools.eq_(inst._connected.wait.call_count, 2)

    @patch("lib.zookeeper.SCIONTime.get_time", new_callable=create_mock)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_timeout_fail(self, init, get_time):
        inst = self._init_basic_setup()
        inst.is_connected = create_mock()
        inst.is_connected.return_value = False
        get_time.side_effect = [0, 10, 20]
        inst._connected = create_mock(["wait"])
        inst._connected.wait.side_effect = [False, False]
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.wait_connected, timeout=15)
        # Tests
        ntools.eq_(inst._connected.wait.call_count, 2)


class TestZookeeperEnsurePath(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.ensure_path
    """
    def _setup(self):
        inst = self._init_basic_setup()
        inst.prefix = "/prefix"
        inst.kazoo = create_mock(["ensure_path"])
        return inst

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_basic(self, init):
        # Setup
        inst = self._setup()
        # Call
        inst.ensure_path("pathness")
        # Tests
        inst.kazoo.ensure_path.assert_called_once_with("/prefix/pathness")

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_abs(self, init):
        # Setup
        inst = self._setup()
        # Call
        inst.ensure_path("/path/to/stuff", abs=True)
        # Tests
        inst.kazoo.ensure_path.assert_called_once_with("/path/to/stuff")

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check_error(self, excp, init):
        # Setup
        inst = self._setup()
        inst.kazoo.ensure_path.side_effect = excp
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.ensure_path, "asdwaf")

    def test_errors(self):
        for excp in ConnectionLoss, SessionExpiredError:
            yield self._check_error, excp


class TestZookeeperPartySetup(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.party_setup
    """
    def _setup(self, connected=True):
        inst = self._init_basic_setup()
        inst.is_connected = create_mock()
        inst.is_connected.return_value = connected
        inst.prefix = "/prefix"
        inst.kazoo = create_mock()
        inst.ensure_path = create_mock()
        inst._srv_id = "srvid"
        inst._parties = {}
        return inst

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_not_connected(self, init):
        inst = self._setup(connected=False)
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.party_setup)
        # Tests
        inst.is_connected.assert_called_once_with()

    @patch("lib.zookeeper.ZkParty", autospec=True)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_basic(self, init, zkparty):
        inst = self._setup()
        # Call
        inst.party_setup()
        # Tests
        inst.ensure_path.assert_called_once_with("/prefix/party", abs=True)
        zkparty.assert_called_once_with(inst.kazoo, "/prefix/party",
                                        inst._srv_id, True)
        ntools.eq_(inst._parties, {"/prefix/party": zkparty.return_value})

    @patch("lib.zookeeper.ZkParty", autospec=True)
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_full(self, init, zkparty):
        inst = self._setup()
        # Call
        inst.party_setup("/pref", False)
        # Tests
        zkparty.assert_called_once_with(inst.kazoo, "/pref/party", inst._srv_id,
                                        False)


class TestZookeeperGetLock(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.get_lock
    """
    def _setup(self, have_lock=False):
        inst = self._init_basic_setup()
        inst._zk_lock = create_mock(["acquire"])
        inst.kazoo = create_mock(["Lock"])
        inst.have_lock = create_mock()
        inst.have_lock.return_value = have_lock
        inst.wait_connected = create_mock()
        inst._lock_epoch = 0
        inst.conn_epoch = 42
        inst._lock = create_mock(["set"])
        return inst

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_full(self, init):
        inst = self._setup()
        inst._zk_lock = None
        inst.prefix = "/prefix"
        inst._srv_id = "srvid"
        lock = create_mock(["acquire"])
        lock.return_value = True
        inst.kazoo.Lock.return_value = lock
        # Call
        ntools.eq_(
            inst.get_lock(lock_timeout="lock t/o", conn_timeout="conn t/o"),
            inst.have_lock.return_value)
        # Tests
        inst.kazoo.Lock.assert_called_once_with("/prefix/lock", "srvid")
        inst.wait_connected.assert_called_once_with(timeout="conn t/o")
        ntools.eq_(inst._lock_epoch, inst.conn_epoch)
        inst._zk_lock.acquire.assert_called_once_with(timeout="lock t/o")
        inst._lock.set.assert_called_once_with()

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_have_lock(self, init):
        inst = self._setup(have_lock=True)
        # Call
        ntools.assert_true(inst.get_lock())
        # Tests
        inst.have_lock.assert_called_once_with()

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_acquire_fail(self, init):
        inst = self._setup()
        inst._zk_lock.acquire.return_value = False
        # Call
        ntools.eq_(inst.get_lock(), inst.have_lock.return_value)
        # Tests
        inst.wait_connected.assert_called_once_with(timeout=None)
        inst._zk_lock.acquire.assert_called_once_with(timeout=None)
        ntools.assert_false(inst._lock.set.called)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check_exception(self, excp, init):
        inst = self._setup()
        inst._zk_lock.acquire.side_effect = excp
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.get_lock)
        # Tests
        inst._zk_lock.acquire.assert_called_once_with(timeout=None)

    def test_exceptions(self):
        for excp in (LockTimeout, ConnectionLoss,
                     SessionExpiredError):
            yield self._check_exception, excp


class TestZookeeperReleaseLock(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.release_lock
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_no_lock(self, init):
        inst = self._init_basic_setup()
        inst._lock = create_mock(["clear"])
        inst._zk_lock = None
        inst.is_connected = create_mock()
        # Call
        inst.release_lock()
        # Tests
        inst._lock.clear.assert_called_once_with()
        ntools.assert_false(inst.is_connected.called)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_not_connected(self, init):
        inst = self._init_basic_setup()
        inst._lock = create_mock(["clear"])
        inst.is_connected = create_mock()
        inst.is_connected.return_value = False
        inst._zk_lock = create_mock(["is_acquired"])
        inst._zk_lock.is_acquired = True
        # Call
        inst.release_lock()
        # Tests
        inst._lock.clear.assert_called_once_with()
        inst.is_connected.assert_called_once_with()
        ntools.assert_false(inst._zk_lock.is_acquired)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_release(self, init):
        inst = self._init_basic_setup()
        inst._lock = create_mock(["clear"])
        inst.is_connected = create_mock()
        inst._zk_lock = create_mock(["is_acquired", "release"])
        # Call
        inst.release_lock()
        # Tests
        inst._zk_lock.release.assert_called_once_with()

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check_exception(self, exception, init):
        inst = self._init_basic_setup()
        inst._lock = create_mock(["clear"])
        inst.is_connected = create_mock()
        inst._zk_lock = create_mock(["is_acquired", "release"])
        inst._zk_lock.release.side_effect = exception
        inst._zk_lock.is_acquired = True
        # Call
        inst.release_lock()
        # Tests
        ntools.assert_false(inst._zk_lock.is_acquired)

    def test_exceptions(self):
        for excp in (NoNodeError, ConnectionLoss,
                     SessionExpiredError):
            yield self._check_exception, excp


class TestZookeeperHaveLock(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.have_lock
    """
    def _setup(self, connected, l_epoch, c_epoch, lock_is_set):
        inst = self._init_basic_setup()
        inst.is_connected = create_mock()
        inst.is_connected.return_value = connected
        inst._lock_epoch = l_epoch
        inst.conn_epoch = c_epoch
        inst._lock = create_mock(["is_set"])
        inst._lock.is_set.return_value = lock_is_set
        inst.release_lock = create_mock()
        return inst

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_have(self, init):
        inst = self._setup(True, 1, 1, True)
        # Call
        ntools.ok_(inst.have_lock())
        # Tests
        inst.is_connected.assert_called_once_with()
        inst._lock.is_set.assert_called_once_with()
        ntools.assert_false(inst.release_lock.called)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def _check_not_have(self, connected, l_epoch, c_epoch, lock_is_set, init):
        inst = self._setup(connected, l_epoch, c_epoch, lock_is_set)
        # Call
        ntools.assert_false(inst.have_lock())
        # Tests
        inst.release_lock.assert_called_once_with()

    def test_not_have(self):
        for connected, l_epoch, c_epoch, lock_is_set in (
                (False, 1, 1, True),
                (True, 0, 1, True),
                (True, 1, 1, False),
        ):
            yield self._check_not_have, connected, l_epoch, c_epoch, lock_is_set


class TestZookeeperWaitLock(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.wait_lock
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test(self, init):
        inst = self._init_basic_setup()
        inst._lock = create_mock(["wait"])
        # Call
        inst.wait_lock()
        # Tests
        inst._lock.wait.assert_called_once_with()


class TestZookeeperRetry(BaseZookeeper):
    """
    Unit tests for lib.zookeeper.Zookeeper.retry
    """
    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_basic(self, init):
        inst = self._init_basic_setup()
        inst.wait_connected = create_mock()
        f = create_mock()
        # Call
        ntools.eq_(inst.retry("desc", f, "arg1", _timeout=5.4, kwarg1="k"),
                   f.return_value)
        # Tests
        inst.wait_connected.assert_called_once_with(timeout=5.4)
        f.assert_called_once_with("arg1", kwarg1="k")

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_no_conn(self, init):
        inst = self._init_basic_setup()
        inst.wait_connected = create_mock()
        inst.wait_connected.side_effect = ZkConnectionLoss
        f = create_mock()
        # Call
        ntools.assert_raises(ZkRetryLimit, inst.retry, "desc", f)
        # Tests
        inst.wait_connected.assert_has_calls([call(timeout=10.0)] * 5)
        ntools.eq_(inst.wait_connected.call_count, 5)
        ntools.assert_false(f.called)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_no_retries(self, init):
        inst = self._init_basic_setup()
        inst.wait_connected = create_mock()
        inst.wait_connected.side_effect = ZkConnectionLoss
        # Call
        ntools.assert_raises(ZkRetryLimit, inst.retry, "desc", "f",
                             _retries=0)
        # Tests
        inst.wait_connected.assert_called_once_with(timeout=10.0)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_inf_retries(self, init):
        inst = self._init_basic_setup()
        inst.wait_connected = create_mock()
        inst.wait_connected.side_effect = [ZkConnectionLoss] * 20
        f = create_mock()
        # Call
        ntools.assert_raises(StopIteration, inst.retry, "desc", f,
                             _retries=None)
        # Tests
        inst.wait_connected.assert_has_calls([call(timeout=10.0)] * 21)
        ntools.eq_(inst.wait_connected.call_count, 21)

    @patch("lib.zookeeper.Zookeeper.__init__", autospec=True, return_value=None)
    def test_conn_drop(self, init):
        inst = self._init_basic_setup()
        inst.wait_connected = create_mock()
        inst.wait_connected.return_value = True
        f = create_mock()
        f.side_effect = [ZkConnectionLoss, "success"]
        # Call
        ntools.eq_(inst.retry("desc", f), "success")
        # Tests
        inst.wait_connected.assert_has_calls([call(timeout=10.0)] * 2)
        ntools.eq_(inst.wait_connected.call_count, 2)


class TestZkPartyInit(object):
    """
    Unit tests for lib.zookeeper.ZkParty.__init__
    """
    @patch("lib.zookeeper.ZkParty.autojoin", autospec=True)
    def test_basic(self, autojoin):
        zk = create_mock(["Party"])
        # Call
        p = ZkParty(zk, "path", "id", "autojoin")
        # Tests
        ntools.eq_(p._autojoin, "autojoin")
        ntools.eq_(p._path, "path")
        zk.Party.assert_called_once_with("path", "id")
        ntools.eq_(p._party, zk.Party.return_value)
        autojoin.assert_called_once_with(p)

    @patch("lib.zookeeper.ZkParty.autojoin", autospec=True)
    def _check_error(self, excp, autojoin):
        zk = create_mock(["Party"])
        zk.Party.side_effect = excp
        # Call
        ntools.assert_raises(ZkConnectionLoss, ZkParty, zk, "path",
                             "id", True)

    def test_error(self):
        for excp in ConnectionLoss, SessionExpiredError:
            yield self._check_error, excp


class TestZkPartyJoin(object):
    """
    Unit tests for lib.zookeeper.ZkParty.join
    """
    @patch("lib.zookeeper.ZkParty.__init__", autospec=True, return_value=None)
    def test_basic(self, init):
        p = ZkParty("zk", "path", "id", "autojoin")
        p._party = create_mock(["join"])
        p.list = create_mock()
        # Call
        p.join()
        # Tests
        p._party.join.assert_called_once_with()

    @patch("lib.zookeeper.ZkParty.__init__", autospec=True, return_value=None)
    def _check_error(self, excp, init):
        p = ZkParty("zk", "path", "id", "autojoin")
        p._party = create_mock(["join"])
        p._party.join.side_effect = excp
        # Call
        ntools.assert_raises(ZkConnectionLoss, p.join)

    def test_error(self):
        for excp in ConnectionLoss, SessionExpiredError:
            yield self._check_error, excp


class TestZkPartyAutoJoin(object):
    """
    Unit tests for lib.zookeeper.ZkParty.autojoin
    """
    @patch("lib.zookeeper.ZkParty.list", autospec=True)
    @patch("lib.zookeeper.ZkParty.__init__", autospec=True, return_value=None)
    def test_auto(self, init, list_):
        p = ZkParty("zk", "path", "id", "autojoin")
        p._autojoin = True
        p.join = create_mock()
        p._path = "path"
        # Call
        p.autojoin()
        # Tests
        p.join.assert_called_once_with()

    @patch("lib.zookeeper.ZkParty.list", autospec=True)
    @patch("lib.zookeeper.ZkParty.__init__", autospec=True, return_value=None)
    def test_noauto(self, init, list_):
        p = ZkParty("zk", "path", "id", "autojoin")
        p._autojoin = False
        p.join = create_mock()
        p._path = "path"
        # Call
        p.autojoin()
        # Tests
        ntools.assert_false(p.join.called)


class TestZkPartyList(object):
    """
    Unit tests for lib.zookeeper.ZkParty.list
    """
    @patch("lib.zookeeper.ZkParty.__init__", autospec=True, return_value=None)
    def test_basic(self, init):
        p = ZkParty("zk", "path", "id", "autojoin")
        p._party = MagicMock(spec_set=["__iter__"])
        p._party.__iter__.return_value = [1, 2, 3]
        # Call
        ntools.eq_(p.list(), {1, 2, 3})

    @patch("lib.zookeeper.ZkParty.__init__", autospec=True, return_value=None)
    def _check_error(self, excp, init):
        p = ZkParty("zk", "path", "id", "autojoin")
        p._party = create_mock(["__iter__"])
        p._party.__iter__.side_effect = excp
        # Call
        ntools.assert_raises(ZkConnectionLoss, p.list)

    def test_error(self):
        for excp in ConnectionLoss, SessionExpiredError:
            yield self._check_error, excp


class TestZkSharedCacheInit(object):
    """
    Unit tests for lib.zookeeper.ZkSharedCache.__init__
    """
    @patch("lib.zookeeper.ExpiringDict", autospec=True)
    def test(self, exp_dict):
        zk = create_mock(["kazoo", "prefix"])
        zk.prefix = "/prefix"
        # Call
        inst = ZkSharedCache(zk, "path", "handler", 22)
        # Tests
        ntools.eq_(inst._zk, zk)
        ntools.eq_(inst._kazoo, zk.kazoo)
        ntools.eq_(inst._path, "/prefix/path")
        ntools.eq_(inst._handler, "handler")
        ntools.eq_(inst._latest_entry, 0)
        ntools.eq_(inst._epoch, 0)
        ntools.eq_(inst._max_age, 22)
        ntools.eq_(inst._epoch, 0)
        exp_dict.assert_called_once_with(max_len=inst.METADATA_CACHE_SIZE,
                                         max_age_seconds=22)
        ntools.eq_(inst._meta, exp_dict.return_value)


class TestZkSharedCacheStore(object):
    """
    Unit tests for lib.zookeeper.ZkSharedCache.store
    """
    def _setup(self):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._zk = create_mock(["is_connected"])
        inst._kazoo = create_mock(["create", "set"])
        return inst

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_not_connected(self, init):
        inst = self._setup()
        inst._zk.is_connected.return_value = False
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.store, 'n', 'v')
        # Tests
        inst._zk.is_connected.assert_called_once_with()

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_set(self, init):
        inst = self._setup()
        # Call
        inst.store('n', 'v')
        # Tests
        inst._kazoo.set.assert_called_once_with("/path/n", "v")
        ntools.assert_false(inst._kazoo.create.called)

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_create(self, init):
        inst = self._setup()
        inst._kazoo.set.side_effect = NoNodeError
        # Call
        inst.store('n', 'v')
        # Tests
        inst._kazoo.create.assert_called_once_with("/path/n", "v",
                                                   makepath=True)

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_suddenly_exists(self, init):
        inst = self._setup()
        inst._kazoo.set.side_effect = NoNodeError
        inst._kazoo.create.side_effect = NodeExistsError
        # Call
        inst.store('n', 'v')


class TestZkSharedCacheProcess(object):
    """
    Unit tests for lib.zookeeper.ZkSharedCache.process
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_not_connected(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._zk = create_mock(["is_connected"])
        inst._zk.is_connected.return_value = False
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.process)
        # Tests
        inst._zk.is_connected.assert_called_once_with()

    def _setup(self):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._zk = create_mock(["conn_epoch", "is_connected"])
        inst._latest_entry = 3112
        inst._epoch = 33
        inst._find_updated = create_mock()
        inst._handle_entries = create_mock()
        inst._path = "/path"
        return inst

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_stale_epoch(self, init):
        inst = self._setup()
        # Call
        inst.process()
        # Tests
        ntools.eq_(inst._latest_entry, 0)
        ntools.eq_(inst._epoch, inst._zk.conn_epoch)
        inst._find_updated.assert_called_once_with()
        inst._handle_entries.assert_called_once_with(
            inst._find_updated.return_value)

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_current_epoch(self, init):
        inst = self._setup()
        inst._epoch = inst._zk.conn_epoch
        # Call
        inst.process()
        # Tests
        ntools.eq_(inst._latest_entry, 3112)
        ntools.eq_(inst._epoch, inst._zk.conn_epoch)


class TestZkSharedCacheGet(object):
    """
    Unit tests for lib.zookeeper.ZkSharedCache._get
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_success(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["get"])
        inst._kazoo.get.return_value = ("data", "meta")
        inst._meta = create_mock(["__setitem__"])
        # Call
        ntools.eq_(inst._get("name"), "data")
        # Tests
        inst._kazoo.get.assert_called_once_with("/path/name")
        inst._meta.__setitem__.assert_called_once_with("name", "meta")

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_no_entry(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["get"])
        inst._kazoo.get.side_effect = NoNodeError
        inst._meta = create_mock(["pop"])
        # Call
        ntools.assert_raises(ZkNoNodeError, inst._get, "name")
        # Tests
        inst._kazoo.get.assert_called_once_with("/path/name")
        inst._meta.pop.assert_called_once_with("name", None)

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def _check_exception(self, excp, expected, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["get"])
        inst._kazoo.get.side_effect = excp
        # Call
        ntools.assert_raises(expected, inst._get, "name")

    def test_exceptions(self):
        for excp, expected in (
            (ConnectionLoss, ZkConnectionLoss),
            (SessionExpiredError, ZkConnectionLoss),
        ):
            yield self._check_exception, excp, expected


class TestZkSharedCacheStat(object):
    """
    Unit tests for lib.zookeeper.ZkSharedCache._stat
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_success(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["exists"])
        inst._kazoo.exists.return_value = "meta"
        inst._meta = create_mock(["__setitem__"])
        # Call
        ntools.eq_(inst._stat("name"), "meta")
        # Tests
        inst._kazoo.exists.assert_called_once_with("/path/name")
        inst._meta.__setitem__.assert_called_once_with("name", "meta")

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_no_node(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["exists"])
        inst._kazoo.exists.return_value = None
        inst._meta = create_mock(["pop"])
        # Call
        ntools.assert_raises(ZkNoNodeError, inst._stat, "name")
        inst._meta.pop.assert_called_once_with("name", None)

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def _check_exception(self, excp, expected, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["exists"])
        inst._kazoo.exists.side_effect = excp
        # Call
        ntools.assert_raises(expected, inst._stat, "name")

    def test_exceptions(self):
        for excp, expected in (
            (ConnectionLoss, ZkConnectionLoss),
            (SessionExpiredError, ZkConnectionLoss),
        ):
            yield self._check_exception, excp, expected


class TestZkSharedCacheListMetadata(object):
    """
    Unit tests for lib.zookeeper.ZkSharedCache._list_metadata
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_sucesss(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["get_children"])
        inst._kazoo.get_children.return_value = [
            "node0", "node1", "node2", "node3"]
        inst._meta = {"node0": "meta0", "node3": "meta3"}
        inst._stat = create_mock()
        inst._stat.side_effect = ["meta1", ZkNoNodeError]
        # Call
        ntools.eq_(inst._list_metadata(), [
            ("node0", "meta0"),
            ("node1", "meta1"),
            ("node3", "meta3"),
        ])
        # Tests
        inst._stat.assert_has_calls([call("node1"), call("node2")])

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_no_cache(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["get_children"])
        inst._kazoo.get_children.side_effect = NoNodeError
        # Call
        ntools.eq_(inst._list_metadata(), [])

    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def _check_children_exception(self, excp, expected, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._path = "/path"
        inst._kazoo = create_mock(["get_children"])
        inst._kazoo.get_children.side_effect = excp
        # Call
        ntools.assert_raises(expected, inst._list_metadata)

    def test_children_exceptions(self):
        for excp, expected in (
            (ConnectionLoss, ZkConnectionLoss),
            (SessionExpiredError, ZkConnectionLoss),
        ):
            yield self._check_children_exception, excp, expected


class TestZkSharedCacheFindUpdated(object):
    """
    Unit test for lib.zookeeper.ZkSharedCache._find_updated
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._list_metadata = create_mock()
        inst._latest_entry = 1
        entries_meta = []
        for i in [1, 6, 4]:
            entry = create_mock(["last_modified"])
            entry.last_modified = i
            entries_meta.append(("data%d" % i, entry))
        inst._list_metadata.return_value = entries_meta
        # Call
        ntools.eq_(inst._find_updated(), ["data6", "data4"])
        # Tests
        ntools.eq_(inst._latest_entry, 6)


class TestZkSharedCacheHandleEntries(object):
    """
    Unit test for lib.zookeeper.ZkSharedCache._handle_entries
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        entry_names = ["entry0", "entry1", "entry2", "entry3"]
        inst._get = create_mock()
        inst._get.side_effect = [
            "data0", ZkNoNodeError, "data2", ZkConnectionLoss
        ]
        inst._path = "/path"
        inst._handler = create_mock()
        # Call
        ntools.eq_(inst._handle_entries(entry_names), 2)
        # Tests
        inst._get.assert_has_calls([call(i) for i in entry_names])
        ntools.eq_(inst._get.call_count, len(entry_names))
        inst._handler.assert_called_once_with(["data0", "data2"])


class TestZkSharedCacheExpire(object):
    """
    Unit test for lib.zookeeper.ZkSharedCache.expire
    """
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_not_connected(self, init):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._zk = create_mock(["is_connected"])
        inst._zk.is_connected.return_value = False
        # Call
        ntools.assert_raises(ZkConnectionLoss, inst.expire, 42)
        # Tests
        inst._zk.is_connected.assert_called_once_with()

    def _setup(self, get_time, entries_meta):
        inst = ZkSharedCache("zk", "path", "handler", "max_age")
        inst._zk = create_mock(["is_connected"])
        get_time.return_value = 1000
        inst._max_age = 0
        inst._list_metadata = create_mock()
        inst._list_metadata.return_value = entries_meta
        inst._kazoo = create_mock(["delete"])
        inst._path = "/path"
        inst._meta = create_mock(["pop"])
        return inst

    @patch("lib.zookeeper.SCIONTime.get_time", new_callable=create_mock)
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def test_success(self, init, get_time):
        entries_meta = []
        for last_mod in 1000, 999, 996, 995, 994, 990, 1001:
            meta = create_mock(["last_modified"])
            meta.last_modified = last_mod
            entries_meta.append(("entry%d" % last_mod, meta))
        inst = self._setup(get_time, entries_meta)
        # Call
        inst.expire(5)
        # Tests
        get_time.assert_called_once_with()
        inst._meta.pop.assert_has_calls([
            call("entry994", None), call("entry990", None)
        ])
        ntools.eq_(inst._meta.pop.call_count, 2)
        inst._kazoo.delete.assert_has_calls([
            call("/path/entry994"), call("/path/entry990")
        ])
        ntools.eq_(inst._kazoo.delete.call_count, 2)

    @patch("lib.zookeeper.SCIONTime.get_time", new_callable=create_mock)
    @patch("lib.zookeeper.ZkSharedCache.__init__", autospec=True,
           return_value=None)
    def _check_exception(self, excp, expected, init, get_time):
        meta = create_mock(["last_modified"])
        meta.last_modified = 1
        inst = self._setup(get_time, [("entry1", meta)])
        inst._kazoo.delete.side_effect = excp
        # Call
        ntools.assert_raises(expected, inst.expire, 5)

    def test_exceptions(self):
        for excp, expected in (
            (NoNodeError, ZkNoNodeError),
            (ConnectionLoss, ZkConnectionLoss),
            (SessionExpiredError, ZkConnectionLoss),
        ):
            yield self._check_exception, excp, expected


if __name__ == "__main__":
    nose.run(defaultTest=__name__)
