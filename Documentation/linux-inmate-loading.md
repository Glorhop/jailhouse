# Loading Linux into private ARM inmate RAM

Copyright (c) Glorhop, 2026. Licensed under the GNU GPL, version 2;
see COPYING.

The ARM/ARM64 Linux loader accepts private readable, writable, executable
LOADABLE RAM without requiring DMA permission. This allows CPU-only inmates
such as XZA100 and XZB100 to boot without granting devices access to their RAM.
IO, communication and root-shared regions cannot hold the Linux images. The
legacy DMA-based RAM predicate and x86/E820 path are unchanged.

Image placement includes the actual region start, loader reservation, DTB
growth, alignment gaps and the ARM64 Image header's runtime size (including
BSS). ARM64 images must have a recognized little-endian header with a nonzero
runtime size and page-aligned text offset. Unsupported headers are rejected
instead of estimating their memory footprint.

When an initramfs is supplied, reserve its compressed image and its expanded
payload. Gzip expansion is measured by streaming the input; uncompressed newc,
crc and odc cpio images use their file size. For other compression formats,
supply the measured expanded size explicitly:

    jailhouse cell linux guest.cell Image -d guest.dtb -i initrd.xz --initrd-unpacked-size 0x8000000 -w /tmp/guest-boot.dtb

The -w option produces the modified DTB and prints commands; it does not
create or start a cell. A manual expansion value cannot understate a measured
gzip/cpio size. Negative decompression factors and an expansion override
without an initrd are rejected. An explicit --kernel-decomp-factor 0
disables that margin without disabling Image/BSS or initramfs accounting.

These checks cover static placement, not the guest's subsequent memory
demand. Allow additional RAM for page tables, initramfs metadata and running
applications. A malformed image or insufficient region fails before the
cell creation path is reached.

Run the standalone offline boundary tests without kernel builds, board files
or device access:

    python3 -B -m unittest discover -s tests -p test_linux_loader.py -v
