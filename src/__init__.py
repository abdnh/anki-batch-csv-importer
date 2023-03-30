from __future__ import annotations

import functools
import json
from pathlib import Path

from anki.collection import Collection, ImportCsvRequest, OpChangesWithCount
from aqt import mw
from aqt.import_export.import_csv_dialog import ImportCsvDialog
from aqt.import_export.importing import CsvImporter
from aqt.operations import CollectionOp
from aqt.qt import *
from aqt.utils import tooltip

ADDON_NAME = "Batch Import CSV"


class BatchCSVImportDialog(ImportCsvDialog):
    def __init__(
        self, folder: str, on_accepted: Callable[[ImportCsvRequest], None]
    ) -> None:
        path = Path(folder)
        self.files: list[str] = []
        for ext in CsvImporter.accepted_file_endings:
            self.files.extend([p.as_posix() for p in path.rglob(f"*{ext}")])
        if not self.files:
            return
        super().__init__(mw, self.files[0], on_accepted)
        self.setWindowTitle("Batch Import CSV")
        # FIXME: might be unreliable
        mw.progress.timer(
            1000,
            lambda: self.web.eval(
                "document.getElementsByClassName('filename')[0].textContent = %s"
                % json.dumps(folder)
            ),
            repeat=False,
        )

    def do_import(self, data: bytes) -> None:
        self.accept()
        request = ImportCsvRequest()
        request.ParseFromString(data)
        want_cancel = False

        def update_progress(i: int) -> None:
            nonlocal want_cancel
            want_cancel = mw.progress.want_cancel()
            mw.progress.update(
                f"Importing file {i} of {len(self.files)}",
                value=i - 1,
                max=len(self.files),
            )

        def op(col: Collection) -> OpChangesWithCount:
            mw.taskman.run_on_main(lambda: mw.progress.set_title(ADDON_NAME))
            undo_entry = col.add_custom_undo_entry("Batch CSV Import")
            changes = None
            i = 1
            for i, file in enumerate(self.files, start=1):
                mw.taskman.run_on_main(functools.partial(update_progress, i=i))
                if want_cancel:
                    break
                request.path = file
                request.metadata.deck_id = col.decks.id(Path(file).stem)
                col.import_csv(request)
                changes = col.merge_undo_entries(undo_entry)
            return OpChangesWithCount(count=i, changes=changes)

        def on_success(changes: OpChangesWithCount) -> None:
            tooltip(f"Imported {changes.count} files")

        CollectionOp(mw, op=op).success(success=on_success).run_in_background()


def on_import() -> None:
    folder = QFileDialog.getExistingDirectory(mw, caption="Choose a folder")
    if folder:
        BatchCSVImportDialog(folder, None)


action = QAction(ADDON_NAME, mw)
qconnect(action.triggered, on_import)
mw.form.menuTools.addAction(action)
