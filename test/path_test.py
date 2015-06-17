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
:mod:`path_tests` --- SCION path packet tests
=============================================
"""
#Stdlib
import copy
from unittest.mock import patch, MagicMock

# External packages
import nose
import nose.tools as ntools

# SCION
from lib.packet.path import (
    CorePath,
    CrossOverPath,
    EmptyPath,
    PathBase,
    PeerPath,
)
from lib.packet.opaque_field import (
    HopOpaqueField,
    InfoOpaqueField,
)

class BasePath(object):
    def setup(self):
        self.path = PathBase()
        self.core_path = CorePath()
        self.iof = [InfoOpaqueField.from_values(24, True, 45, 18, 3),
                    InfoOpaqueField.from_values(3, False, 9, 65, 5),
                    InfoOpaqueField.from_values(6, False, 29, 51, 3)]

        self.hof = [HopOpaqueField.from_values(120, 8, 5, b'\x01\x02\x03'),
                    HopOpaqueField.from_values(140, 5, 56, b'\x04\x05\x06'),
                    HopOpaqueField.from_values(80, 12, 22, b'\x07\x08\x09'),
                    HopOpaqueField.from_values(12, 98, 3, b'\x0A\x0B\x0C'),
                    HopOpaqueField.from_values(90, 235, 55, b'\x0D\x0E\x0F')]

    def teardown(self):
        del self.path
        del self.core_path
        del self.iof
        del self.hof


class TestPathBaseInit(BasePath):
    """
    Unit tests for lib.packet.path.PathBase.__init__
    """
    def test(self):
        """
        Tests proper member initialization.
        """
        ntools.eq_(self.path.up_segment_info, None)
        ntools.eq_(self.path.up_segment_hops, [])
        ntools.eq_(self.path.down_segment_info, None)
        ntools.eq_(self.path.down_segment_hops, [])
        ntools.assert_false(self.path.parsed)


class TestPathBaseReverse(BasePath):
    """
    Unit tests for lib.packet.path.PathBase.reverse
    """
    def test_with_info(self):
        """
        Tests PathBase.reverse, with up_segment_info and down_segment_info set
        """
        self.path.up_segment_info = self.iof[0]
        self.path.down_segment_info = self.iof[1]
        self.path.up_segment_hops = self.hof[:3]
        self.path.down_segment_hops = self.hof[:]
        iof1_ = copy.copy(self.iof[0])
        iof2_ = copy.copy(self.iof[1])
        self.path.reverse()
        iof1_.up_flag ^= True
        iof2_.up_flag ^= True
        ntools.eq_(self.path.up_segment_info, iof2_)
        ntools.eq_(self.path.down_segment_info, iof1_)
        ntools.eq_(self.path.up_segment_hops, self.hof[::-1])
        ntools.eq_(self.path.down_segment_hops, self.hof[2::-1])

    def test_without_info(self):
        """
        Tests PathBase.reverse, with up_segment_info and down_segment_info unset
        """
        self.path.up_segment_hops = self.hof[:3]
        self.path.down_segment_hops = self.hof[:]
        self.path.reverse()
        ntools.eq_(self.path.up_segment_hops, self.hof[::-1])
        ntools.eq_(self.path.down_segment_hops, self.hof[2::-1])


class TestPathBaseIsLastHop(BasePath):
    """
    Unit tests for lib.packet.path.PathBase.is_last_hop
    """
    def _check(self, idx, truth):
        self.path.up_segment_hops = self.hof[:3]
        self.path.down_segment_hops = self.hof[:]
        ntools.eq_(self.path.is_last_hop(self.hof[idx]), truth)

    def test(self):
        for idx, truth in ((4, True), (3, False), (1, False)):
            yield self._check, idx, truth


class TestPathBaseIsFirstHop(BasePath):
    """
    Unit tests for lib.packet.path.PathBase.is_first_hop
    """
    def _check(self, idx, truth):
        self.path.up_segment_hops = self.hof[:3]
        self.path.down_segment_hops = self.hof[:]
        ntools.eq_(self.path.is_first_hop(self.hof[idx]), truth)

    def test(self):
        for idx, truth in ((0, True), (1, False), (4, False)):
            yield self._check, idx, truth


class TestPathBaseGetFirstHopOf(BasePath):
    """
    Unit tests for lib.packet.path.PathBase.get_first_hop_of
    """
    def test_with_down_hops(self):
        self.path.down_segment_hops = self.hof[2:5]
        ntools.eq_(self.path.get_first_hop_of(), self.hof[2])

    def test_with_up_hops(self):
        self.path.down_segment_hops = self.hof[2:5]
        self.path.up_segment_hops = self.hof[:3]
        ntools.eq_(self.path.get_first_hop_of(), self.hof[0])

    def test_without_hops(self):
        ntools.eq_(self.path.get_first_hop_of(), None)

class TestPathBaseGetOf(BasePath):
    """
    Unit tests for lib.packet.path.PathBase.get_of
    """
    def _check(self, idx):
        self.path.up_segment_info = self.iof[0]
        self.path.down_segment_info = self.iof[1]
        self.path.down_segment_hops = self.hof[2:5]
        self.path.up_segment_hops = self.hof[:3]
        ofs = [self.iof[0]] + self.hof[:3] + [self.iof[1]] + self.hof[2:5] + \
              [None]
        ntools.eq_(self.path.get_of(idx), ofs[idx])

    def test(self):
        for i in range(9):
            yield self._check, i


class TestCorePathInit(BasePath):
    """
    Unit tests for lib.packet.path.CorePath.__init__
    """
    def test_basic(self):
        ntools.eq_(self.core_path.core_segment_info, None)
        ntools.eq_(self.core_path.core_segment_hops, [])

    @patch("lib.packet.path.CorePath.parse")
    def test_raw(self, parse):
        self.core_path = CorePath("data")
        parse.assert_called_once_with("data")


class TestCorePathParse(BasePath):
    """
    Unit tests for lib.packet.path.CorePath.parse
    """
    def test(self):
        raw = b'1\x00\x00\x00-\x00\x12\x03\x00x\x00\x80\x05\x01\x02\x03\x00' \
              b'\x8c\x00P8\x04\x05\x06\x00P\x00\xc0\x16\x07\x08\t\x0c\x00\x00' \
              b'\x00\x1d\x003\x03\x00P\x00\xc0\x16\x07\x08\t\x00\x8c\x00P8' \
              b'\x04\x05\x06\x00x\x00\x80\x05\x01\x02\x03\x06\x00\x00\x00' \
              b'\t\x00A\x05\x00x\x00\x80\x05\x01\x02\x03\x00\x8c\x00P8\x04' \
              b'\x05\x06\x00P\x00\xc0\x16\x07\x08\t\x00\x0c\x06 \x03\n\x0b' \
              b'\x0c\x00Z\x0e\xb07\r\x0e\x0f'
        self.core_path.parse(raw)
        ntools.eq_(self.core_path.up_segment_info, self.iof[0])
        ntools.eq_(self.core_path.down_segment_info, self.iof[1])
        ntools.eq_(self.core_path.core_segment_info, self.iof[2])
        ntools.eq_(self.core_path.up_segment_hops, self.hof[:3])
        ntools.eq_(self.core_path.down_segment_hops, self.hof[:])
        ntools.eq_(self.core_path.core_segment_hops, self.hof[2::-1])
        ntools.assert_true(self.core_path.parsed)


class TestCorePathPack(BasePath):
    """
    Unit tests for lib.packet.path.CorePath.pack
    """
    def test(self):
        self.core_path.up_segment_info = self.iof[0]
        self.core_path.down_segment_info = self.iof[1]
        self.core_path.core_segment_info = self.iof[2]
        self.core_path.up_segment_hops = self.hof[:3]
        self.core_path.down_segment_hops = self.hof[:]
        self.core_path.core_segment_hops = self.hof[2::-1]
        packed = b'1\x00\x00\x00-\x00\x12\x03\x00x\x00\x80\x05\x01\x02\x03' \
                 b'\x00\x8c\x00P8\x04\x05\x06\x00P\x00\xc0\x16\x07\x08\t\x0c' \
                 b'\x00\x00\x00\x1d\x003\x03\x00P\x00\xc0\x16\x07\x08\t\x00' \
                 b'\x8c\x00P8\x04\x05\x06\x00x\x00\x80\x05\x01\x02\x03\x06' \
                 b'\x00\x00\x00\t\x00A\x05\x00x\x00\x80\x05\x01\x02\x03\x00' \
                 b'\x8c\x00P8\x04\x05\x06\x00P\x00\xc0\x16\x07\x08\t\x00\x0c' \
                 b'\x06 \x03\n\x0b\x0c\x00Z\x0e\xb07\r\x0e\x0f'
        ntools.eq_(self.core_path.pack(), packed)


class TestCorePathReverse(BasePath):
    """
    Unit tests for lib.packet.path.CorePath.reverse
    """
    @patch("lib.packet.path.PathBase.reverse")
    def test_with_info(self, reverse):
        iof1_ = copy.copy(self.iof[0])
        self.core_path.core_segment_info = self.iof[0]
        self.core_path.core_segment_hops = MagicMock()
        self.core_path.reverse()
        reverse.assert_called_once_with(self.core_path)
        self.core_path.core_segment_hops.reverse.assert_called_once_with()
        iof1_.up_flag ^= True
        ntools.eq_(self.core_path.core_segment_info, iof1_)

    @patch("lib.packet.path.PathBase.reverse")
    def test_without_info(self, reverse):
        self.core_path.core_segment_hops = MagicMock()
        self.core_path.reverse()
        reverse.assert_called_once_with(self.core_path)
        self.core_path.core_segment_hops.reverse.assert_called_once_with()


class TestCorePathGetOf(BasePath):
    """
    Unit tests for lib.packet.path.CorePath.get_of
    """
    def _check(self, idx):
        self.core_path.up_segment_info = self.iof[0]
        self.core_path.down_segment_info = self.iof[1]
        self.core_path.core_segment_info = self.iof[2]
        self.core_path.up_segment_hops = self.hof[:2]
        self.core_path.down_segment_hops = [self.hof[2], self.hof[4]]
        self.core_path.core_segment_hops = self.hof[1:4]
        ofs = [self.iof[0]] + self.hof[:2] + [self.iof[2]] + self.hof[1:4] \
                            + [self.iof[1], self.hof[2], self.hof[4], None]
        ntools.eq_(self.core_path.get_of(idx), ofs[idx])

    def test(self):
        for i in range(11):
            yield self._check, i


class TestCorePathFromValues(BasePath):
    """
    Unit tests for lib.packet.path.CorePath.from_values
    """
    def test(self):
        up_hops = self.hof[:2]
        core_hops = self.hof[1:4]
        down_hops = [self.hof[2], self.hof[4]]
        self.core_path = CorePath.from_values(self.iof[0], up_hops, self.iof[1],
                                              core_hops, self.iof[2], down_hops)
        ntools.eq_(self.core_path.up_segment_info, self.iof[0])
        ntools.eq_(self.core_path.core_segment_info, self.iof[1])
        ntools.eq_(self.core_path.down_segment_info, self.iof[2])
        ntools.eq_(self.core_path.up_segment_hops, self.hof[:2])
        ntools.eq_(self.core_path.core_segment_hops, self.hof[1:4])
        ntools.eq_(self.core_path.down_segment_hops, [self.hof[2], self.hof[4]])


class TestCrossOverPathInit(object):
    """
    Unit tests for lib.packet.path.CrossOverPath.__init__
    """
    @patch("lib.packet.path.PathBase.__init__")
    def test_basic(self, __init__):
        co_path = CrossOverPath()
        __init__.assert_called_once_with(co_path)
        ntools.eq_(co_path.up_segment_upstream_ad, None)
        ntools.eq_(co_path.down_segment_upstream_ad, None)

    @patch("lib.packet.path.CrossOverPath.parse")
    def test_raw(self, parse):
        co_path = CrossOverPath("data")
        parse.assert_called_once_with("data")


class TestCrossOverPathParse(BasePath):
    """
    Unit tests for lib.packet.path.CrossOverPath.parse
    """
    def test(self):
        pass


class TestCrossOverPathPack(BasePath):
    """
    Unit tests for lib.packet.path.CrossOverPath.pack
    """
    def test(self):
        pass

class TestCrossOverPathReverse(object):
    """
    Unit tests for lib.packet.path.CrossOverPath.reverse
    """
    @patch("lib.packet.path.PathBase.reverse")
    def test(self, reverse):
        co_path = CrossOverPath()
        co_path.up_segment_upstream_ad = 1
        co_path.down_segment_upstream_ad = 2
        co_path.reverse()
        reverse.assert_called_once_with(co_path)
        ntools.eq_(co_path.up_segment_upstream_ad, 2)
        ntools.eq_(co_path.down_segment_upstream_ad, 1)


class TestCrossOverPathGetOf(BasePath):
    """
    Unit tests for lib.packet.path.CrossOverPath.get_of
    """
    def _check(self, idx):
        co_path = CrossOverPath()
        co_path.up_segment_info = 0
        co_path.up_segment_hops = [1, 2, 3]
        co_path.up_segment_upstream_ad = 4
        co_path.down_segment_info = 5
        co_path.down_segment_upstream_ad = 6
        co_path.down_segment_hops = [7, 8, 9]
        ofs = list(range(10))
        ntools.eq_(co_path.get_of(idx), ofs[idx])

    def test(self):
        for i in range(10):
            yield self._check, i


class TestPeerPathInit(object):
    """
    Unit tests for lib.packet.path.PeerPath.__init__
    """
    @patch("lib.packet.path.PathBase.__init__")
    def test_basic(self, __init__):
        peer_path = PeerPath()
        __init__.assert_called_once_with(peer_path)
        ntools.assert_is_none(peer_path.up_segment_peering_link)
        ntools.assert_is_none(peer_path.up_segment_upstream_ad)
        ntools.assert_is_none(peer_path.down_segment_peering_link)
        ntools.assert_is_none(peer_path.down_segment_upstream_ad)

    @patch("lib.packet.path.PeerPath.parse")
    def test_raw(self, parse):
        peer_path = PeerPath('rawstring')
        parse.assert_called_once_with('rawstring')


class TestPeerPathParse(object):
    """
    Unit tests for lib.packet.path.PeerPath.parse
    """
    def test(self):
        pass


class TestPeerPathPack(object):
    """
    Unit tests for lib.packet.path.PeerPath.pack
    """
    def test(self):
        pass


class TestPeerPathReverse(object):
    """
    Unit tests for lib.packet.path.PeerPath.reverse
    """
    @patch("lib.packet.path.PathBase.reverse")
    def test(self, reverse):
        peer_path = PeerPath()
        peer_path.up_segment_upstream_ad = 1
        peer_path.down_segment_upstream_ad = 2
        peer_path.up_segment_peering_link = 3
        peer_path.down_segment_peering_link = 4
        peer_path.reverse()
        reverse.assert_called_once_with(peer_path)
        ntools.eq_(peer_path.up_segment_upstream_ad, 2)
        ntools.eq_(peer_path.down_segment_upstream_ad, 1)
        ntools.eq_(peer_path.up_segment_peering_link, 4)
        ntools.eq_(peer_path.down_segment_peering_link, 3)


class TestPeerPathGetOf(BasePath):
    """
    Unit tests for lib.packet.path.PeerPath.get_of
    """
    def _check(self, idx):
        peer_path = PeerPath()
        peer_path.up_segment_info = 0
        peer_path.up_segment_hops = [1, 2, 3]
        peer_path.up_segment_peering_link = 4
        peer_path.up_segment_upstream_ad = 5
        peer_path.down_segment_info = 6
        peer_path.down_segment_upstream_ad = 7
        peer_path.down_segment_peering_link = 8
        peer_path.down_segment_hops = [9, 10, 11]
        ofs = list(range(12))
        ntools.eq_(peer_path.get_of(idx), ofs[idx])

    def test(self):
        for i in range(12):
            yield self._check, i


class TestEmptyPathInit(object):
    """
    Unit tests for lib.packet.path.EmptyPath.__init__
    """
    @patch("lib.packet.path.PathBase.__init__")
    def test_basic(self, __init__):
        empty_path = EmptyPath()
        __init__.assert_called_once_with(empty_path)

    @patch("lib.packet.path.EmptyPath.parse")
    def test_raw(self, parse):
        empty_path = EmptyPath('rawstring')
        parse.assert_called_once_with('rawstring')


class TestEmptyPathParse(object):
    """
    Unit tests for lib.packet.path.EmptyPath.parse
    """
    def test_basic(self):
        empty_path = EmptyPath()
        raw = b'\01' * InfoOpaqueField.LEN
        empty_path.parse(raw)
        ntools.eq_(empty_path.up_segment_info, InfoOpaqueField(raw))
        ntools.eq_(empty_path.up_segment_info, empty_path.down_segment_info)
        ntools.assert_true(empty_path.parsed)

    def test_wrong_type(self):
        empty_path = EmptyPath()
        ntools.assert_raises(AssertionError, empty_path.parse, 10)


class TestEmptyPathPack(object):
    """
    Unit tests for lib.packet.path.EmptyPath.pack
    """
    def test(self):
        empty_path = EmptyPath()
        ntools.eq_(empty_path.pack(), b'')


class TestEmptyPathIsFirstHop(object):
    """
    Unit tests for lib.packet.path.EmptyPath.is_first_hop
    """
    def test(self):
        empty_path = EmptyPath()
        ntools.assert_true(empty_path.is_first_hop(1))


class TestEmptyPathIsLastHop(object):
    """
    Unit tests for lib.packet.path.EmptyPath.is_last_hop
    """
    def test(self):
        empty_path = EmptyPath()
        ntools.assert_true(empty_path.is_last_hop(1))


class TestEmptyPathGetFirstHopOf(object):
    """
    Unit tests for lib.packet.path.EmptyPath.get_first_hop_of
    """
    def test(self):
        empty_path = EmptyPath()
        ntools.assert_is_none(empty_path.get_first_hop_of())


class TestEmptyPathGetOf(object):
    """
    Unit tests for lib.packet.path.EmptyPath.get_of
    """
    def test(self):
        empty_path = EmptyPath()
        empty_path.up_segment_info = 1
        ntools.eq_(empty_path.get_of(123), 1)


if __name__ == "__main__":
    nose.run(defaultTest=__name__)
