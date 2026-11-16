#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
#
# Jailhouse, a Linux-based partitioning hypervisor
#
# Copyright (c) Glorhop, 2026
#
# Authors:
#  Glorhop <1150595033@qq.com>
#
# This work is licensed under the terms of the GNU GPL, version 2.  See
# the COPYING file in the top-level directory.
#
"""Check XZ100 resources without kernels, hardware or saved evidence.

Requires CROSS_COMPILE (default aarch64-linux-gnu-), dtc and fdtget.
Run: python3 tests/test_xz100_configs.py
"""

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pyjailhouse.config_parser import CellConfig, SystemConfig  # noqa: E402

READ, WRITE, EXEC, DMA, IO, COMM, LOAD, SHARED = [1 << i for i in range(8)]
PCI_FORMAT = '<BBHH6IHHBBHHQIBBH'
BOARDS = {
    'xzb100': dict(hv=0xc0000000, shared=0xc1000000, private=0xc2000000,
                   ecam=0x0f800000, gicd=0x0f400000, gicd_size=0x10000,
                   gicr=0x0f440000, gicr_size=0x200000,
                   guest_gicr=0x0f520000, affinity=0x10300,
                   root_irq=590, guest_irq=588, spi_count=960),
    'xza100': dict(hv=0xb0000000, shared=0xb1000000, private=0xb2000000,
                   ecam=0x34000000, gicd=0x29a00000, gicd_size=0x20000,
                   gicr=0x29b00000, gicr_size=0x100000,
                   guest_gicr=0x29be0000, affinity=0x301,
                   root_irq=105, guest_irq=101, spi_count=128),
}


