#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) Glorhop, 2026
"""Exercise layout rejection using a self-contained ELF64 firmware fixture."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts'
SCRIPT = SCRIPT / 'gen-arm64-entry-layout.py'
SPEC = importlib.util.spec_from_file_location('entry_layout', SCRIPT)
LAYOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAYOUT)


def fixture(root):
    """Two RX pages, a separate mutable header, and the two-HVC entry ABI."""
    directory = root / 'hypervisor'
    directory.mkdir()
    firmware = bytearray(0x3000)
    struct.pack_into('<8sQQQ', firmware, 0, b'JAILHOUS', 0x4000, 0, 0x2000)
    struct.pack_into('<II', firmware, 0x1000, 0xd503201f, 0xd65f03c0)
    branch = 0x94000000 | ((-0x1000 // 4) & 0x3ffffff)
    struct.pack_into('<IIII', firmware, 0x2000, branch,
                     0xd4000002, 0xd4000002, 0x14000000)
    names = bytearray(b'\0')
    symbol_data = bytearray(24)
    symbols = [('hypervisor_header', 0, 1), ('arm_dcaches_flush', 0x1000, 2),
               ('cache_end', 0x1008, 2), ('arch_entry', 0x2000, 2),
               ('el2_entry', 0x2010, 2)]
    for name, address, index in symbols:
        offset = len(names)
        names += name.encode() + b'\0'
        symbol_data += struct.pack('<IBBHQQ', offset, 0x12, 0,
                                   index, address, 0)
    section_names = b'\0.header\0.text\0.symtab\0.strtab\0.shstrtab\0'
    binary = bytearray(64)
    binary[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    sections = [(0,) * 10]
    for name, kind, flags, address, payload, link, entry in [
            ('.header', 1, 3, 0, firmware[:0x1000], 0, 0),
            ('.text', 1, 6, 0x1000, firmware[0x1000:], 0, 0),
            ('.symtab', 2, 0, 0, symbol_data, 4, 24),
            ('.strtab', 3, 0, 0, names, 0, 0),
            ('.shstrtab', 3, 0, 0, section_names, 0, 0)]:
        offset = len(binary)
        binary += payload
        sections.append((section_names.index(name.encode()), kind, flags,
                         address, offset, len(payload), link, 0, 1, entry))
    table = len(binary)
    for section in sections:
        binary += struct.pack('<IIQQQQIIQQ', *section)
    struct.pack_into('<HHIQQQIHHHHHH', binary, 16,
                     2, 183, 1, 0x2000, 0, table, 0,
                     64, 0, 0, 64, len(sections), 5)
    (directory / 'hypervisor.o').write_bytes(binary)
    (directory / 'jailhouse.bin').write_bytes(firmware)


class EntryLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture(self.root)

    def mutate_instruction(self, offset, instruction):
        path = self.root / 'hypervisor/jailhouse.bin'
        firmware = bytearray(path.read_bytes())
        struct.pack_into('<I', firmware, offset, instruction)
        path.write_bytes(firmware)
        path = self.root / 'hypervisor/hypervisor.o'
        raw, sections, _ = LAYOUT.elf(path)
        section = next(s for s in sections if s['flags'] & 2 and
                       s['address'] <= offset < s['address'] + s['size'])
        raw = bytearray(raw)
        struct.pack_into('<I', raw,
                         section['offset'] + offset - section['address'],
                         instruction)
        path.write_bytes(raw)

    def test_valid_firmware_maps_only_code_pages(self):
        report = LAYOUT.layout(self.root)
        self.assertEqual(report['exec_ranges'], [[0x1000, 0x3000]])
        self.assertEqual(report['entry'], 0x2000)
        self.assertNotIn([0, 0x1000], report['exec_ranges'])

    def test_binary_from_another_build_is_rejected(self):
        path = self.root / 'hypervisor/jailhouse.bin'
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Firmware bytes'):
            LAYOUT.layout(self.root)

    def test_indirect_entry_transfer_requires_review(self):
        self.mutate_instruction(0x200c, 0xd61f0120)  # BR x9
        with self.assertRaisesRegex(ValueError, 'indirect EL1'):
            LAYOUT.layout(self.root)

    def test_branch_outside_audited_code_requires_review(self):
        self.mutate_instruction(0x200c, 0x14000010)
        with self.assertRaisesRegex(ValueError, 'branch escapes'):
            LAYOUT.layout(self.root)

    def test_missing_hypervisor_call_requires_review(self):
        self.mutate_instruction(0x2008, 0xd503201f)
        with self.assertRaisesRegex(ValueError, 'HVC sequence'):
            LAYOUT.layout(self.root)

    def test_nonreturning_cache_helper_is_rejected(self):
        self.mutate_instruction(0x1004, 0xd503201f)
        with self.assertRaisesRegex(ValueError, 'end in ret'):
            LAYOUT.layout(self.root)

    def test_writable_executable_page_is_rejected(self):
        path = self.root / 'hypervisor/hypervisor.o'
        raw = bytearray(path.read_bytes())
        table = struct.unpack_from('<Q', raw, 40)[0]
        struct.pack_into('<Q', raw, table + 2 * 64 + 8, 7)
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'writable ELF'):
            LAYOUT.layout(self.root)

    def test_truncated_section_table_is_rejected(self):
        path = self.root / 'hypervisor/hypervisor.o'
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, 'section table'):
            LAYOUT.layout(self.root)

    def test_cli_preserves_header_when_binding_is_unchanged(self):
        output = self.root / 'entry.h'
        command = [sys.executable, str(SCRIPT), '--hypervisor-dir',
                   str(self.root / 'hypervisor'), '--output', str(output)]
        subprocess.run(command, check=True, capture_output=True)
        before = (output.read_bytes(), output.stat().st_mtime_ns)
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual(before, (output.read_bytes(),
                                  output.stat().st_mtime_ns))
        self.mutate_instruction(0x2008, 0xd503201f)
        result = subprocess.run(command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before[0], output.read_bytes())


if __name__ == '__main__':
    unittest.main()
