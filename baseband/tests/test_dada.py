# Licensed under the GPLv3 - see LICENSE.rst
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import io
import numpy as np
import astropy.units as u
from astropy.tests.helper import pytest, catch_warnings
from .. import dada
from ..dada.base import DADAFileNameSequencer

SAMPLE_FILE = os.path.join(os.path.dirname(__file__), 'sample.dada')


class TestDADA(object):
    def setup(self):
        with open(SAMPLE_FILE, 'rb') as fh:
            self.header = dada.DADAHeader.fromfile(fh)
            self.payload = dada.DADAPayload.fromfile(fh, self.header)

    def test_header(self):
        with open(SAMPLE_FILE, 'rb') as fh:
            header = dada.DADAHeader.fromfile(fh)
            assert header.size == 4096
            assert fh.tell() == 4096
        assert header['NDIM'] == 2
        assert header['NCHAN'] == 1
        assert header['UTC_START'] == '2013-07-02-01:37:40'
        assert header['OBS_OFFSET'] == 6400000000  # 100 s
        assert header.time.isot == '2013-07-02T01:39:20.000'
        assert header.framesize == 64000 + 4096
        assert header.payloadsize == 64000
        assert header.mutable is False
        with io.BytesIO() as s:
            header.tofile(s)
            assert s.tell() == header.size
            s.seek(0)
            header2 = dada.DADAHeader.fromfile(s)
            assert s.tell() == header.size
        assert header2 == header
        assert header2.mutable is False
        # Note that this is not guaranteed to preserve order!
        header3 = dada.DADAHeader.fromkeys(**header)
        assert header3 == header
        assert header3.mutable is True
        # # Try initialising with properties instead of keywords.
        # Here, we first just try the start time.
        header4 = dada.DADAHeader.fromvalues(
            time0=header.time0, offset=header.time-header.time0,
            bps=header.bps, complex_data=header.complex_data,
            bandwidth=header.bandwidth, sideband=header.sideband,
            samples_per_frame=header.samples_per_frame,
            sample_shape=header.sample_shape,
            source=header['SOURCE'], ra=header['RA'], dec=header['DEC'],
            telescope=header['TELESCOPE'], instrument=header['INSTRUMENT'],
            receiver=header['RECEIVER'], freq=header['FREQ'],
            pic_version=header['PIC_VERSION'])
        assert header4 == header
        assert header4.mutable is True
        # And now try both start time and time of observation.
        header5 = dada.DADAHeader.fromvalues(
            offset=header.offset, time=header.time,
            bps=header.bps, complex_data=header.complex_data,
            bandwidth=header.bandwidth, sideband=header.sideband,
            samples_per_frame=header.samples_per_frame,
            sample_shape=header.sample_shape,
            source=header['SOURCE'], ra=header['RA'], dec=header['DEC'],
            telescope=header['TELESCOPE'], instrument=header['INSTRUMENT'],
            receiver=header['RECEIVER'], freq=header['FREQ'],
            pic_version=header['PIC_VERSION'])
        assert header5 == header
        # Check repr can be used to instantiate header
        header6 = eval('dada.' + repr(header))
        assert header6 == header
        # repr includes the comments
        assert header6.comments == header.comments
        # Therefore repr should be identical too.
        assert repr(header6) == repr(header)
        # Check instantiation via tuple
        header7 = dada.DADAHeader(((key, (header[key], header.comments[key]))
                                   for key in header))
        assert header7 == header
        assert header7.comments == header.comments
        # Check copying
        header8 = header.copy()
        assert header8 == header
        assert header8.mutable is True
        assert header8.comments == header.comments

    def test_payload(self):
        payload = self.payload
        assert payload.size == 64000
        assert payload.shape == (16000, 2, 1)
        assert payload.dtype == np.complex64
        assert np.all(payload[:3] == np.array(
            [[[-38.-38.j], [-38.-38.j]],
             [[-38.-38.j], [-40.+0.j]],
             [[-105.+60.j], [85.-15.j]]], dtype=np.complex64))

        with io.BytesIO() as s:
            payload.tofile(s)
            s.seek(0)
            payload2 = dada.DADAPayload.fromfile(s, payloadsize=64000, bps=8,
                                                 complex_data=True,
                                                 sample_shape=(2, 1))
            assert payload2 == payload
            with pytest.raises(EOFError):
                # Too few bytes.
                s.seek(100)
                dada.DADAPayload.fromfile(s, self.header)
        payload3 = dada.DADAPayload.fromdata(payload.data, bps=8)
        assert payload3 == payload
        with open(SAMPLE_FILE, 'rb') as fh:
            fh.seek(4096)
            payload4 = dada.DADAPayload.fromfile(fh, self.header, memmap=True)
        assert isinstance(payload4.words, np.memmap)
        assert not isinstance(payload.words, np.memmap)
        assert payload == payload4

    def test_frame(self):
        with dada.open(SAMPLE_FILE, 'rb') as fh:
            frame = fh.read_frame(memmap=False)
        header, payload = frame.header, frame.payload
        assert header == self.header
        assert payload == self.payload
        assert frame == dada.DADAFrame(header, payload)
        assert np.all(frame[:3] == np.array(
            [[[-38.-38.j], [-38.-38.j]],
             [[-38.-38.j], [-40.+0.j]],
             [[-105.+60.j], [85.-15.j]]], dtype=np.complex64))
        with io.BytesIO() as s:
            frame.tofile(s)
            s.seek(0)
            frame2 = dada.DADAFrame.fromfile(s, memmap=False)
        assert frame2 == frame
        frame3 = dada.DADAFrame.fromdata(payload.data, header)
        assert frame3 == frame
        frame4 = dada.DADAFrame.fromdata(payload.data, **header)
        assert frame4 == frame
        header5 = header.copy()
        frame5 = dada.DADAFrame(header5, payload, valid=False)
        assert frame5.valid is False
        assert np.all(frame5.data == 0.)
        frame5.valid = True
        assert frame5 == frame

    def test_frame_memmap(self, tmpdir):
        # Get frame regular way.
        with dada.open(SAMPLE_FILE, 'rb') as fr:
            frame = fr.read_frame(memmap=False)
        assert not isinstance(frame.payload.words, np.memmap)
        # Check that if we map it instead, we get the same result.
        with dada.open(SAMPLE_FILE, 'rb') as fh:
            frame2 = fh.read_frame(memmap=True)
        assert frame2 == frame
        assert isinstance(frame2.payload.words, np.memmap)
        # Bit superfluous perhaps, but check decoding as well.
        assert np.all(frame2[:3] == np.array(
            [[[-38.-38.j], [-38.-38.j]],
             [[-38.-38.j], [-40.+0.j]],
             [[-105.+60.j], [85.-15.j]]], dtype=np.complex64))
        assert np.all(frame2.data == frame.data)

        # Now check writing.  First, without memmap, just ensuring writing
        # to file works as well as to BytesIO done above.
        filename = str(tmpdir.join('a.dada'))
        with dada.open(filename, 'wb') as fw:
            fw.write_frame(frame)

        with dada.open(filename, 'rb') as fw:
            frame3 = fw.read_frame()

        assert frame3 == frame
        # Now memmap file to be written to.
        with dada.open(filename, 'wb') as fw:
            frame4 = fw.memmap_frame(frame.header)
        # Initially no data set, so frames should not match yet.
        assert frame4 != frame
        # So, if we read this file, it also should not match
        with dada.open(filename, 'rb') as fw:
            frame5 = fw.read_frame()
        assert frame5 != frame

        # Fill in some data.  This should only update some words.
        frame4[:20] = frame[:20]
        assert np.all(frame4[:20] == frame[:20])
        assert frame4 != frame
        # Update the rest, so it becomes the same.
        frame4[20:] = frame[20:]
        assert frame4 == frame
        # flush to disk just to be sure, then read and check it is OK.
        frame4.payload.words.flush()
        with dada.open(filename, 'rb') as fw:
            frame6 = fw.read_frame()

        assert frame6 == frame

    def test_filestreamer(self, tmpdir):
        time0 = self.header.time
        with dada.open(SAMPLE_FILE, 'rs') as fh:
            assert fh.header0 == self.header
            assert fh.size == 16000
            assert fh.time0 == time0
            record1 = fh.read(12)
            assert fh.tell() == 12
            fh.seek(10000)
            record2 = fh.read(2)
            assert fh.tell() == 10002
            assert np.abs(fh.tell(unit='time') -
                          (time0 + 10002 / (16*u.MHz))) < 1. * u.ns
            fh.seek(fh.time0 + 1000 / (16*u.MHz))
            assert fh.tell() == 1000
            assert fh.header1 is fh.header0
            assert np.abs(fh.time1 - (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns

        assert record1.shape == (12, 2)
        assert np.all(record1[:3] == np.array(
            [[-38.-38.j, -38.-38.j],
             [-38.-38.j, -40.+0.j],
             [-105.+60.j, 85.-15.j]], dtype=np.complex64))
        assert record1.shape == (12, 2) and record1.dtype == np.complex64
        assert np.all(record1 == self.payload[:12].squeeze())
        assert record2.shape == (2, 2)
        assert np.all(record2 == self.payload[10000:10002].squeeze())

        filename = str(tmpdir.join('a.dada'))
        with dada.open(filename, 'ws', header=self.header) as fw:
            fw.write(self.payload.data)
            assert fw.time0 == time0
            assert np.abs(fw.tell(unit='time') -
                          (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns

        with dada.open(filename, 'rs') as fh:
            data = fh.read()
            assert fh.time0 == time0
            assert np.abs(fh.tell(unit='time') -
                          (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns
            assert np.abs(fh.time1 == fh.tell(unit='time'))
        assert np.all(data == self.payload.data.squeeze())

    def test_incomplete_stream(self, tmpdir):
        filename = str(tmpdir.join('a.dada'))
        with catch_warnings(UserWarning) as w:
            with dada.open(filename, 'ws', header=self.header) as fw:
                fw.write(self.payload[:10])
        assert len(w) == 1
        assert 'partial buffer' in str(w[0].message)

    def test_multiple_files_stream(self, tmpdir):
        time0 = self.header.time
        data = self.payload.data.squeeze()
        header = self.header.copy()
        header.payloadsize = self.header.payloadsize // 2
        filenames = (str(tmpdir.join('a.dada')),
                     str(tmpdir.join('b.dada')))
        with dada.open(filenames, 'ws', header=header) as fw:
            time0 = fw.time0
            fw.write(data[:1000])
            time1000 = fw.tell(unit='time')
            fw.write(data[1000:])
            time_end = fw.tell(unit='time')
        assert time0 == header.time
        assert np.abs(time1000 - (time0 + 1000 / (16.*u.MHz))) < 1.*u.ns
        assert np.abs(time_end - (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns

        with dada.open(filenames[1], 'rs') as fr:
            assert np.abs(fr.tell(unit='time') -
                          (time0 + 8000 / (16.*u.MHz))) < 1.*u.ns
            data1 = fr.read()
        assert np.all(data1 == data[8000:])

        with dada.open(filenames, 'rs') as fr:
            assert fr.time0 == time0
            assert fr.tell(unit='time') == time0
            assert np.abs(fr.time1 - (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns
            data2 = fr.read()
            assert fr.tell(unit='time') == fr.time1
        assert np.all(data2 == data)

    def test_template_stream(self, tmpdir):
        time0 = self.header.time
        data = self.payload.data.squeeze()
        header = self.header.copy()
        header.payloadsize = self.header.payloadsize // 4
        template = str(tmpdir.join('a{frame_nr}.dada'))
        with dada.open(template, 'ws', header=header) as fw:
            fw.write(data[:1000])
            time1000 = fw.tell(unit='time')
            fw.write(data[1000:])
            time_end = fw.tell(unit='time')
        assert np.abs(time1000 - (header.time + 1000 / (16.*u.MHz))) < 1.*u.ns
        assert np.abs(time_end - (header.time + 16000 / (16.*u.MHz))) < 1.*u.ns

        with dada.open(template.format(frame_nr=1), 'rs') as fr:
            data1 = fr.read()
            assert fr.tell(unit='time') == fr.time1
            assert np.abs(fr.time0 - (time0 + 4000 / (16.*u.MHz))) < 1.*u.ns
            assert np.abs(fr.time1 - (time0 + 8000 / (16.*u.MHz))) < 1.*u.ns
        assert np.all(data1 == data[4000:8000])

        with dada.open(template, 'rs') as fr:
            assert fr.tell(unit='time') == time0
            data2 = fr.read()
            assert fr.time1 == fr.tell(unit='time')
            assert np.abs(fr.time1 -
                          (header.time + 16000 / (16.*u.MHz))) < 1.*u.ns
        assert np.all(data2 == data)

        # More complicated template, 8 files
        header.payloadsize = self.header.payloadsize // 8
        template = str(tmpdir
                       .join('{utc_start}_{obs_offset:016d}.000000.dada'))
        with dada.open(template, 'ws', header=header) as fw:
            fw.write(data[:7000])
            assert fw.time0 == header.time
            assert np.abs(fw.tell(unit='time') -
                          (time0 + 7000 / (16.*u.MHz))) < 1.*u.ns
            assert fw._frame_nr == 3
            fw.write(data[7000:])
            assert np.abs(fw.tell(unit='time') -
                          (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns

        name3 = template.format(utc_start=header['UTC_START'],
                                obs_offset=header['OBS_OFFSET'] +
                                3 * header.payloadsize)
        with dada.open(name3, 'rs') as fr:
            assert np.abs(fr.time0 - (time0 + 6000 / (16.*u.MHz))) < 1.*u.ns
            assert np.abs(fr.time1 - (time0 + 8000 / (16.*u.MHz))) < 1.*u.ns
            data1 = fr.read()
            assert fr.time1 == fr.tell(unit='time')
        assert np.all(data1 == data[6000:8000])

        name0 = template.format(utc_start=header['UTC_START'],
                                obs_offset=header['OBS_OFFSET'])
        with dada.open(name0, 'rs', template=template) as fr:
            assert fr.tell(unit='time') == time0
            data2 = fr.read()
            assert fr.tell(unit='time') == fr.time1
            assert np.abs(fr.time1 - (time0 + 16000 / (16.*u.MHz))) < 1.*u.ns
        assert np.all(data2 == data)


class TestDADAFileNameSequencer(object):
    def setup(self):
        with open(SAMPLE_FILE, 'rb') as fh:
            self.header = dada.DADAHeader.fromfile(fh)

    def test_basic_enumeration(self):
        fns1 = DADAFileNameSequencer('x{file_nr:03d}.dada', {})
        assert fns1[0] == 'x000.dada'
        assert fns1[100] == 'x100.dada'
        fns2 = DADAFileNameSequencer('{snake}_{frame_nr}', {'SNAKE': 'python'})
        assert fns2[10] == 'python_10'
        fns3 = DADAFileNameSequencer('{obs_offset:06d}.x', {'OBS_OFFSET': 10,
                                                            'FILE_SIZE': 20})
        assert fns3[0] == '000010.x'
        assert fns3[9] == '000190.x'

        with pytest.raises(KeyError):
            DADAFileNameSequencer('{snake:06d}.x', {'PYTHON': 10})

        with pytest.raises(KeyError):
            DADAFileNameSequencer('{obs_offset:06d}.x', {'OBS_OFFSET': 10})

    def test_header_enumeration(self):
        template = '{frame_nr}_{obs_offset:016d}.dada'
        fns = DADAFileNameSequencer(template, self.header)
        assert fns[0] == '0_0000006400000000.dada'
        assert fns[1] == '1_0000006400064000.dada'
        assert fns[10] == '10_0000006400640000.dada'

    def test_complicated_enumeration(self):
        # Follow the typical naming scheme:
        # 2016-04-23-07:29:30_0000000000000000.000000.dada
        template = '{utc_start}_{obs_offset:016d}.000000.dada'
        fns = DADAFileNameSequencer(template, self.header)
        assert fns[0] == '2013-07-02-01:37:40_0000006400000000.000000.dada'
        assert fns[100] == '2013-07-02-01:37:40_0000006406400000.000000.dada'

    def test_len(self, tmpdir):
        template = str(tmpdir.join('a{frame_nr}.dada'))
        fns = DADAFileNameSequencer(template, {})
        for i in range(5):
            assert len(fns) == i
            filename = fns[i]
            assert filename.endswith('a{}.dada'.format(i))
            with open(filename, 'wb') as fh:
                fh.write(b'bird')
        assert len(fns) == 5
