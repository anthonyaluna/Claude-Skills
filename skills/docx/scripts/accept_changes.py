"""Accept all tracked changes in a DOCX file using LibreOffice.

Requires LibreOffice (soffice) to be installed.
"""

import argparse
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from office.soffice import get_soffice_env

logger = logging.getLogger(__name__)

ACCEPT_CHANGES_MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
    Sub AcceptAllTrackedChanges()
        Dim document As Object
        Dim dispatcher As Object

        document = ThisComponent.CurrentController.Frame
        dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")

        dispatcher.executeDispatch(document, ".uno:AcceptAllTrackedChanges", "", 0, Array())
        If ThisComponent.Redlines.Count = 0 Then
            ThisComponent.store()
            Dim receipt As Integer
            receipt = FreeFile
            Open Environ("CLAUDE_SKILL_OFFICE_RECEIPT") For Output As #receipt
            Print #receipt, "saved"
            Close #receipt
        End If
        ThisComponent.close(True)
    End Sub
</script:module>"""


def accept_changes(
    input_file: str,
    output_file: str,
) -> tuple[None, str]:
    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        return None, f"Error: Input file not found: {input_file}"

    if not input_path.suffix.lower() == ".docx":
        return None, f"Error: Input file is not a DOCX file: {input_file}"

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and input_path.samefile(output_path):
            return None, "Error: input and output must be distinct files"

        with tempfile.TemporaryDirectory(
            prefix="libreoffice-docx-", dir=output_path.parent
        ) as work:
            work_dir = Path(work).resolve()
            staged = work_dir / "document.docx"
            shutil.copy2(input_path, staged)
            profile_dir = work_dir / "profile"
            profile_dir.mkdir(mode=0o700)
            if not _setup_libreoffice_macro(profile_dir):
                return None, "Error: Failed to setup LibreOffice macro"

            receipt = profile_dir / "accepted.txt"
            cmd = [
                "soffice",
                "--headless",
                f"-env:UserInstallation={profile_dir.as_uri()}",
                "--norestore",
                "vnd.sun.star.script:Standard.Module1.AcceptAllTrackedChanges?language=Basic&location=application",
                str(staged),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=False,
                env={**get_soffice_env(), "CLAUDE_SKILL_OFFICE_RECEIPT": str(receipt)},
            )
            if result.returncode != 0:
                return None, f"Error: LibreOffice failed: {result.stderr}"
            if not receipt.is_file():
                return None, "Error: LibreOffice did not confirm that tracked changes were accepted"
            staged.replace(output_path)
    except subprocess.TimeoutExpired:
        return None, f"Error: LibreOffice timed out before confirming tracked changes: {output_file}"
    except OSError as error:
        return None, f"Error: Could not write accepted document: {error}"

    return (
        None,
        f"Successfully accepted all tracked changes: {input_file} -> {output_file}",
    )


def _setup_libreoffice_macro(profile_dir: Path) -> bool:
    profile_dir = Path(profile_dir)
    macro_dir = profile_dir / "user" / "basic" / "Standard"
    macro_file = macro_dir / "Module1.xba"

    try:
        if any(profile_dir.iterdir()):
            return False
    except Exception as e:
        logger.warning(f"Failed to setup LibreOffice macro: {e}")
        return False

    subprocess.run(
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--terminate_after_init",
        ],
        capture_output=True,
        timeout=10,
        check=False,
        env=get_soffice_env(),
    )

    try:
        macro_dir.mkdir(parents=True, exist_ok=True)
        macro_file.write_text(ACCEPT_CHANGES_MACRO)
    except Exception as e:
        logger.warning(f"Failed to setup LibreOffice macro: {e}")
        return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Accept all tracked changes in a DOCX file"
    )
    parser.add_argument("input_file", help="Input DOCX file with tracked changes")
    parser.add_argument(
        "output_file", help="Output DOCX file (clean, no tracked changes)"
    )
    args = parser.parse_args()

    _, message = accept_changes(args.input_file, args.output_file)
    print(message)

    if "Error" in message:
        raise SystemExit(1)
