// Copyright 2020 Anapaya Systems
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package cases

import (
	"hash"
	"net"
	"path/filepath"

	"github.com/gopacket/gopacket"
	"github.com/gopacket/gopacket/layers"

	"github.com/scionproto/scion/pkg/addr"
	"github.com/scionproto/scion/pkg/slayers"
	"github.com/scionproto/scion/pkg/slayers/path"
	"github.com/scionproto/scion/pkg/slayers/path/empty"
	"github.com/scionproto/scion/pkg/slayers/path/onehop"
	"github.com/scionproto/scion/tools/braccept/runner"
)

func bfdNormalizePacket(pkt gopacket.Packet) {
	// Apply all the standard normalizations.
	runner.DefaultNormalizePacket(pkt)
	for _, l := range pkt.Layers() {
		switch v := l.(type) {
		case *slayers.SCION:
			switch p := v.Path.(type) {
			case *onehop.Path:
				// Timestamps are generated by the sender from the current time.
				p.Info.Timestamp = 0
				// MACs are different because of different timestamps.
				for i := range p.FirstHop.Mac {
					p.FirstHop.Mac[i] = 0
				}
			}
		case *layers.BFD:
			// This field is randomly chosen by the sender.
			v.MyDiscriminator = 0
		}
	}
}

// ExternalBFD sends an unbootstrapped BFD message to an external interface
// and expects a bootstrapped BFD message on the same interface.
func ExternalBFD(artifactsDir string, mac hash.Hash) runner.Case {
	options := gopacket.SerializeOptions{
		FixLengths:       true,
		ComputeChecksums: true,
	}
	ethernet := &layers.Ethernet{
		SrcMAC:       net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0xbe, 0xef},
		DstMAC:       net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0x00, 0x13},
		EthernetType: layers.EthernetTypeIPv4,
	}
	ip := &layers.IPv4{
		Version:  4,
		IHL:      5,
		TTL:      64,
		SrcIP:    net.IP{192, 168, 13, 3},
		DstIP:    net.IP{192, 168, 13, 2},
		Protocol: layers.IPProtocolUDP,
		Flags:    layers.IPv4DontFragment,
	}
	udp := &layers.UDP{
		SrcPort: layers.UDPPort(40000),
		DstPort: layers.UDPPort(50000),
	}
	_ = udp.SetNetworkLayerForChecksum(ip)
	localIA, _ := addr.ParseIA("1-ff00:0:1")
	remoteIA, _ := addr.ParseIA("1-ff00:0:3")
	ohp := &onehop.Path{
		Info: path.InfoField{
			ConsDir:   true,
			Timestamp: 0, // TODO: util.TimeToSecs(time.Now()),
		},
		FirstHop: path.HopField{
			ExpTime:     63,
			ConsIngress: 0,
			ConsEgress:  131,
		},
	}
	ohp.FirstHop.Mac = path.MAC(mac, ohp.Info, ohp.FirstHop, nil)
	scionL := &slayers.SCION{
		Version:      0,
		TrafficClass: 0xb8,
		FlowID:       0xdead,
		NextHdr:      slayers.L4BFD,
		PathType:     onehop.PathType,
		Path:         ohp,
		DstIA:        localIA,
		SrcIA:        remoteIA,
	}
	err := scionL.SetSrcAddr(addr.MustParseHost("192.168.13.3"))
	if err != nil {
		panic(err)
	}
	err = scionL.SetDstAddr(addr.MustParseHost("192.168.13.2"))
	if err != nil {
		panic(err)
	}
	bfd := &layers.BFD{
		Version:               1,
		State:                 layers.BFDStateDown,
		DetectMultiplier:      3,
		MyDiscriminator:       12345,
		YourDiscriminator:     0,
		DesiredMinTxInterval:  1000000,
		RequiredMinRxInterval: 200000,
	}
	// Prepare input packet
	input := gopacket.NewSerializeBuffer()
	err = gopacket.SerializeLayers(input, options, ethernet, ip, udp, scionL, bfd)
	if err != nil {
		panic(err)
	}
	// Prepare want packet
	want := gopacket.NewSerializeBuffer()
	ethernet.SrcMAC = net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0x00, 0x13}
	ethernet.DstMAC = net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0xbe, 0xef}
	ip.SrcIP = net.IP{192, 168, 13, 2}
	ip.DstIP = net.IP{192, 168, 13, 3}
	udp.SrcPort, udp.DstPort = udp.DstPort, udp.SrcPort
	scionL.DstIA = remoteIA
	scionL.SrcIA = localIA
	err = scionL.SetSrcAddr(addr.MustParseHost("192.168.13.2"))
	if err != nil {
		panic(err)
	}
	err = scionL.SetDstAddr(addr.MustParseHost("192.168.13.3"))
	if err != nil {
		panic(err)
	}
	bfd.State = layers.BFDStateInit
	bfd.YourDiscriminator = 12345
	bfd.DesiredMinTxInterval = 200000
	err = gopacket.SerializeLayers(want, options, ethernet, ip, udp, scionL, bfd)
	if err != nil {
		panic(err)
	}
	return runner.Case{
		Name:              "ExternalBFD",
		WriteTo:           "veth_131_host",
		ReadFrom:          "veth_131_host",
		Input:             input.Bytes(),
		Want:              want.Bytes(),
		StoreDir:          filepath.Join(artifactsDir, "ExternalBFD"),
		IgnoreNonMatching: true,
		NormalizePacket:   bfdNormalizePacket,
	}
}

