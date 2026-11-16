#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (c) Glorhop, 2026
#
"""Bind the built ARM64 firmware to its audited Linux executable mappings."""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import tempfile

PAGE_SIZE = 4096


def elf(path):
    """Read linked firmware sections and symbols without external tools."""
    data = path.read_bytes()
    ident = b'\x7fELF\x02\x01'
    if (data[:6] != ident or
            struct.unpack_from('<H', data, 18)[0] != 183):
        raise ValueError('Expected little-endian ELF64 AArch64')
    offset = struct.unpack_from('<Q', data, 40)[0]
    stride, count, names_index = struct.unpack_from('<HHH', data, 58)
    if (stride != 64 or not count or names_index >= count or
            offset + count * stride > len(data)):
        raise ValueError('Invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * stride)
                for i in range(count)]
    names = sections[names_index]
    names = data[names[4]:names[4] + names[5]]
    decoded, symbols = [], {}
    for section in sections:
        name, kind, flags, address, start, size, link, _, _, entry = section
        if kind != 8 and start + size > len(data):
            raise ValueError('Truncated ELF section')
        name = names[name:names.index(b'\0', name)].decode()
        decoded.append(dict(name=name, type=kind, flags=flags, address=address,
                            offset=start, size=size))
        if kind != 2:
            continue
        if entry != 24 or size % entry or link >= count:
            raise ValueError('Invalid ELF symbol table')
        strings = sections[link]
        strings = data[strings[4]:strings[4] + strings[5]]
        for pos in range(start, start + size, entry):
            name, _, _, index, value, length = struct.unpack_from(
                '<IBBHQQ', data, pos)
            name = strings[name:strings.index(b'\0', name)].decode()
            if name:
                symbols[name] = (value, length, index)
    return data, decoded, symbols


def signed(value, width):
    return value - (1 << width) if value & (1 << (width - 1)) else value


