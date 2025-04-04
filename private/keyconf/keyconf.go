// Copyright 2018 ETH Zurich, Anapaya Systems
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

package keyconf

import (
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/scionproto/scion/pkg/private/serrors"
)

const (
	MasterKey0 = "master0.key"
	MasterKey1 = "master1.key"

	RawKey = "raw"
)

// Errors
var (
	ErrOpen    = errors.New("unable to load key")
	ErrParse   = errors.New("unable to parse key file")
	ErrUnknown = errors.New("unknown algorithm")
)

// loadKey decodes a base64 encoded key stored in file and returns the raw bytes.
func loadKey(file string, algo string) ([]byte, error) {
	b, err := os.ReadFile(file)
	if err != nil {
		return nil, serrors.JoinNoStack(ErrOpen, err)
	}
	dbuf := make([]byte, base64.StdEncoding.DecodedLen(len(b)))
	n, err := base64.StdEncoding.Decode(dbuf, b)
	if err != nil {
		return nil, serrors.JoinNoStack(ErrParse, err)
	}
	dbuf = dbuf[:n]
	if strings.ToLower(algo) != RawKey {
		return nil, serrors.JoinNoStack(ErrUnknown, nil, "algo", algo)
	}
	return dbuf, nil
}

type Master struct {
	Key0 []byte
	Key1 []byte
}

func LoadMaster(path string) (Master, error) {
	var err error
	m := Master{}
	if m.Key0, err = loadKey(filepath.Join(path, MasterKey0), RawKey); err != nil {
		return m, err
	}
	if m.Key1, err = loadKey(filepath.Join(path, MasterKey1), RawKey); err != nil {
		return m, err
	}
	return m, nil
}

func (m Master) MarshalJSON() ([]byte, error) {
	return []byte(`{"key0":"redacted","key1":"redacted"}`), nil
}

func (m Master) String() string {
	return fmt.Sprintf("Key0:%s Key1:%s",
		//XXX(roosd): Uncomment for debugging.
		//m.Key0, m.Key1
		"<redacted>", "<redacted>")
}