// InternalBFD sends an unbootstrapped BFD message to an internal interface
// and expects a bootstrapped BFD message on the same interface.
func InternalBFD(artifactsDir string, mac hash.Hash) runner.Case {
	options := gopacket.SerializeOptions{
		FixLengths:       true,
		ComputeChecksums: true,
	}
	ethernet := &layers.Ethernet{
		SrcMAC:       net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0xbe, 0xef},
		DstMAC:       net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0x00, 0x01},
		EthernetType: layers.EthernetTypeIPv4,
	}
	ip := &layers.IPv4{
		Version:  4,
		IHL:      5,
		TTL:      64,
		SrcIP:    net.IP{192, 168, 0, 13},
		DstIP:    net.IP{192, 168, 0, 11},
		Protocol: layers.IPProtocolUDP,
		Flags:    layers.IPv4DontFragment,
	}
	udp := &layers.UDP{
		SrcPort: layers.UDPPort(30003),
		DstPort: layers.UDPPort(30001),
	}
	_ = udp.SetNetworkLayerForChecksum(ip)
	localIA, _ := addr.ParseIA("1-ff00:0:1")
	scionL := &slayers.SCION{
		Version:      0,
		TrafficClass: 0xb8,
		FlowID:       0xdead,
		NextHdr:      slayers.L4BFD,
		PathType:     empty.PathType,
		Path:         &empty.Path{},
		SrcIA:        localIA,
		DstIA:        localIA,
	}
	err := scionL.SetSrcAddr(addr.MustParseHost("192.168.0.13"))
	if err != nil {
		panic(err)
	}
	err = scionL.SetDstAddr(addr.MustParseHost("192.168.0.11"))
	if err != nil {
		panic(err)
	}
	bfd := &layers.BFD{
		Version:               1,
		State:                 layers.BFDStateDown,
		DetectMultiplier:      3,
		MyDiscriminator:       12345,
		YourDiscriminator:     0,
		DesiredMinTxInterval:  1000000,
		RequiredMinRxInterval: 200000,
	}
	// Prepare input packet
	input := gopacket.NewSerializeBuffer()
	err = gopacket.SerializeLayers(input, options, ethernet, ip, udp, scionL, bfd)
	if err != nil {
		panic(err)
	}
	// Prepare want packet
	want := gopacket.NewSerializeBuffer()
	ethernet.SrcMAC = net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0x00, 0x01}
	ethernet.DstMAC = net.HardwareAddr{0xf0, 0x0d, 0xca, 0xfe, 0xbe, 0xef}
	ip.SrcIP = net.IP{192, 168, 0, 11}
	ip.DstIP = net.IP{192, 168, 0, 13}
	udp.SrcPort, udp.DstPort = udp.DstPort, udp.SrcPort
	err = scionL.SetSrcAddr(addr.MustParseHost("192.168.0.11"))
	if err != nil {
		panic(err)
	}
	err = scionL.SetDstAddr(addr.MustParseHost("192.168.0.13"))
	if err != nil {
		panic(err)
	}
	bfd.State = layers.BFDStateInit
	bfd.YourDiscriminator = 12345
	bfd.DesiredMinTxInterval = 200000
	err = gopacket.SerializeLayers(want, options, ethernet, ip, udp, scionL, bfd)
	if err != nil {
		panic(err)
	}
	return runner.Case{
		Name:              "InternalBFD",
		WriteTo:           "veth_int_host",
		ReadFrom:          "veth_int_host",
		Input:             input.Bytes(),
		Want:              want.Bytes(),
		StoreDir:          filepath.Join(artifactsDir, "InternalBFD"),
		IgnoreNonMatching: true,
		NormalizePacket:   bfdNormalizePacket,
	}
}
