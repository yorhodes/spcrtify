"""Configure a fresh Pi boot partition without duplicate KMS overlays."""
import argparse
from pathlib import Path
import re


def configure(boot: Path, video="composite", shutdown_button=False):
    config = boot / "config.txt"
    cmdline = boot / "cmdline.txt"
    value = config.read_text()
    value = re.sub(r"\n# BEGIN SPCRTIFY\n.*?# END SPCRTIFY\n?", "\n", value, flags=re.S)
    # The generic vc4 line lives in the original global section. Keep exactly
    # one, and leave all other upstream boot settings intact.
    value = re.sub(r"^\s*dtoverlay=vc4-kms-v3d(?:,.*)?\s*$", "", value, flags=re.M)
    block = ["[all]", "dtoverlay=vc4-kms-v3d" + (",composite" if video == "composite" else ""),
             "enable_tvout=" + ("1" if video == "composite" else "0"),
             "dtparam=watchdog=on", "disable_splash=1"]
    if shutdown_button:
        block.append("dtoverlay=gpio-shutdown,gpio_pin=3,active_low=1,gpio_pull=up")
    config.write_text(value.rstrip() + "\n\n# BEGIN SPCRTIFY\n" + "\n".join(block) + "\n# END SPCRTIFY\n")
    args = cmdline.read_text().split()
    managed = {"vc4.tv_norm", "consoleblank", "vt.global_cursor_default", "loglevel", "quiet"}
    args = [arg for arg in args if arg.split("=", 1)[0] not in managed]
    args += ["consoleblank=0", "vt.global_cursor_default=0", "quiet", "loglevel=3"]
    if video == "composite":
        args += ["vc4.tv_norm=NTSC"]
    cmdline.write_text(" ".join(args) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boot", type=Path)
    parser.add_argument("--video", choices=("composite", "hdmi"), default="composite")
    parser.add_argument("--shutdown-button", action="store_true")
    args = parser.parse_args()
    configure(args.boot, args.video, args.shutdown_button)
