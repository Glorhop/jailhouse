#!/usr/bin/env python3
# Jailhouse, a Linux-based partitioning hypervisor
#
# Copyright (c) Glorhop, 2026
#
# Authors:
#  Glorhop <1150595033@qq.com>
#
# This work is licensed under the terms of the GNU GPL, version 2. See
# the COPYING file in the top-level directory.

"""Offline ARM image placement tests; never access /dev/jailhouse."""

import contextlib
import gzip
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'tools/jailhouse-cell-linux'
helper = {'__file__': str(HELPER), '__name__': 'offline_loader_test'}
saved_path = sys.path[:]
# Only load definitions, excluding the command-line cell-create path.
exec(compile(HELPER.read_text().split(
    '# pretend to be part of the jailhouse tool')[0],
    str(HELPER), 'exec'), helper)
sys.path[:] = saved_path
MemRegion = helper['config_parser'].MemRegion


def minimal_dtb():
    # Build a complete FDT fixture without dtc or board artifacts.
    strings = b'#address-cells' + bytes([0]) + b'#size-cells' + bytes([0])
    nodes = struct.pack('>II', 1, 0)
    nodes += struct.pack('>IIII', 3, 4, 0, 2)
    nodes += struct.pack('>IIII', 3, 4, 15, 2)
    for name in [b'memory', b'chosen']:
        padded = name + bytes(4 - len(name) % 4)
        nodes += struct.pack('>I', 1) + padded + struct.pack('>I', 2)
    nodes += struct.pack('>II', 2, 9)
    header = struct.pack('>10I', 0xd00dfeed, 56 + len(nodes) + len(strings),
                         56, 56 + len(nodes), 40, 17, 16, 0,
                         len(strings), len(nodes))
    return header + bytes(16) + nodes + strings


def image(size=0x1801, memory=0x6000, offset=0x80000):
    data = bytearray(size)
    struct.pack_into('<QQQ', data, 8, offset, memory, 0)
    data[56:60] = b'ARM\x64'
    return bytes(data)


def region(start=0x10003000, size=0x10000000, flags=0x47):
    return MemRegion(struct.pack('QQQQ', start, start, size, flags))


class HelperBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / 'Image').write_bytes(image())
        (self.directory / 'initrd').write_bytes(
            gzip.compress(b'070701' + b'x' * 8193))
        (self.directory / 'guest.dtb').write_bytes(minimal_dtb())

    def setup_arm(self, regions=None, **options):
        with contextlib.ExitStack() as stack:
            args = SimpleNamespace(
                kernel=stack.enter_context(
                    open(
                        self.directory / 'Image',
                        'rb')),
                initrd=stack.enter_context(
                    open(
                        self.directory / 'initrd',
                        'rb')),
                dtb=stack.enter_context(
                    open(
                        self.directory / 'guest.dtb',
                        'rb')),
                kernel_decomp_factor=None,
                initrd_unpacked_size=None,
                cmdline=None)
            for key, value in options.items():
                setattr(args, key, value)
            arch = helper['ARM64']()
            arch.setup(
                args,
                SimpleNamespace(
                    cpu_reset_address=0,
                    memory_regions=regions or [
                        region()]))
            return arch

    def test_no_dma_predicate_requires_private_loadable_ram(self):
        self.assertTrue(region().is_loadable_ram())
        self.assertTrue(region(flags=0x4f).is_loadable_ram())
        for bit in (1, 2, 4, 0x40):
            self.assertFalse(region(flags=0x47 & ~bit).is_loadable_ram())
        for bit in (0x10, 0x20, 0x80):
            self.assertFalse(region(flags=0x47 | bit).is_loadable_ram())
        self.assertFalse(region(size=0).is_loadable_ram())
        # The legacy x86/E820 classifier remains unchanged.
        self.assertTrue(region(flags=0x0f).is_ram())
        self.assertFalse(region(flags=0x47).is_ram())

    def test_exact_fit_and_one_byte_underflow(self):
        first = self.setup_arm()
        end = first._layout['required_end_exclusive']
        exact = self.setup_arm([region(size=end - 0x10003000)])
        self.assertEqual(exact._layout['required_end_exclusive'], end)
        with self.assertRaisesRegex(RuntimeError, 'No space'):
            self.setup_arm([region(size=end - 0x10003000 - 1)])

    def test_compressed_and_expanded_ramdisk_are_both_counted(self):
        arch = self.setup_arm()
        layout = arch._layout
        self.assertEqual(layout['expanded_initramfs_payload_bytes'], 8199)
        self.assertEqual(layout['initrd_bytes'],
                         (self.directory / 'initrd').stat().st_size)
        self.assertEqual(
            layout['required_end_exclusive'],
            helper['page_align'](
                layout['initrd_end_exclusive']) +
            helper['page_align'](8199))
        with self.assertRaisesRegex(RuntimeError, 'No space'):
            self.setup_arm([region(size=layout['initrd_ipa'] - 0x10003000)])

    def test_header_memory_and_kernel_alignment(self):
        arch = self.setup_arm()
        self.assertEqual(
            arch._layout['kernel_reserved_bytes'], 0x6000 + 0x2000)
        self.assertEqual((arch.kernel_address() - 0x80000) % 0x200000, 0)
        self.assertGreaterEqual(arch.kernel_address(),
                                arch.dtb_address() + arch._dtb_capacity)
        zero = self.setup_arm(kernel_decomp_factor=0)
        self.assertEqual(zero._layout['kernel_reserved_bytes'], 0x6000)
        with self.assertRaisesRegex(RuntimeError, 'non-negative'):
            self.setup_arm(kernel_decomp_factor=-1)

    def test_skips_small_alias_and_failing_first_region(self):
        arch = self.setup_arm(
            [region(0, 0x10000), region(size=0x1000), region(0x20003000)])
        self.assertEqual(arch.dtb_address(), 0x20003000)
        combined = self.setup_arm([region(0, 0x2000000)])
        self.assertEqual(combined.dtb_address(), 0x10000)

    def test_gzip_stream_position_and_truncated_archive(self):
        with open(self.directory / 'initrd', 'rb') as stream:
            self.assertEqual(helper['initrd_expanded_size'](stream), 8199)
            self.assertEqual(stream.tell(), 0)
        p = self.directory / 'initrd'
        p.write_bytes(p.read_bytes()[:-3])
        with self.assertRaisesRegex(RuntimeError, 'Invalid gzip'):
            self.setup_arm()

    def test_unknown_initrd_needs_measured_override(self):
        (self.directory / 'initrd').write_bytes(b'unsupported compression')
        with self.assertRaisesRegex(RuntimeError, 'Unknown initrd'):
            self.setup_arm()
        self.assertEqual(self.setup_arm(initrd_unpacked_size=0x8000)._layout[
            'expanded_initramfs_payload_bytes'], 0x8000)

    def test_cannot_understate_gzip_expansion(self):
        with self.assertRaisesRegex(RuntimeError, 'smaller than measured'):
            self.setup_arm(initrd_unpacked_size=100)
        with self.assertRaisesRegex(RuntimeError, 'positive'):
            self.setup_arm(initrd_unpacked_size=0)

    def test_final_dtb_growth_exceeding_reservation_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'DTB exceeds'):
            self.setup_arm(cmdline='x' * 20000)

    def test_invalid_arm64_header_is_rejected(self):
        p = self.directory / 'Image'
        p.write_bytes(b'x' * 256)
        with self.assertRaisesRegex(RuntimeError, 'Image header'):
            self.setup_arm()
        p.write_bytes(image(memory=0))
        with self.assertRaisesRegex(RuntimeError, 'Image format'):
            self.setup_arm()

    def test_uncompressed_cpio_uses_file_length(self):
        data = b'070701' + b'x' * 9000
        (self.directory / 'initrd').write_bytes(data)
        arch = self.setup_arm()
        self.assertEqual(arch._layout['expanded_initramfs_payload_bytes'],
                         len(data))

    def test_no_initrd_does_not_reserve_expansion(self):
        arch = self.setup_arm(initrd=None)
        self.assertEqual(arch._layout['initrd_bytes'], 0)
        self.assertEqual(arch._layout['expanded_initramfs_payload_bytes'], 0)
        with self.assertRaisesRegex(RuntimeError, 'requires an initrd'):
            self.setup_arm(initrd=None, initrd_unpacked_size=4096)

    def test_ramdisk_properties_use_this_architecture_instance(self):
        with mock.patch.dict(helper, {'arch': object()}):
            arch = self.setup_arm()
        self.assertEqual(
            struct.unpack('>Q', arch.dtb.get_prop(
                '/chosen', 'linux,initrd-start'))[0],
            arch.ramdisk_address())
        self.assertEqual(
            struct.unpack('>Q', arch.dtb.get_prop(
                '/chosen', 'linux,initrd-end'))[0],
            arch._layout['initrd_end_exclusive'])

    def test_arm32_retains_decompression_margin(self):
        with mock.patch.dict(helper, {'ARM64': helper['ARM']}):
            arch = self.setup_arm()
        self.assertEqual(arch._layout['kernel_reserved_bytes'], 5 * 0x2000)


if __name__ == '__main__':
    unittest.main()
