# ARM64 Linux entry mapping

On kernels which remove execute permission from ioremap aliases, the driver
cannot enter Jailhouse through an ordinary PAGE_KERNEL_EXEC mapping. ARM64
therefore allocates a fresh virtual area and creates 4 KiB page mappings. All
pages start writable and non-executable while firmware, configuration and
per-CPU data are copied. Only the pages containing the EL1 entry and its cache
maintenance helper become read-only and executable before CPU handover. Every
PTE is checked before the first CPU enters EL2. Guest image copies use a
non-executable Linux alias.

The build generates driver/arm64-entry-layout.h from the linked hypervisor ELF
and jailhouse.bin. It checks that the binary is exactly the ELF load image,
that executable pages do not overlap writable ELF sections or the mutable
header, and that the EL1 entry has the reviewed direct-call/two-HVC sequence.
Unknown indirect control transfers or branches outside the reviewed spans
fail the build. Updating entry assembly may therefore require updating this
review, rather than merely rebuilding.

The module checks the complete firmware SHA256, size, entry offset and core
size before mapping. Install the module and firmware from the same build.
A stale or independently rebuilt firmware is rejected. The generated header
is a build output, not a board configuration or a source-controlled hash.

The mapper currently supports Linux with 4 KiB pages and fails enable on
other page sizes. It requires CONFIG_KALLSYMS_ALL, CONFIG_KPROBES on kernels
using kprobe symbol lookup, and the kernel SHA256 library. The checked XZB100
5.15 and XZA100 6.6 configurations provide these requirements. ARM and x86
keep their existing mapping paths.

For an initial mapping check, load jailhouse.ko with prepare_only=1. Enable
then validates the firmware and actual page permissions, unwinds resources
and returns EAGAIN without entering EL2. This is an explicit diagnostic mode,
not evidence that CPU transfer or device isolation has passed. Normal enable
requires prepare_only=0 and the board's current resource/boot checks.

Run the build-independent regression tests with:

    python3 -m unittest discover -s tests -p test_arm64_entry_layout.py -v

The integrated sources were compiled against the two board kernels. A new
module/firmware pair still needs its own hardware validation; previous results
from separately patched or vendor trees do not certify this build.