def command(args):
    result = subprocess.run([str(x) for x in args], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip()


def disjoint(start, size, other_start, other_size):
    return start + size <= other_start or other_start + other_size <= start


def assigned_irqs(cell):
    result = []
    for irq in cell.irqchips:
        bits = irq.pin_bitmap_lo | irq.pin_bitmap_hi << 64
        result.extend(irq.pin_base + n for n in range(128) if bits >> n & 1)
    return result


def pci_devices(cell):
    size = struct.calcsize(PCI_FORMAT)
    start = len(cell.data) - cell.num_pci_devices * size
    return [struct.unpack_from(PCI_FORMAT, cell.data, start + n * size)
            for n in range(cell.num_pci_devices)]


class XZ100ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='jailhouse-xz-configs-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cross = os.environ.get('CROSS_COMPILE', 'aarch64-linux-gnu-')
        cls.built = {}
        for board in BOARDS:
            cells = []
            for suffix in ('', '-linux'):
                name = board + suffix
                obj = cls.directory / (name + '.o')
                binary = cls.directory / (name + '.cell')
                command([cross + 'gcc', '-c', '-O2', '-Wall', '-Wextra',
                         '-Werror', '-I' + str(ROOT / 'include'),
                         '-I' + str(ROOT / 'hypervisor/include'),
                         '-I' + str(ROOT / 'hypervisor/arch/arm64/include'),
                         ROOT / 'configs/arm64' / (name + '.c'), '-o', obj])
                command([cross + 'objcopy', '-O', 'binary',
                         '--only-section=.data',
                         obj, binary])
                cells.append(binary)
            dtb = cls.directory / (board + '.dtb')
            # The helper addresses /memory by its exact name, without @unit.
            command(['dtc', '-Wno-unit_address_vs_reg',
                     '-I', 'dts', '-O', 'dtb',
                     '-o', dtb, ROOT / 'configs/arm64/dts' /
                     ('inmate-' + board + '.dts')])
            cls.built[board] = (SystemConfig(cells[0].read_bytes()),
                                CellConfig(cells[1].read_bytes()), dtb, cells)

    def prop(self, dtb, node, name):
        return [int(x, 16) for x in command(
            ['fdtget', '-t', 'x', dtb, node, name]).split()]

    def test_binary_abi_and_initial_cpu_ownership(self):
        for board, (system, guest, _, _) in self.built.items():
            with self.subTest(board=board):
                self.assertEqual((system.arch, guest.arch), ('arm64', 'arm64'))
                self.assertEqual(system.root_cell.cpus, set(range(8)))
                self.assertEqual(guest.cpus, {7})
                self.assertEqual(guest.cpu_reset_address, 0)
                self.assertEqual(struct.unpack_from(
                    '<I', system.data, 8)[0], 3)
                self.assertEqual(system.iommus, [])
                self.assertEqual(system.pci_domain, 0x10)
                self.assertEqual(system.pci_is_virtual, 1)
                self.assertEqual(system.arm_maintenance_irq, 25)

    def test_memory_permissions_and_no_overlaps(self):
        for board, (system, guest, _, _) in self.built.items():
            expected = BOARDS[board]
            with self.subTest(board=board):
                self.assertEqual(system.hypervisor_memory.phys_start,
                                 expected['hv'])
                self.assertEqual(system.hypervisor_memory.size, 0x1000000)
                for cell in (system.root_cell, guest):
                    regions = [m for m in cell.memory_regions if m.size]
                    for i, region in enumerate(regions):
                        self.assertEqual(region.phys_start % 4096, 0)
                        self.assertEqual(region.virt_start % 4096, 0)
                        self.assertEqual(region.size % 4096, 0)
                        for other in regions[i + 1:]:
                            self.assertFalse(region.virt_overlaps(other))
                            if not (region.flags | other.flags) & COMM:
                                self.assertFalse(region.phys_overlaps(other))
                        if not region.flags & COMM:
                            self.assertTrue(disjoint(
                                region.phys_start, region.size,
                                expected['hv'], 0x1000000))
                self.assertFalse(any(m.flags & (DMA | IO)
                                     for m in guest.memory_regions))
                self.assertEqual(len(guest.memory_regions), 12)
                loader, ram, comm = guest.memory_regions[9:]
                self.assertEqual((loader.phys_start,
                                  loader.virt_start, loader.size),
                                 (expected['private'], 0, 65536))
                self.assertEqual((ram.phys_start, ram.virt_start, ram.size),
                                 (expected['private'] + 65536,
                                  expected['private'] + 65536, 0x1fff0000))
                self.assertEqual(loader.flags, READ | WRITE | EXEC | LOAD)
                self.assertEqual(ram.flags, loader.flags)
                self.assertEqual((comm.virt_start, comm.size, comm.flags),
                                 (0x80000000, 4096, READ | WRITE | COMM))

    def test_shared_memory_write_matrix(self):
        for board, (system, guest, _, _) in self.built.items():
            with self.subTest(board=board):
                root_shared = system.root_cell.memory_regions[:9]
                guest_shared = guest.memory_regions[:9]
                self.assertEqual([n for n, r in enumerate(root_shared)
                                  if r.flags & WRITE], [1, 2, 7])
                self.assertEqual([n for n, r in enumerate(guest_shared)
                                  if r.flags & WRITE], [1, 4, 8])
                for root, inmate in zip(root_shared, guest_shared):
                    self.assertEqual((root.phys_start, root.size),
                                     (inmate.phys_start, inmate.size))
                    self.assertFalse(root.flags & (DMA | IO | EXEC))
                    self.assertFalse(inmate.flags & (DMA | IO | EXEC))
                    if root.size:
                        self.assertTrue(root.flags & SHARED)
                        self.assertTrue(inmate.flags & SHARED)
                self.assertEqual(root_shared[0].phys_start,
                                 BOARDS[board]['shared'])
                self.assertEqual(root_shared[6].size, 0)

    def test_trapped_controller_apertures_not_direct_mapped(self):
        for board, (system, guest, _, _) in self.built.items():
            e = BOARDS[board]
            for cell in (system.root_cell, guest):
                for region in cell.memory_regions:
                    if not region.size or region.flags & COMM:
                        continue
                    for start, size in [(e['gicd'], e['gicd_size']),
                                        (e['gicr'], e['gicr_size']),
                                        (e['ecam'], 0x200000)]:
                        with self.subTest(board=board, start=hex(start)):
                            self.assertTrue(disjoint(region.phys_start,
                                                     region.size, start, size))

    def test_irq_ownership_and_endpoint_separation(self):
        for board, (system, guest, _, _) in self.built.items():
            e = BOARDS[board]
            with self.subTest(board=board):
                root_irqs = assigned_irqs(system.root_cell)
                self.assertEqual(len(root_irqs), len(set(root_irqs)))
                self.assertEqual(set(root_irqs),
                                 set(range(32, 32 + e['spi_count'])))
                self.assertEqual(assigned_irqs(guest),
                                 [e['guest_irq'], e['guest_irq'] + 1])
                self.assertEqual(system.root_cell.vpci_irq_base + 32,
                                 e['root_irq'])
                self.assertEqual(guest.vpci_irq_base + 32, e['guest_irq'])
                self.assertTrue(set(assigned_irqs(guest)).isdisjoint(
                    [e['root_irq'], e['root_irq'] + 1]))
                self.assertTrue(all(i.address == e['gicd']
                                    for i in guest.irqchips))

    def test_pci_peers_have_no_physical_devices_or_msi(self):
        for board, (system, guest, _, _) in self.built.items():
            for cell, peers in [(system.root_cell, (0, 0)), (guest, (2, 1))]:
                with self.subTest(board=board, cell=cell.name):
                    devices = pci_devices(cell)
                    self.assertEqual(len(devices), 2)
                    for index, device in enumerate(devices):
                        self.assertEqual(device[:4], (3, 0, 0x10, index << 3))
                        self.assertEqual(device[4:10], (0xfffff000, 0, 0,
                                                        0, 0, 0))
                        self.assertEqual(device[10:17], (0, 0, 0, 0, 0, 0, 0))
                        self.assertEqual(device[17:],
                                         ((0, peers[0], 3, 0) if index == 0
                                          else (5, peers[1], 2, 1)))

    def test_dts_matches_cpu_ram_gic_and_virtual_pci(self):
        for board, (system, guest, dtb, _) in self.built.items():
            e = BOARDS[board]
            with self.subTest(board=board):
                cpu = '/cpus/cpu@%x' % e['affinity']
                self.assertEqual(self.prop(dtb, cpu, 'reg'),
                                 [0, e['affinity']])
                self.assertEqual(self.prop(dtb, '/memory', 'reg'),
                                 [0, e['private'] + 65536, 0, 0x1fff0000])
                gic = '/interrupt-controller@%x' % e['gicd']
                self.assertEqual(self.prop(dtb, gic, 'reg'),
                                 [0, e['gicd'], 0, e['gicd_size'],
                                  0, e['guest_gicr'], 0, 0x20000])
                pci = '/pci@%x' % e['ecam']
                self.assertEqual(self.prop(dtb, pci, 'reg'),
                                 [0, system.pci_mmconfig_base, 0, 0x100000])
                self.assertEqual(self.prop(dtb, pci, 'linux,pci-domain'), [16])
                pci_props = command(['fdtget', '-p', dtb, pci]).split()
                self.assertEqual('dma-coherent' in pci_props,
                                 board == 'xza100')
                mapping = self.prop(dtb, pci, 'interrupt-map')
                self.assertEqual(len(mapping), 16)
                self.assertEqual([mapping[6] + 32, mapping[14] + 32],
                                 assigned_irqs(guest))
                self.assertEqual(mapping[0:4], [0, 0, 0, 1])
                self.assertEqual(mapping[8:12], [0x800, 0, 0, 2])
                self.assertEqual(self.prop(dtb, pci, 'interrupt-map-mask'),
                                 [0xf800, 0, 0, 7])
                properties = command(['fdtget', '-p', dtb, '/chosen']).split()
                self.assertNotIn('linux,initrd-start', properties)
                self.assertNotIn('linux,initrd-end', properties)
                args = command(['fdtget', dtb, '/chosen', 'bootargs']).split()
                self.assertIn('arm64.nopauth', args)
                self.assertIn('irqchip.gicv3_nolpi=1', args)
                self.assertNotIn('smrs.ssh=1', args)

    def test_existing_jailhouse_resource_checker(self):
        for board, (_, _, _, cells) in self.built.items():
            with self.subTest(board=board):
                command([sys.executable, ROOT / 'tools/jailhouse-config-check',
                         *cells])


if __name__ == '__main__':
    unittest.main(verbosity=2)