def layout(tree):
    """Reject changed EL1 control flow or an ELF/binary mismatch."""
    fw = (tree / 'hypervisor/jailhouse.bin').read_bytes()
    data, sections, symbols = elf(tree / 'hypervisor/hypervisor.o')
    base = symbols['hypervisor_header'][0]
    entry, end = symbols['arch_entry'][0], symbols['el2_entry'][0]
    cache = symbols['arm_dcaches_flush'][0]
    cache_end = min(v[0] for v in symbols.values() if v[0] > cache)
    signature, core, _, header_entry = struct.unpack_from('<8sQQQ', fw)
    if (signature != b'JAILHOUS' or header_entry != entry - base or
            not 0 < end - entry <= 1024):
        raise ValueError('Unrecognized hypervisor handover ABI')

    # Match objcopy -O binary -R .eh_frame, including inter-section padding.
    loaded = [s for s in sections if s['flags'] & 2 and s['type'] != 8
              and s['size'] and s['name'] != '.eh_frame']
    if min(s['address'] for s in loaded) != base:
        raise ValueError('Unexpected ELF firmware base')
    image_size = max(s['address'] + s['size'] for s in loaded) - base
    if image_size != len(fw):
        raise ValueError('ELF firmware size differs from the binary')
    image = bytearray(image_size)
    for section in loaded:
        start = section['address'] - base
        offset, size = section['offset'], section['size']
        image[start:start + size] = data[offset:offset + size]
    if image != fw:
        raise ValueError('Firmware bytes do not match the ELF image')

    spans = [(entry - base, end - base), (cache - base, cache_end - base)]
    if any(a < PAGE_SIZE or a % 4 or b % 4 or a >= b or b > len(fw)
           for a, b in spans):
        raise ValueError('Invalid EL1 code span')
    if struct.unpack_from('<I', fw, cache_end - base - 4)[0] != 0xd65f03c0:
        raise ValueError('Cache helper must end in ret')
    # Entry may only call the cache helper. Other branches must stay within
    # these two spans; an unknown indirect transfer requires a code review.
    calls, hvcs = [], 0
    for start, stop in spans:
        for offset in range(start, stop, 4):
            insn = struct.unpack_from('<I', fw, offset)[0]
            target = None
            if insn & 0xfe000000 == 0xd6000000:
                if not (insn == 0xd65f03c0 and offset == cache_end - base - 4):
                    raise ValueError('Unreviewed indirect EL1 transfer')
            if insn & 0x7c000000 == 0x14000000:
                target = offset + (signed(insn & 0x3ffffff, 26) << 2)
                if insn & 0x80000000:
                    calls.append(target)
            elif (insn & 0xff000010 == 0x54000000 or
                  insn & 0x7e000000 == 0x34000000):
                target = offset + (signed((insn >> 5) & 0x7ffff, 19) << 2)
            elif insn & 0x7e000000 == 0x36000000:
                target = offset + (signed((insn >> 5) & 0x3fff, 14) << 2)
            if (target is not None and
                    not any(a <= target < b for a, b in spans)):
                raise ValueError('EL1 branch escapes reviewed handover code')
            if insn & 0xffe0001f == 0xd4000002:
                hvcs += 1
    if calls != [cache - base] or hvcs != 2:
        raise ValueError('Changed EL1 calls or HVC sequence; review required')

    pages = sorted({page for start, stop in spans
                    for page in range(start & -PAGE_SIZE,
                                      (stop + PAGE_SIZE - 1) & -PAGE_SIZE,
                                      PAGE_SIZE)})
    for page in pages:
        if page < PAGE_SIZE or page + PAGE_SIZE > core:
            raise ValueError('Executable page overlaps header or exceeds core')
        if not any(s['flags'] & 4 and s['address'] <= base + page and
                   s['address'] + s['size'] >= base + page + PAGE_SIZE
                   for s in sections):
            raise ValueError('EL1 page is not entirely in executable ELF text')
        if any(s['flags'] & 1 and s['size'] and
               s['address'] < base + page + PAGE_SIZE and
               base + page < s['address'] + s['size'] for s in sections):
            raise ValueError('EL1 page overlaps writable ELF data')
    ranges = []
    for page in pages:
        if ranges and ranges[-1][1] == page:
            ranges[-1][1] += PAGE_SIZE
        else:
            ranges.append([page, page + PAGE_SIZE])
    return dict(firmware_sha256=hashlib.sha256(fw).hexdigest(),
                firmware_size=len(fw), core_size=core, entry=header_entry,
                exec_ranges=ranges, exec_pages=len(pages),
                el1_code_spans=spans,
                elf_sha256=hashlib.sha256(data).hexdigest())


def render(report):
    rows = [
        '/* Generated by gen-arm64-entry-layout.py; do not edit. */',
        '#define JH_EL1_FIRMWARE_SIZE %dUL' % report['firmware_size'],
        '#define JH_EL1_CORE_SIZE 0x%xUL' % report['core_size'],
        '#define JH_EL1_ENTRY 0x%xUL' % report['entry'],
        'static const u8 jh_el1_firmware_sha256[32] = {',
    ]
    digest = report['firmware_sha256']
    for start in range(0, 64, 16):
        values = ['0x' + digest[i:i + 2] for i in range(start, start + 16, 2)]
        rows.append('\t' + ', '.join(values) + ',')
    rows += ['};', 'static const struct {',
             '\tunsigned long start, end;',
             '} jh_el1_exec_ranges[] = {']
    rows += ['\t{ 0x%xUL, 0x%xUL },' % (a, b)
             for a, b in report['exec_ranges']]
    return '\n'.join(rows + ['};', ''])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hypervisor-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    text = render(layout(args.hypervisor_dir.parent))
    if args.output.exists() and args.output.read_text() == text:
        return
    with tempfile.NamedTemporaryFile(mode='w', dir=args.output.parent,
                                     prefix=args.output.name + '.',
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    try:
        os.replace(temporary, args.output)
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        raise SystemExit('ARM64 firmware layout rejected: ' + str(error))
